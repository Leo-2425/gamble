import discord
from discord.ext import commands
from discord.ui import Button, View
import random
import asyncio
import sqlite3
from datetime import datetime, timedelta
import time

# Configuration
OWNER_IDS = [123456789012345678]  # Replace with your user ID
COOLDOWN_RATE = 1  # Commands per 10 seconds
COOLDOWN_TIME = 10  # Seconds
ELEMENT_EMOJIS = {
    'Fire': '🔥', 'Water': '💧', 'Earth': '🌿',
    'Air': '💨', 'Dark': '🌑', 'Light': '✨'
}

class CooldownView(View):
    """View for handling cooldown buttons"""
    def __init__(self, cooldown_time):
        super().__init__(timeout=cooldown_time)
        self.cooldown_time = cooldown_time
        self.last_used = time.time()

    async def interaction_check(self, interaction):
        if time.time() - self.last_used < self.cooldown_time:
            remaining = int(self.cooldown_time - (time.time() - self.last_used))
            await interaction.response.send_message(
                f"⏳ Please wait {remaining} seconds before using this again!",
                ephemeral=True
            )
            return False
        self.last_used = time.time()
        return True

class MythicalBeastArenaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents, owner_ids=set(OWNER_IDS))
        
        self.conn = sqlite3.connect('mythical_beasts.db')
        self.setup_database()
        self.spam_control = commands.CooldownMapping.from_cooldown(COOLDOWN_RATE, COOLDOWN_TIME, commands.BucketType.user)

    def setup_database(self):
        cursor = self.conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                eldergems REAL DEFAULT 1000.0,
                mana_crystals INTEGER DEFAULT 50,
                guild_id INTEGER DEFAULT NULL,
                rank TEXT DEFAULT 'Novice',
                last_daily_claim TIMESTAMP DEFAULT NULL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS beasts (
                beast_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                beast_name TEXT,
                beast_type TEXT,
                element TEXT,
                rarity TEXT,
                level INTEGER DEFAULT 1,
                experience INTEGER DEFAULT 0,
                power INTEGER,
                health INTEGER,
                magic INTEGER,
                equipped_item TEXT DEFAULT NULL,
                FOREIGN KEY (user_id) REFERENCES players(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_name TEXT,
                item_type TEXT,
                rarity TEXT,
                quantity INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES players(user_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_name TEXT UNIQUE,
                leader_id INTEGER,
                members_count INTEGER DEFAULT 1,
                guild_level INTEGER DEFAULT 1,
                guild_power INTEGER DEFAULT 0,
                FOREIGN KEY (leader_id) REFERENCES players(user_id)
            )
        ''')
        self.conn.commit()
    
    async def setup_hook(self):
        await self.add_cog(CoreCommands(self))
        await self.add_cog(BeastCommands(self))
        await self.add_cog(GamblingCommands(self))
        await self.add_cog(MarketCommands(self))
        await self.add_cog(GuildCommands(self))
        await self.add_cog(AlchemyCommands(self))
        await self.add_cog(AdminCommands(self))
        print(f'Logged in as {self.user}')

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            embed = discord.Embed(
                title="❌ Unknown Command",
                description=f"Use `!help` to see available commands",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Missing Argument",
                description=f"Correct usage: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏳ Command Cooldown",
                description=f"Try again in {error.retry_after:.1f} seconds",
                color=0xf1c40f
            )
            await ctx.send(embed=embed, delete_after=error.retry_after)
        elif isinstance(error, commands.CheckFailure):
            embed = discord.Embed(
                title="⛔ Permission Denied",
                description="You don't have permission to use this command",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="⚠️ Unexpected Error",
                description=f"```{str(error)}```",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
            raise error

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(hidden=True)
    @commands.is_owner()
    async def give(self, ctx, item_id: int, quantity: int, user: discord.Member):
        """Give items to a player (Owner only)"""
        cursor = self.bot.conn.cursor()
        
        cursor.execute('SELECT item_name FROM inventory WHERE inventory_id = ?', (item_id,))
        item = cursor.fetchone()
        if not item:
            await ctx.send("❌ Invalid item ID!")
            return
        
        try:
            cursor.execute('''
                UPDATE inventory
                SET quantity = quantity + ?
                WHERE inventory_id = ? AND user_id = ?
            ''', (quantity, item_id, user.id))
            
            if cursor.rowcount == 0:
                cursor.execute('''
                    INSERT INTO inventory (user_id, item_name, item_type, rarity, quantity)
                    SELECT ?, item_name, item_type, rarity, ?
                    FROM inventory
                    WHERE inventory_id = ?
                ''', (user.id, quantity, item_id))
            
            self.bot.conn.commit()
            
            embed = discord.Embed(
                title="✨ Admin Action",
                description=f"Gave {quantity}x {item[0]} to {user.mention}",
                color=0x2ecc71
            )
            await ctx.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                title="⚠️ Database Error",
                description=f"```{str(e)}```",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)

class CoreCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.elements = ['Fire', 'Water', 'Earth', 'Air', 'Dark', 'Light']
        self.rarities = {
            'Common': {'chance': 0.60, 'color': 0x95a5a6},
            'Uncommon': {'chance': 0.25, 'color': 0x2ecc71},
            'Rare': {'chance': 0.10, 'color': 0x3498db},
            'Epic': {'chance': 0.04, 'color': 0x9b59b6},
            'Legendary': {'chance': 0.009, 'color': 0xf1c40f},
            'Divine': {'chance': 0.001, 'color': 0xe74c3c}
        }
        self.beast_types = {
            'Fire': ['Phoenix', 'Dragon', 'Hellhound', 'Salamander', 'Ifrit'],
            'Water': ['Kraken', 'Leviathan', 'Selkie', 'Kappa', 'Hydra'],
            'Earth': ['Griffin', 'Golem', 'Manticore', 'Treant', 'Basilisk'],
            'Air': ['Pegasus', 'Thunderbird', 'Garuda', 'Sylph', 'Harpy'],
            'Dark': ['Cerberus', 'Shade', 'Nightmare', 'Banshee', 'Wraith'],
            'Light': ['Unicorn', 'Angel', 'Kirin', 'Valkyrie', 'Seraph']
        }

    def get_player_data(self, user_id):
        cursor = self.bot.conn.cursor()
        cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result is None:
            cursor.execute('INSERT INTO players (user_id) VALUES (?)', (user_id,))
            self.create_starter_beast(user_id)
            self.bot.conn.commit()
            cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
        
        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, result))

    def create_starter_beast(self, user_id):
        element = random.choice(self.elements)
        beast_type = random.choice(self.beast_types[element])
        power = random.randint(10, 20)
        health = random.randint(50, 100)
        magic = random.randint(10, 20)
        
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            INSERT INTO beasts 
            (user_id, beast_name, beast_type, element, rarity, power, health, magic)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, beast_type, beast_type, element, 'Common', power, health, magic))
        self.bot.conn.commit()

    def get_random_rarity(self):
        roll = random.random()
        cumulative = 0
        for rarity, data in self.rarities.items():
            cumulative += data['chance']
            if roll <= cumulative:
                return rarity
        return 'Common'  # Fallback

    @commands.command()
    @commands.cooldown(2, 10, commands.BucketType.user)
    async def profile(self, ctx):
        player = self.get_player_data(ctx.author.id)
        cursor = self.bot.conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM beasts WHERE user_id = ?', (ctx.author.id,))
        beast_count = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT beast_name, level, element, rarity 
            FROM beasts 
            WHERE user_id = ? 
            ORDER BY (power + health + magic) DESC 
            LIMIT 1
        ''', (ctx.author.id,))
        strongest_beast = cursor.fetchone()
        strongest_beast_info = (
            f"{strongest_beast[0]} (Lvl {strongest_beast[1]}, {strongest_beast[2]}, {strongest_beast[3]})" 
            if strongest_beast else "None"
        )
        
        guild_info = "None"
        if player['guild_id']:
            cursor.execute('SELECT guild_name FROM guilds WHERE guild_id = ?', (player['guild_id'],))
            guild_result = cursor.fetchone()
            if guild_result:
                guild_info = guild_result[0]
        
        embed = discord.Embed(
            title=f"🧙 {ctx.author.name}'s Profile",
            color=0x9b59b6
        )
        embed.set_thumbnail(url=ctx.author.avatar.url)
        embed.add_field(name="💎 Eldergems", value=f"{player['eldergems']:.2f}", inline=True)
        embed.add_field(name="✨ Mana Crystals", value=str(player['mana_crystals']), inline=True)
        embed.add_field(name="🏅 Rank", value=player['rank'], inline=True)
        embed.add_field(name="🐉 Beasts", value=str(beast_count), inline=True)
        embed.add_field(name="⚔️ Strongest Beast", value=strongest_beast_info, inline=True)
        embed.add_field(name="🏰 Guild", value=guild_info, inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 86400, commands.BucketType.user)
    async def daily(self, ctx):
        player = self.get_player_data(ctx.author.id)
        if player['last_daily_claim'] and (datetime.now() - datetime.fromisoformat(player['last_daily_claim'])).days < 1:
            next_claim = datetime.fromisoformat(player['last_daily_claim']) + timedelta(days=1)
            delta = next_claim - datetime.now()
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            embed = discord.Embed(
                title="⏳ Daily Cooldown",
                description=f"Next claim in {hours}h {minutes}m {seconds}s",
                color=0xe74c3c
            )
            return await ctx.send(embed=embed)
        
        # Claim rewards
        eldergems = random.randint(100, 300)
        mana = random.randint(10, 30)
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            UPDATE players SET
                eldergems = eldergems + ?, 
                mana_crystals = mana_crystals + ?,
                last_daily_claim = ?
            WHERE user_id = ?
        ''', (eldergems, mana, datetime.now().isoformat(), ctx.author.id))
        
        # Bonus item
        bonus = ""
        if random.random() < 0.3:
            item_name = f"{random.choice(['Ancient', 'Mystic'])} {random.choice(['Scroll', 'Potion'])}"
            rarity = self.get_random_rarity()
            cursor.execute('''
                INSERT INTO inventory (user_id, item_name, item_type, rarity)
                VALUES (?, ?, ?, ?)
            ''', (ctx.author.id, item_name, 'Consumable', rarity))
            bonus = f"\n+ **{rarity} {item_name}**"
        
        self.bot.conn.commit()
        embed = discord.Embed(
            title="🎁 Daily Rewards Claimed!",
            description=f"Received:\n{eldergems}💎 Eldergems\n{mana}✨ Mana Crystals{bonus}",
            color=0x2ecc71
        )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def help(self, ctx):
        view = CooldownView(10)
        categories = {
            "📋 Core": ["profile", "daily", "inventory"],
            "🐲 Beasts": ["beasts", "summon", "battle", "train"],
            "🎲 Gambling": ["coinflip", "slot", "elementalwheel"],
            "💰 Market": ["market", "buy", "sell"],
            "🏰 Guilds": ["createguild", "joinguild", "guildinfo"],
            "🧪 Alchemy": ["brew", "evolve"]
        }
        
        embed = discord.Embed(title="🐉 Command Categories", color=0x9b59b6)
        for category, commands_list in categories.items():
            embed.add_field(
                name=category,
                value="\n".join([f"`!{cmd}`" for cmd in commands_list]),
                inline=True
            )
        
        await ctx.send(embed=embed, view=view)

    @commands.command()
    @commands.cooldown(2, 10, commands.BucketType.user)
    async def inventory(self, ctx):
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT inventory_id, item_name, item_type, rarity, quantity
            FROM inventory
            WHERE user_id = ?
            ORDER BY rarity, item_name
        ''', (ctx.author.id,))
        items = cursor.fetchall()
        
        if not items:
            embed = discord.Embed(
                title="🎒 Inventory",
                description="Your inventory is empty.",
                color=0x95a5a6
            )
            return await ctx.send(embed=embed)
        
        embed = discord.Embed(title="🎒 Inventory", color=0x3498db)
        for item in items:
            embed.add_field(
                name=f"ID {item[0]}: {item[1]} (x{item[4]})",
                value=f"Type: {item[2]} | Rarity: {item[3]}",
                inline=False
            )
        await ctx.send(embed=embed)

class BeastCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.core = self.bot.get_cog('CoreCommands')

    @commands.command()
    @commands.cooldown(2, 10, commands.BucketType.user)
    async def beasts(self, ctx):
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT beast_id, beast_name, element, rarity, level 
            FROM beasts WHERE user_id = ?
            ORDER BY level DESC
        ''', (ctx.author.id,))
        beasts = cursor.fetchall()
        
        if not beasts:
            return await ctx.send("You have no beasts! Use `!summon` to get one.")
        
        embed = discord.Embed(title=f"{ctx.author.name}'s Beasts", color=0x3498db)
        for beast in beasts:
            embed.add_field(
                name=f"ID {beast[0]}: {beast[1]}",
                value=f"{ELEMENT_EMOJIS[beast[2]]} {beast[2]} | {beast[3]} | Lv{beast[4]}",
                inline=False
            )
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def summon(self, ctx):
        player = self.core.get_player_data(ctx.author.id)
        if player['eldergems'] < 300:
            return await ctx.send("❌ You need 300💎 Eldergems to summon!")
        
        # Deduct cost
        cursor = self.bot.conn.cursor()
        cursor.execute('UPDATE players SET eldergems = eldergems - 300 WHERE user_id = ?', (ctx.author.id,))
        
        # Summon animation
        embed = discord.Embed(title="🔮 Summoning...", color=0x9b59b6)
        msg = await ctx.send(embed=embed)
        for step in [
            "Drawing ritual circles...",
            "Chanting ancient words...",
            "Channeling elemental energy..."
        ]:
            embed.description = step
            await msg.edit(embed=embed)
            await asyncio.sleep(1)
        
        # Create beast
        rarity = self.core.get_random_rarity()
        element = random.choice(list(self.core.beast_types.keys()))
        beast_type = random.choice(self.core.beast_types[element])
        multiplier = {
            'Common': 1.0, 'Uncommon': 1.2, 'Rare': 1.5,
            'Epic': 2.0, 'Legendary': 3.0, 'Divine': 5.0
        }[rarity]
        
        stats = {
            'power': int(random.randint(15, 30) * multiplier),
            'health': int(random.randint(80, 120) * multiplier),
            'magic': int(random.randint(15, 30) * multiplier)
        }
        
        cursor.execute('''
            INSERT INTO beasts 
            (user_id, beast_name, beast_type, element, rarity, power, health, magic)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ctx.author.id, beast_type, beast_type, element, rarity, stats['power'], stats['health'], stats['magic']))
        beast_id = cursor.lastrowid
        self.bot.conn.commit()
        
        embed = discord.Embed(
            title=f"{ELEMENT_EMOJIS[element]} Summon Successful!",
            description=f"You summoned a {rarity} {beast_type}!",
            color=self.core.rarities[rarity]['color']
        )
        embed.add_field(name="ID", value=f"#{beast_id}", inline=True)
        embed.add_field(name="Power", value=stats['power'], inline=True)
        embed.add_field(name="Health", value=stats['health'], inline=True)
        embed.add_field(name="Magic", value=stats['magic'], inline=True)
        await msg.edit(embed=embed)

    @commands.command()
    @commands.cooldown(2, 10, commands.BucketType.user)
    async def beast(self, ctx, beast_id: int):
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT * FROM beasts 
            WHERE beast_id = ? AND user_id = ?
        ''', (beast_id, ctx.author.id))
        beast = cursor.fetchone()
        
        if not beast:
            return await ctx.send("❌ Beast not found!")
        
        columns = [col[0] for col in cursor.description]
        beast_data = dict(zip(columns, beast))
        embed = discord.Embed(
            title=f"{ELEMENT_EMOJIS[beast_data['element']]} {beast_data['beast_name']}",
            color=self.core.rarities[beast_data['rarity']]['color']
        )
        embed.add_field(name="Level", value=beast_data['level'], inline=True)
        embed.add_field(name="Rarity", value=beast_data['rarity'], inline=True)
        embed.add_field(name="Element", value=beast_data['element'], inline=True)
        embed.add_field(name="Power", value=beast_data['power'], inline=True)
        embed.add_field(name="Health", value=beast_data['health'], inline=True)
        embed.add_field(name="Magic", value=beast_data['magic'], inline=True)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def battle(self, ctx, beast_id: int, opponent: discord.Member = None, opponent_beast_id: int = None):
        # Get player beast
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT beast_id, beast_name, element, level, power, health, magic, rarity
            FROM beasts WHERE beast_id = ? AND user_id = ?
        ''', (beast_id, ctx.author.id))
        player_beast = cursor.fetchone()
        
        if not player_beast:
            return await ctx.send("❌ Beast not found! Check your beasts with `!beasts`")
        
        # If no opponent specified, battle AI
        if not opponent:
            # Create AI opponent with similar stats
            ai_level = player_beast[3]
            ai_stats = {
                'power': player_beast[4] + random.randint(-5, 5),
                'health': player_beast[5] + random.randint(-20, 20),
                'magic': player_beast[6] + random.randint(-5, 5)
            }
            ai_element = random.choice(self.core.elements)
            ai_beast_type = random.choice(self.core.beast_types[ai_element])
            opponent_beast = (None, ai_beast_type, ai_element, ai_level, 
                             ai_stats['power'], ai_stats['health'], ai_stats['magic'], 'Unknown')
            opponent_name = "Wild Beast"
        else:
            # Get opponent beast
            if not opponent_beast_id:
                # Get opponent's strongest beast if not specified
                cursor.execute('''
                    SELECT beast_id, beast_name, element, level, power, health, magic, rarity
                    FROM beasts WHERE user_id = ? ORDER BY (power + health + magic) DESC LIMIT 1
                ''', (opponent.id,))
            else:
                cursor.execute('''
                    SELECT beast_id, beast_name, element, level, power, health, magic, rarity
                    FROM beasts WHERE beast_id = ? AND user_id = ?
                ''', (opponent_beast_id, opponent.id))
                
            opponent_beast = cursor.fetchone()
            if not opponent_beast:
                return await ctx.send("❌ Opponent beast not found!")
            opponent_name = opponent.name
            
        # Battle logic
        view = CooldownView(3)
        attack_btn = Button(style=discord.ButtonStyle.danger, label="Attack", row=0)
        special_btn = Button(style=discord.ButtonStyle.primary, label="Special", row=0)
        defend_btn = Button(style=discord.ButtonStyle.secondary, label="Defend", row=0)
        
        # Battle state
        player_hp = player_beast[5]
        opponent_hp = opponent_beast[5]
        player_defended = False
        special_cooldown = 0
        turn_count = 0
        battle_log = []
        
        # Element effectiveness 
        effectiveness = {
            'Fire': {'Water': 0.8, 'Air': 1.2},
            'Water': {'Fire': 1.2, 'Earth': 0.8},
            'Earth': {'Water': 1.2, 'Air': 0.8},
            'Air': {'Earth': 1.2, 'Fire': 0.8},
            'Dark': {'Light': 1.2, 'Dark': 0.8},
            'Light': {'Dark': 1.2, 'Light': 0.8}
        }
        
        # Update battle display
        async def update_battle(interaction=None):
            player_hp_percent = max(0, int((player_hp / player_beast[5]) * 100))
            opponent_hp_percent = max(0, int((opponent_hp / opponent_beast[5]) * 100))
            
            embed = discord.Embed(
                title=f"⚔️ Battle: {ctx.author.name} vs {opponent_name}",
                color=0xf1c40f
            )
            embed.add_field(
                name=f"{ELEMENT_EMOJIS[player_beast[2]]} {player_beast[1]} (Lv{player_beast[3]})",
                value=f"HP: {player_hp}/{player_beast[5]} [{player_hp_percent}%]\n" +
                      f"{'▓' * (player_hp_percent // 10)}{'░' * (10 - player_hp_percent // 10)}",
                inline=False
            )
            embed.add_field(
                name=f"{ELEMENT_EMOJIS[opponent_beast[2]]} {opponent_beast[1]} (Lv{opponent_beast[3]})",
                value=f"HP: {opponent_hp}/{opponent_beast[5]} [{opponent_hp_percent}%]\n" +
                      f"{'▓' * (opponent_hp_percent // 10)}{'░' * (10 - opponent_hp_percent // 10)}",
                inline=False
            )
            
            # Add battle log
            if battle_log:
                log_text = "\n".join(battle_log[-3:])
                embed.add_field(name="Battle Log", value=f"```{log_text}```", inline=False)
            
            # Special button cooldown
            if special_cooldown > 0:
                special_btn.label = f"Special ({special_cooldown})"
                special_btn.disabled = True
            else:
                special_btn.label = "Special"
                special_btn.disabled = False
                
            # Update message
            if interaction:
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                return embed
        
        # AI turn logic
        async def ai_turn():
            nonlocal opponent_hp, player_hp, battle_log, special_cooldown
            
            await asyncio.sleep(1)  # Dramatic pause
            
            # AI decides action
            if player_hp <= opponent_beast[4] * 1.2 and random.random() < 0.7:
                # If player can be defeated, likely attack
                multiplier = 1.0
                if player_beast[2] in effectiveness.get(opponent_beast[2], {}):
                    multiplier = effectiveness[opponent_beast[2]][player_beast[2]]
                
                damage = int(opponent_beast[4] * multiplier * random.uniform(0.8, 1.2))
                if player_defended:
                    damage = damage // 2
                    battle_log.append(f"{opponent_beast[1]} attacks for {damage} damage (reduced)")
                else:
                    battle_log.append(f"{opponent_beast[1]} attacks for {damage} damage")
                player_hp -= damage
            elif special_cooldown == 0 and random.random() < 0.4:
                # Use special occasionally
                damage = int(opponent_beast[6] * random.uniform(1.2, 1.5))
                if player_defended:
                    damage = damage // 2
                    battle_log.append(f"{opponent_beast[1]} uses special for {damage} damage (reduced)")
                else:
                    battle_log.append(f"{opponent_beast[1]} uses special for {damage} damage")
                player_hp -= damage
                special_cooldown = 3
                player_hp -= damage
                special_cooldown = 3
            else:
                # Defend sometimes
                battle_log.append(f"{opponent_beast[1]} defends")
            
            # Check if player defeated
            if player_hp <= 0:
                player_hp = 0
                return False
            return True
            
        # Player action handlers
        async def handle_attack(interaction):
            nonlocal opponent_hp, battle_log, player_defended
            
            # Reset defense status
            player_defended = False
            
            # Calculate damage with element effectiveness
            multiplier = 1.0
            if opponent_beast[2] in effectiveness.get(player_beast[2], {}):
                multiplier = effectiveness[player_beast[2]][opponent_beast[2]]
                
            damage = int(player_beast[4] * multiplier * random.uniform(0.8, 1.2))
            battle_log.append(f"{player_beast[1]} attacks for {damage} damage")
            opponent_hp -= damage
            
            # Check if opponent defeated
            if opponent_hp <= 0:
                opponent_hp = 0
                await battle_end(True)
                return
            
            # AI turn
            player_alive = await ai_turn()
            if not player_alive:
                await battle_end(False)
                return
                
            await update_battle(interaction)
            
        async def handle_special(interaction):
            nonlocal opponent_hp, battle_log, player_defended, special_cooldown
            
            # Reset defense status
            player_defended = False
            
            # Special attack damage based on magic stat
            damage = int(player_beast[6] * random.uniform(1.2, 1.5))
            battle_log.append(f"{player_beast[1]} uses special for {damage} damage")
            opponent_hp -= damage
            special_cooldown = 3
            
            # Check if opponent defeated
            if opponent_hp <= 0:
                opponent_hp = 0
                await battle_end(True)
                return
            
            # AI turn
            player_alive = await ai_turn()
            if not player_alive:
                await battle_end(False)
                return
                
            await update_battle(interaction)
        
        async def handle_defend(interaction):
            nonlocal player_defended, battle_log
            
            player_defended = True
            battle_log.append(f"{player_beast[1]} defends")
            
            # AI turn
            player_alive = await ai_turn()
            if not player_alive:
                await battle_end(False)
                return
                
            await update_battle(interaction)
        
        # End battle and give rewards
        async def battle_end(victory):
            for item in view.children:
                item.disabled = True
            
            embed = await update_battle()
            
            if victory:
                # Calculate rewards
                exp_gain = 10 + opponent_beast[3] * 2
                eldergem_reward = 50 + opponent_beast[3] * 5
                
                # Update database
                cursor = self.bot.conn.cursor()
                
                # Add experience and check for level up
                cursor.execute('''
                    UPDATE beasts 
                    SET experience = experience + ? 
                    WHERE beast_id = ?
                ''', (exp_gain, player_beast[0]))
                
                # Check for level up - every 100 exp
                cursor.execute('''
                    SELECT experience FROM beasts WHERE beast_id = ?
                ''', (player_beast[0],))
                new_exp = cursor.fetchone()[0]
                
                level_up = False
                new_level = player_beast[3]
                if new_exp >= new_level * 100:
                    new_level += 1
                    power_gain = random.randint(1, 3)
                    health_gain = random.randint(5, 10)
                    magic_gain = random.randint(1, 3)
                    
                    cursor.execute('''
                        UPDATE beasts 
                        SET level = ?, power = power + ?, health = health + ?, magic = magic + ? 
                        WHERE beast_id = ?
                    ''', (new_level, power_gain, health_gain, magic_gain, player_beast[0]))
                    level_up = True
                
                # Add eldergems to player
                cursor.execute('''
                    UPDATE players SET eldergems = eldergems + ? WHERE user_id = ?
                ''', (eldergem_reward, ctx.author.id))
                
                self.bot.conn.commit()
                
                # Victory message
                embed.add_field(
                    name="🏆 Victory!",
                    value=f"Rewards:\n+{exp_gain} EXP\n+{eldergem_reward}💎 Eldergems",
                    inline=False
                )
                
                if level_up:
                    embed.add_field(
                        name="🔼 Level Up!",
                        value=f"{player_beast[1]} leveled up to {new_level}!",
                        inline=False
                    )
                
            else:
                # Defeat - small consolation prize
                consolation = 10 + opponent_beast[3] * 2
                cursor = self.bot.conn.cursor()
                cursor.execute('''
                    UPDATE players SET eldergems = eldergems + ? WHERE user_id = ?
                ''', (consolation, ctx.author.id))
                self.bot.conn.commit()
                
                embed.add_field(
                    name="💀 Defeat!",
                    value=f"Consolation: +{consolation}💎 Eldergems",
                    inline=False
                )
            
            await msg.edit(embed=embed, view=view)
        
        # Connect buttons to handlers
        attack_btn.callback = handle_attack
        special_btn.callback = handle_special
        defend_btn.callback = handle_defend
        
        # Add buttons to view
        view.add_item(attack_btn)
        view.add_item(special_btn)
        view.add_item(defend_btn)
        
        # Start battle
        embed = await update_battle()
        msg = await ctx.send(embed=embed, view=view)
    
    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def train(self, ctx, beast_id: int):
        # Get beast data
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT beast_name, level, experience, element, rarity
            FROM beasts WHERE beast_id = ? AND user_id = ?
        ''', (beast_id, ctx.author.id))
        beast = cursor.fetchone()
        
        if not beast:
            return await ctx.send("❌ Beast not found!")
        
        # Check if player has enough eldergems
        player = self.core.get_player_data(ctx.author.id)
        training_cost = 20 * beast[1]  # Cost scales with beast level
        
        if player['eldergems'] < training_cost:
            return await ctx.send(f"❌ You need {training_cost}💎 Eldergems to train your beast!")
        
        # Deduct cost
        cursor.execute('UPDATE players SET eldergems = eldergems - ? WHERE user_id = ?', 
                      (training_cost, ctx.author.id))
        
        # Training animation
        embed = discord.Embed(
            title=f"🏆 Training {beast[0]}",
            description="Starting training session...",
            color=0x3498db
        )
        msg = await ctx.send(embed=embed)
        
        # Training steps
        training_steps = [
            f"{beast[0]} is warming up...",
            f"{beast[0]} is practicing {beast[3]} techniques...",
            f"{beast[0]} is building strength...",
            f"Training complete!"
        ]
        
        for step in training_steps:
            embed.description = step
            await msg.edit(embed=embed)
            await asyncio.sleep(1)
        
        # Calculate gains - based on rarity
        exp_multiplier = {
            'Common': 1.0, 'Uncommon': 1.2, 'Rare': 1.5,
            'Epic': 1.8, 'Legendary': 2.0, 'Divine': 2.5
        }[beast[4]]
        
        exp_gain = int(random.randint(10, 20) * exp_multiplier)
        
        # Update beast
        cursor.execute('''
            UPDATE beasts SET experience = experience + ? WHERE beast_id = ?
        ''', (exp_gain, beast_id))
        
        # Check for level up - every 100 exp
        new_exp = beast[2] + exp_gain
        level_up = False
        new_level = beast[1]
        
        if new_exp >= new_level * 100:
            new_level += 1
            power_gain = random.randint(1, 3)
            health_gain = random.randint(5, 10)
            magic_gain = random.randint(1, 3)
            
            cursor.execute('''
                UPDATE beasts 
                SET level = ?, power = power + ?, health = health + ?, magic = magic + ? 
                WHERE beast_id = ?
            ''', (new_level, power_gain, health_gain, magic_gain, beast_id))
            level_up = True
        
        self.bot.conn.commit()
        
        # Results
        embed = discord.Embed(
            title=f"🏆 Training Results for {beast[0]}",
            color=0x2ecc71
        )
        embed.add_field(name="Experience Gained", value=f"+{exp_gain} EXP", inline=False)
        
        if level_up:
            embed.add_field(
                name="🔼 Level Up!",
                value=f"Level {beast[1]} → {new_level}\n+{power_gain} Power\n+{health_gain} Health\n+{magic_gain} Magic",
                inline=False
            )
        else:
            exp_needed = (new_level * 100) - new_exp
            embed.add_field(
                name="Next Level",
                value=f"{exp_needed} EXP needed for level {new_level + 1}",
                inline=False
            )
        
        await msg.edit(embed=embed)

class GamblingCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.core = self.bot.get_cog('CoreCommands')
    
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def coinflip(self, ctx, bet: float, choice: str):
        # Validate input
        choice = choice.lower()
        if choice not in ['heads', 'tails']:
            return await ctx.send("❌ Please choose either 'heads' or 'tails'!")
        
        if bet < 10:
            return await ctx.send("❌ Minimum bet is 10💎 Eldergems!")
        
        # Check if player has enough eldergems
        player = self.core.get_player_data(ctx.author.id)
        if player['eldergems'] < bet:
            return await ctx.send("❌ You don't have enough Eldergems!")
        
        # Deduct bet
        cursor = self.bot.conn.cursor()
        cursor.execute('UPDATE players SET eldergems = eldergems - ? WHERE user_id = ?', 
                      (bet, ctx.author.id))
        
        # Flip animation
        embed = discord.Embed(
            title="🪙 Coin Flip",
            description="Flipping the coin...",
            color=0xf1c40f
        )
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(1.5)
        
        # Result
        result = random.choice(['heads', 'tails'])
        won = choice == result
        
        if won:
            winnings = bet * 1.9  # 1.9x payout (95% return)
            cursor.execute('UPDATE players SET eldergems = eldergems + ? WHERE user_id = ?', 
                          (winnings, ctx.author.id))
            self.bot.conn.commit()
            
            embed.description = f"**{result.upper()}!** You won {winnings:.2f}💎 Eldergems!"
            embed.color = 0x2ecc71
        else:
            self.bot.conn.commit()
            embed.description = f"**{result.upper()}!** You lost {bet:.2f}💎 Eldergems!"
            embed.color = 0xe74c3c
        
        await msg.edit(embed=embed)
    
    @commands.command(aliases=['slots'])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def slot(self, ctx, bet: float):
        # Validate input
        if bet < 20:
            return await ctx.send("❌ Minimum bet is 20💎 Eldergems!")
        
        # Check if player has enough eldergems
        player = self.core.get_player_data(ctx.author.id)
        if player['eldergems'] < bet:
            return await ctx.send("❌ You don't have enough Eldergems!")
        
        # Deduct bet
        cursor = self.bot.conn.cursor()
        cursor.execute('UPDATE players SET eldergems = eldergems - ? WHERE user_id = ?', 
                      (bet, ctx.author.id))
        
        # Slots setup
        symbols = ['💎', '🔥', '💧', '🌿', '✨', '🌑']
        
        # Initial message
        embed = discord.Embed(
            title="🎰 Mystical Slots",
            description="Spinning...",
            color=0xf1c40f
        )
        msg = await ctx.send(embed=embed)
        
        # Animation
        for _ in range(3):
            slot1 = random.choice(symbols)
            slot2 = random.choice(symbols)
            slot3 = random.choice(symbols)
            embed.description = f"[ {slot1} | {slot2} | {slot3} ]"
            await msg.edit(embed=embed)
            await asyncio.sleep(0.7)
        
        # Final result
        slot1 = random.choice(symbols)
        slot2 = random.choice(symbols)
        slot3 = random.choice(symbols)
        
        # Determine winnings
        winnings = 0
        if slot1 == slot2 == slot3:
            # Jackpot - all three match
            multiplier = 10 if slot1 == '💎' else 5
            winnings = bet * multiplier
            result_msg = f"JACKPOT! All {slot1} match!"
        elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:
            # Two matching
            winnings = bet * 2
            result_msg = "Two matching symbols!"
        else:
            result_msg = "No matches!"
        
        # Update display
        embed.description = f"[ {slot1} | {slot2} | {slot3} ]\n\n{result_msg}"
        
        if winnings > 0:
            cursor.execute('UPDATE players SET eldergems = eldergems + ? WHERE user_id = ?', 
                          (winnings, ctx.author.id))
            embed.add_field(name="Winnings", value=f"{winnings:.2f}💎 Eldergems", inline=False)
            embed.color = 0x2ecc71
        else:
            embed.add_field(name="Result", value=f"You lost {bet:.2f}💎 Eldergems", inline=False)
            embed.color = 0xe74c3c
        
        self.bot.conn.commit()
        await msg.edit(embed=embed)
    
    @commands.command()
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def elementalwheel(self, ctx, bet: float, element: str):
        # Validate input
        element = element.capitalize()
        if element not in ELEMENT_EMOJIS:
            return await ctx.send(f"❌ Please choose a valid element: {', '.join(ELEMENT_EMOJIS.keys())}")
        
        if bet < 50:
            return await ctx.send("❌ Minimum bet is 50💎 Eldergems!")
        
        # Check if player has enough eldergems
        player = self.core.get_player_data(ctx.author.id)
        if player['eldergems'] < bet:
            return await ctx.send("❌ You don't have enough Eldergems!")
        
        # Deduct bet
        cursor = self.bot.conn.cursor()
        cursor.execute('UPDATE players SET eldergems = eldergems - ? WHERE user_id = ?', 
                      (bet, ctx.author.id))
        
        # Wheel setup
        wheel_elements = list(ELEMENT_EMOJIS.keys())
        # Weight distribution (can be adjusted for different odds)
        weights = [0.18, 0.18, 0.18, 0.18, 0.14, 0.14]  # 18% each for common elements, 14% for rare
        
        # Spin animation
        embed = discord.Embed(
            title="🎡 Elemental Wheel",
            description=f"Spinning the wheel for {bet}💎 Eldergems...\nYou chose: {ELEMENT_EMOJIS[element]} {element}",
            color=0xf1c40f
        )
        msg = await ctx.send(embed=embed)
        
        # Show spinning animation
        for _ in range(3):
            spinning_display = " → ".join([ELEMENT_EMOJIS[random.choice(wheel_elements)] for _ in range(3)])
            embed.add_field(name="Spinning...", value=spinning_display, inline=False)
            await msg.edit(embed=embed)
            await asyncio.sleep(1)
            embed.clear_fields()  # Clear for next animation frame
        
        # Final result
        result_element = random.choices(wheel_elements, weights=weights, k=1)[0]
        
        # Determine winnings
        winnings = 0
        if result_element == element:
            # Direct match
            multiplier = 5
            winnings = bet * multiplier
            result_msg = f"You won! {ELEMENT_EMOJIS[element]} matches your choice!"
        else:
            result_msg = f"The wheel landed on {ELEMENT_EMOJIS[result_element]} {result_element}."
        
        # Update display
        embed = discord.Embed(
            title="🎡 Elemental Wheel Results",
            description=f"Your choice: {ELEMENT_EMOJIS[element]} {element}\nResult: {ELEMENT_EMOJIS[result_element]} {result_element}",
            color=0xf1c40f
        )
        
        if winnings > 0:
            cursor.execute('UPDATE players SET eldergems = eldergems + ? WHERE user_id = ?', 
                          (winnings, ctx.author.id))
            embed.add_field(name="Winnings", value=f"{winnings:.2f}💎 Eldergems", inline=False)
            embed.color = 0x2ecc71
        else:
            embed.add_field(name="Result", value=f"You lost {bet:.2f}💎 Eldergems", inline=False)
            embed.color = 0xe74c3c
        
        self.bot.conn.commit()
        await msg.edit(embed=embed)

class MarketCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.core = self.bot.get_cog('CoreCommands')
        self.market_items = {
            'Summoning Orb': {'price': 250, 'description': 'Summon a new beast', 'type': 'Consumable'},
            'Training Manual': {'price': 100, 'description': 'Gain 30-50 EXP for a beast', 'type': 'Consumable'},
            'Health Potion': {'price': 75, 'description': 'Increase beast health by 10-20', 'type': 'Consumable'},
            'Power Potion': {'price': 85, 'description': 'Increase beast power by 2-5', 'type': 'Consumable'},
            'Magic Potion': {'price': 85, 'description': 'Increase beast magic by 2-5', 'type': 'Consumable'},
            'Mana Crystal Pack': {'price': 200, 'description': 'Get 10 Mana Crystals', 'type': 'Consumable'},
            'Element Stone': {'price': 500, 'description': 'Change a beast\'s element', 'type': 'Consumable', 'rarity': 'Rare'},
            'Evolution Essence': {'price': 1000, 'description': 'Required for beast evolution', 'type': 'Material', 'rarity': 'Epic'}
        }
    
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def market(self, ctx):
        embed = discord.Embed(title="🛒 Mythical Market", color=0x2ecc71)
        
        for item, data in self.market_items.items():
            embed.add_field(
                name=f"{item} - {data['price']}💎",
                value=f"{data['description']}\nType: {data['type']}\nRarity: {data.get('rarity', 'Common')}",
                inline=False
            )
            
        embed.set_footer(text="Use !buy <item_name> to purchase")
        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def buy(self, ctx, *, item_name: str):
        # Check if item exists
        item_name = item_name.strip()
        item_data = None
        for name, data in self.market_items.items():
            if name.lower() == item_name.lower():
                item_name = name  # Get correct capitalization
                item_data = data
                break
                
        if not item_data:
            return await ctx.send(f"❌ Item '{item_name}' not found in the market! Use `!market` to see available items.")
        
        # Check if player has enough eldergems
        player = self.core.get_player_data(ctx.author.id)
        if player['eldergems'] < item_data['price']:
            return await ctx.send(f"❌ You need {item_data['price']}💎 Eldergems to buy this item!")
        
        # Purchase item
        cursor = self.bot.conn.cursor()
        cursor.execute('UPDATE players SET eldergems = eldergems - ? WHERE user_id = ?', 
                      (item_data['price'], ctx.author.id))
        
        # Special handling for Mana Crystal Pack
        if item_name == 'Mana Crystal Pack':
            cursor.execute('UPDATE players SET mana_crystals = mana_crystals + 10 WHERE user_id = ?', 
                         (ctx.author.id,))
            purchase_message = "Added 10 Mana Crystals to your account!"
        else:
            # Add to inventory
            cursor.execute('''
                INSERT INTO inventory (user_id, item_name, item_type, rarity)
                VALUES (?, ?, ?, ?)
            ''', (ctx.author.id, item_name, item_data['type'], item_data.get('rarity', 'Common')))
            purchase_message = f"Added {item_name} to your inventory!"
        
        self.bot.conn.commit()
        
        embed = discord.Embed(
            title="🛍️ Purchase Successful",
            description=f"You bought {item_name} for {item_data['price']}💎 Eldergems.\n{purchase_message}",
            color=0x2ecc71
        )
        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def sell(self, ctx, inventory_id: int):
        # Check if item exists in player's inventory
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT item_name, item_type, rarity, quantity 
            FROM inventory 
            WHERE inventory_id = ? AND user_id = ?
        ''', (inventory_id, ctx.author.id))
        item = cursor.fetchone()
        
        if not item:
            return await ctx.send("❌ Item not found in your inventory!")
        
        # Calculate sell price (typically 50% of buy price)
        item_name, item_type, rarity, quantity = item
        
        sell_price = 0
        # Try to find market price if it's a market item
        for name, data in self.market_items.items():
            if name == item_name:
                sell_price = data['price'] * 0.5
                break
        
        # If not found in market, base on rarity
        if sell_price == 0:
            rarity_values = {
                'Common': 25, 'Uncommon': 50, 'Rare': 100,
                'Epic': 200, 'Legendary': 500, 'Divine': 1000
            }
            sell_price = rarity_values.get(rarity, 25)
        
        # Confirm sale
        embed = discord.Embed(
            title="💰 Confirm Sale",
            description=f"Sell {quantity}x {item_name} ({rarity}) for {sell_price * quantity:.2f}💎 Eldergems?",
            color=0xf1c40f
        )
        
        # Create confirmation view with buttons
        view = CooldownView(cooldown_time=10)
        confirm_btn = Button(style=discord.ButtonStyle.green, label="Confirm", row=0)
        cancel_btn = Button(style=discord.ButtonStyle.red, label="Cancel", row=0)
        
        async def confirm_sale(interaction):
            # Remove item from inventory
            if quantity > 1:
                cursor.execute('''
                    UPDATE inventory 
                    SET quantity = quantity - 1 
                    WHERE inventory_id = ? AND user_id = ?
                ''', (inventory_id, ctx.author.id))
            else:
                cursor.execute('''
                    DELETE FROM inventory 
                    WHERE inventory_id = ? AND user_id = ?
                ''', (inventory_id, ctx.author.id))
            
            # Add eldergems
            cursor.execute('''
                UPDATE players 
                SET eldergems = eldergems + ? 
                WHERE user_id = ?
            ''', (sell_price, ctx.author.id))
            
            self.bot.conn.commit()
            
            embed.title = "💰 Item Sold"
            embed.description = f"Sold {item_name} for {sell_price:.2f}💎 Eldergems!"
            embed.color = 0x2ecc71
            
            for button in view.children:
                button.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        async def cancel_sale(interaction):
            embed.title = "❌ Sale Cancelled"
            embed.description = "You decided not to sell the item."
            embed.color = 0xe74c3c
            
            for button in view.children:
                button.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=view)
        
        confirm_btn.callback = confirm_sale
        cancel_btn.callback = cancel_sale
        
        view.add_item(confirm_btn)
        view.add_item(cancel_btn)
        
        await ctx.send(embed=embed, view=view)

class GuildCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.core = self.bot.get_cog('CoreCommands')
    
    @commands.command()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def createguild(self, ctx, *, guild_name: str):
        if len(guild_name) < 3 or len(guild_name) > 32:
            return await ctx.send("❌ Guild name must be between 3 and 32 characters!")
        
        # Check if player is already in a guild
        player = self.core.get_player_data(ctx.author.id)
        if player['guild_id'] is not None:
            return await ctx.send("❌ You're already in a guild! Leave your current guild first.")
        
        # Check if player has enough eldergems
        if player['eldergems'] < 1000:
            return await ctx.send("❌ Creating a guild costs 1000💎 Eldergems!")
        
        # Check if guild name exists
        cursor = self.bot.conn.cursor()
        cursor.execute('SELECT guild_id FROM guilds WHERE guild_name = ?', (guild_name,))
        if cursor.fetchone():
            return await ctx.send("❌ A guild with that name already exists!")
        
        # Create guild
        cursor.execute('UPDATE players SET eldergems = eldergems - 1000 WHERE user_id = ?',
                      (ctx.author.id,))
        
        cursor.execute('''
            INSERT INTO guilds (guild_name, leader_id)
            VALUES (?, ?)
        ''', (guild_name, ctx.author.id))
        guild_id = cursor.lastrowid
        
        # Update player's guild
        cursor.execute('UPDATE players SET guild_id = ? WHERE user_id = ?',
                      (guild_id, ctx.author.id))
        
        self.bot.conn.commit()
        
        embed = discord.Embed(
            title="🏰 Guild Created",
            description=f"You've founded the guild **{guild_name}**!",
            color=0x9b59b6
        )
        embed.add_field(name="Cost", value="1000💎 Eldergems", inline=False)
        embed.add_field(name="Members", value="1/10", inline=True)
        embed.add_field(name="Guild Level", value="1", inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def joinguild(self, ctx, *, guild_name: str):
        # Check if player is already in a guild
        player = self.core.get_player_data(ctx.author.id)
        if player['guild_id'] is not None:
            return await ctx.send("❌ You're already in a guild! Leave your current guild first.")
        
        # Check if guild exists
        cursor = self.bot.conn.cursor()
        cursor.execute('SELECT guild_id, members_count FROM guilds WHERE guild_name = ?', (guild_name,))
        guild = cursor.fetchone()
        
        if not guild:
            return await ctx.send("❌ Guild not found!")
        
        # Check if guild is full (max 10 members)
        if guild[1] >= 10:
            return await ctx.send("❌ This guild is full!")
