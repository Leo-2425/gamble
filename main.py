import discord
from discord.ext import commands
import random
import asyncio
import sqlite3
from datetime import datetime, timedelta

class MythicalBeastArenaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        super().__init__(command_prefix='!', intents=intents)
        
        # Remove default help command
        self._help_command = self.help_command
        self.help_command = None
        
        # Initialize database connection
        self.conn = sqlite3.connect('mythical_beasts.db')
        self.setup_database()
    
    def setup_database(self):
        cursor = self.conn.cursor()
        
        # Player accounts table (currency, stats)
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
        
        # Beasts collection table
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
        
        # Items inventory table
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
        
        # Guilds table
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
        # Register all cogs/commands
        await self.add_cog(CoreCommands(self))
        await self.add_cog(BeastCommands(self))
        await self.add_cog(GamblingCommands(self))
        await self.add_cog(MarketCommands(self))
        await self.add_cog(GuildCommands(self))
        print(f'Logged in as {self.user}')


class CoreCommands(commands.Cog):
    """Core commands for the Mythical Beast Arena system"""
    
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
        
        # Predefined beast types with their elements
        self.beast_types = {
            'Fire': ['Phoenix', 'Dragon', 'Hellhound', 'Salamander', 'Ifrit'],
            'Water': ['Kraken', 'Leviathan', 'Selkie', 'Kappa', 'Hydra'],
            'Earth': ['Griffin', 'Golem', 'Manticore', 'Treant', 'Basilisk'],
            'Air': ['Pegasus', 'Thunderbird', 'Garuda', 'Sylph', 'Harpy'],
            'Dark': ['Cerberus', 'Shade', 'Nightmare', 'Banshee', 'Wraith'],
            'Light': ['Unicorn', 'Angel', 'Kirin', 'Valkyrie', 'Seraph']
        }
    
    def get_player_data(self, user_id):
        """Get player data or create new player"""
        cursor = self.bot.conn.cursor()
        cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if result is None:
            # Create new player account
            cursor.execute(
                'INSERT INTO players (user_id, eldergems, mana_crystals) VALUES (?, 1000.0, 50)',
                (user_id,)
            )
            self.bot.conn.commit()
            
            # Give new player a starter beast
            self.create_starter_beast(user_id)
            
            # Get the newly created player
            cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
        
        # Convert to dictionary
        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, result))
    
    def create_starter_beast(self, user_id):
        """Create a starter beast for new players"""
        element = random.choice(self.elements)
        beast_type = random.choice(self.beast_types[element])
        
        # Create a Common starter beast
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
    
    def update_player_currency(self, user_id, eldergems=0, mana_crystals=0):
        """Update player's currency"""
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            UPDATE players 
            SET eldergems = eldergems + ?, mana_crystals = mana_crystals + ?
            WHERE user_id = ?
        ''', (eldergems, mana_crystals, user_id))
        self.bot.conn.commit()
    
    @commands.command()
    async def profile(self, ctx):
        """View your Mythical Beast Tamer profile"""
        player = self.get_player_data(ctx.author.id)
        
        # Count total beasts
        cursor = self.bot.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM beasts WHERE user_id = ?', (ctx.author.id,))
        beast_count = cursor.fetchone()[0]
        
        # Get strongest beast
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
        
        # Get guild info if applicable
        guild_info = "None"
        if player['guild_id']:
            cursor.execute('SELECT guild_name FROM guilds WHERE guild_id = ?', (player['guild_id'],))
            guild_result = cursor.fetchone()
            if guild_result:
                guild_info = guild_result[0]
        
        embed = discord.Embed(
            title=f"🧙 {ctx.author.name}'s Beast Tamer Profile",
            color=0x9b59b6
        )
        
        embed.set_thumbnail(url=ctx.author.avatar.url if ctx.author.avatar else ctx.author.default_avatar.url)
        
        embed.add_field(name="💎 Eldergems", value=f"{player['eldergems']:.2f}", inline=True)
        embed.add_field(name="✨ Mana Crystals", value=str(player['mana_crystals']), inline=True)
        embed.add_field(name="🏅 Rank", value=player['rank'], inline=True)
        embed.add_field(name="🐉 Beasts Tamed", value=str(beast_count), inline=True)
        embed.add_field(name="⚔️ Strongest Beast", value=strongest_beast_info, inline=True)
        embed.add_field(name="🏰 Guild", value=guild_info, inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command()
    async def daily(self, ctx):
        """Claim your daily rewards"""
        player = self.get_player_data(ctx.author.id)
        
        # Check if already claimed today
        cursor = self.bot.conn.cursor()
        last_claim = player['last_daily_claim']
        
        if last_claim:
            last_claim_date = datetime.fromisoformat(last_claim)
            now = datetime.now()
            
            if (now - last_claim_date).total_seconds() < 86400:  # 24 hours in seconds
                time_left = last_claim_date + timedelta(days=1) - now
                hours, remainder = divmod(int(time_left.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                
                embed = discord.Embed(
                    title="⏳ Daily Reward Already Claimed",
                    description=f"You can claim again in {hours}h {minutes}m {seconds}s",
                    color=0xe74c3c
                )
                await ctx.send(embed=embed)
                return
        
        # Generate random rewards
        eldergems = random.randint(100, 300)
        mana_crystals = random.randint(10, 30)
        
        # Update player with rewards
        cursor.execute('''
            UPDATE players 
            SET eldergems = eldergems + ?, 
                mana_crystals = mana_crystals + ?,
                last_daily_claim = ?
            WHERE user_id = ?
        ''', (eldergems, mana_crystals, datetime.now().isoformat(), ctx.author.id))
        self.bot.conn.commit()
        
        # Sometimes give a random item
        bonus_item = ""
        if random.random() < 0.3:  # 30% chance
            item_types = ["Scroll", "Potion", "Artifact", "Charm"]
            item_name = f"{random.choice(['Ancient', 'Mystic', 'Enchanted', 'Arcane'])} {random.choice(item_types)}"
            item_rarity = self.get_random_rarity()
            
            cursor.execute('''
                INSERT INTO inventory (user_id, item_name, item_type, rarity, quantity)
                VALUES (?, ?, ?, ?, 1)
            ''', (ctx.author.id, item_name, item_types[0], item_rarity))
            self.bot.conn.commit()
            
            bonus_item = f"\n\n**Bonus Item!** You received a **{item_rarity} {item_name}**!"
        
        embed = discord.Embed(
            title="🎁 Daily Rewards Claimed!",
            description=f"You received:\n**{eldergems}** 💎 Eldergems\n**{mana_crystals}** ✨ Mana Crystals{bonus_item}",
            color=0x2ecc71
        )
        
        await ctx.send(embed=embed)
    
    def get_random_rarity(self):
        """Get a random rarity based on probability"""
        roll = random.random()
        cumulative = 0
        
        for rarity, data in self.rarities.items():
            cumulative += data['chance']
            if roll <= cumulative:
                return rarity
        
        return "Common"  # Fallback
    
    @commands.command()
    async def help(self, ctx):
        """Show available commands"""
        embed = discord.Embed(
            title="🐉 Mythical Beast Arena - Commands",
            description="Command list for Mythical Beast Arena",
            color=0x9b59b6
        )
        
        # Core commands
        embed.add_field(
            name="📋 Core Commands",
            value=(
                "`!profile` - View your Beast Tamer profile\n"
                "`!daily` - Claim daily rewards\n"
                "`!inventory` - Check your inventory"
            ),
            inline=False
        )
        
        # Beast commands
        embed.add_field(
            name="🐲 Beast Commands",
            value=(
                "`!beasts` - View your beasts collection\n"
                "`!beast <id>` - View details of a specific beast\n"
                "`!summon` - Summon a new beast (costs 300 Eldergems)\n"
                "`!rename <id> <name>` - Rename one of your beasts\n"
                "`!battle <id> <user> <id>` - Battle another player's beast\n"
                "`!train <id>` - Train your beast to gain experience"
            ),
            inline=False
        )
        
        # Gambling commands
        embed.add_field(
            name="🎲 Gambling Commands",
            value=(
                "`!coinflip <bet>` - Bet on a coin flip\n"
                "`!slot <bet>` - Play the magical slot machine\n"
                "`!elementalwheel <bet> <element>` - Bet on an elemental wheel spin"
            ),
            inline=False
        )
        
        # Market commands
        embed.add_field(
            name="💰 Market Commands",
            value=(
                "`!market` - View the mystical marketplace\n"
                "`!buy <item_id>` - Purchase an item\n"
                "`!sell <beast_id>` - Sell a beast for Eldergems\n"
                "`!trade <user> <offer> <want>` - Trade with another player"
            ),
            inline=False
        )
        
        # Guild commands
        embed.add_field(
            name="🏰 Guild Commands",
            value=(
                "`!createguild <name>` - Create a new guild (costs 5000 Eldergems)\n"
                "`!joinguild <id>` - Join an existing guild\n"
                "`!guildinfo` - View your guild's information\n"
                "`!guildcontribute <amount>` - Contribute to your guild's power"
            ),
            inline=False
        )
        
        # Alchemy commands
        embed.add_field(
            name="🧪 Alchemy Commands",
            value=(
                "`!brew <recipe>` - Brew a magical potion\n"
                "`!evolve <beast_id>` - Evolve a beast using reagents\n"
                "`!enchant <item_id> <spell>` - Enchant an item with magic"
            ),
            inline=False
        )
        
        await ctx.send(embed=embed)


class BeastCommands(commands.Cog):
    """Commands for managing mythical beasts"""
    
    def __init__(self, bot):
        self.bot = bot
        self.core = self.bot.get_cog('CoreCommands')
    
    @commands.command()
    async def beasts(self, ctx):
        """View your collection of mythical beasts"""
        player = self.core.get_player_data(ctx.author.id)
        
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT beast_id, beast_name, element, rarity, level
            FROM beasts
            WHERE user_id = ?
            ORDER BY level DESC, rarity DESC
        ''', (ctx.author.id,))
        beasts = cursor.fetchall()
        
        if not beasts:
            await ctx.send("You don't have any beasts yet! Use the `!summon` command to get your first beast.")
            return
        
        embed = discord.Embed(
            title=f"🐉 {ctx.author.name}'s Beast Collection",
            description=f"You have {len(beasts)} mythical beasts in your collection.",
            color=0x3498db
        )
        
        for beast in beasts:
            beast_id, name, element, rarity, level = beast
            
            # Get color for rarity
            rarity_color = self.core.rarities[rarity]['color']
            
            # Add element emoji
            element_emoji = {
                'Fire': '🔥', 'Water': '💧', 'Earth': '🌿', 
                'Air': '💨', 'Dark': '🌑', 'Light': '✨'
            }.get(element, '')
            
            embed.add_field(
                name=f"ID #{beast_id}: {name}",
                value=f"Level {level} {element_emoji} {element} ({rarity})",
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    @commands.command()
    async def beast(self, ctx, beast_id: int):
        """View detailed information about a specific beast"""
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT * FROM beasts WHERE beast_id = ? AND user_id = ?
        ''', (beast_id, ctx.author.id))
        beast = cursor.fetchone()
        
        if not beast:
            await ctx.send("Beast not found or doesn't belong to you.")
            return
        
        # Convert to dictionary
        columns = [column[0] for column in cursor.description]
        beast_data = dict(zip(columns, beast))
        
        # Calculate stats
        total_power = beast_data['power'] + beast_data['health'] // 10 + beast_data['magic']
        
        # Get rarity color
        rarity_color = self.core.rarities[beast_data['rarity']]['color']
        
        # Element emoji
        element_emoji = {
            'Fire': '🔥', 'Water': '💧', 'Earth': '🌿', 
            'Air': '💨', 'Dark': '🌑', 'Light': '✨'
        }.get(beast_data['element'], '')
        
        embed = discord.Embed(
            title=f"{element_emoji} {beast_data['beast_name']}",
            description=f"Level {beast_data['level']} {beast_data['beast_type']}",
            color=rarity_color
        )
        
        # Beast stats
        embed.add_field(name="Element", value=beast_data['element'], inline=True)
        embed.add_field(name="Rarity", value=beast_data['rarity'], inline=True)
        embed.add_field(name="Total Power", value=str(total_power), inline=True)
        
        embed.add_field(name="Power", value=str(beast_data['power']), inline=True)
        embed.add_field(name="Health", value=str(beast_data['health']), inline=True)
        embed.add_field(name="Magic", value=str(beast_data['magic']), inline=True)
        
        # Experience info
        exp_to_next = beast_data['level'] * 100
        exp_progress = min(100, int((beast_data['experience'] / exp_to_next) * 100))
        
        embed.add_field(
            name="Experience",
            value=f"{beast_data['experience']}/{exp_to_next} ({exp_progress}%)",
            inline=False
        )
        
        # Equipped item
        if beast_data['equipped_item']:
            embed.add_field(name="Equipped Item", value=beast_data['equipped_item'], inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.command()
    async def summon(self, ctx):
        """Summon a new mythical beast (costs 300 Eldergems)"""
        player = self.core.get_player_data(ctx.author.id)
        
        # Check if player has enough Eldergems
        if player['eldergems'] < 300:
            await ctx.send("You need 300 Eldergems to perform a summon ritual.")
            return
        
        # Deduct cost
        self.core.update_player_currency(ctx.author.id, eldergems=-300)
        
        # Create summoning animation
        embed = discord.Embed(
            title="🔮 Summoning Ritual",
            description="Preparing the ritual circle...",
            color=0x9b59b6
        )
        message = await ctx.send(embed=embed)
        
        # Animation steps
        steps = [
            "Drawing the arcane symbols...",
            "Focusing elemental energies...",
            "Chanting the ancient words...",
            "A magical presence approaches!"
        ]
        
        for step in steps:
            await asyncio.sleep(1)
            embed.description = step
            await message.edit(embed=embed)
        
        # Determine beast rarity
        rarity = self.core.get_random_rarity()
        rarity_color = self.core.rarities[rarity]['color']
        
        # Determine element
        element = random.choice(self.core.elements)
        
        # Choose beast type from that element
        beast_type = random.choice(self.core.beast_types[element])
        
        # Generate stats based on rarity
        rarity_multiplier = {
            'Common': 1,
            'Uncommon': 1.2,
            'Rare': 1.5,
            'Epic': 2,
            'Legendary': 3,
            'Divine': 5
        }[rarity]
        
        power = int(random.randint(15, 30) * rarity_multiplier)
        health = int(random.randint(80, 120) * rarity_multiplier)
        magic = int(random.randint(15, 30) * rarity_multiplier)
        
        # Add beast to database
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            INSERT INTO beasts 
            (user_id, beast_name, beast_type, element, rarity, power, health, magic)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ctx.author.id, beast_type, beast_type, element, rarity, power, health, magic))
        self.bot.conn.commit()
        
        beast_id = cursor.lastrowid
        
        # Element emoji
        element_emoji = {
            'Fire': '🔥', 'Water': '💧', 'Earth': '🌿', 
            'Air': '💨', 'Dark': '🌑', 'Light': '✨'
        }.get(element, '')
        
        # Final reveal
        embed = discord.Embed(
            title=f"{element_emoji} Summoning Complete!",
            description=f"You summoned a **{rarity}** beast!",
            color=rarity_color
        )
        
        embed.add_field(name="Beast", value=beast_type, inline=True)
        embed.add_field(name="Element", value=element, inline=True)
        embed.add_field(name="ID", value=f"#{beast_id}", inline=True)
        
        embed.add_field(name="Power", value=str(power), inline=True)
        embed.add_field(name="Health", value=str(health), inline=True)
        embed.add_field(name="Magic", value=str(magic), inline=True)
        
        await message.edit(embed=embed)
    
    @commands.command()
    async def rename(self, ctx, beast_id: int, *, new_name):
        """Rename one of your beasts"""
        # Check if name is valid
        if len(new_name) > 20:
            await ctx.send("Beast name must be 20 characters or less.")
            return
        
        # Check if beast exists and belongs to user
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT beast_id FROM beasts WHERE beast_id = ? AND user_id = ?
        ''', (beast_id, ctx.author.id))
        beast = cursor.fetchone()
        
        if not beast:
            await ctx.send("Beast not found or doesn't belong to you.")
            return
        
        # Update name
        cursor.execute('''
            UPDATE beasts SET beast_name = ? WHERE beast_id = ?
        ''', (new_name, beast_id))
        self.bot.conn.commit()
        
        await ctx.send(f"Your beast has been renamed to **{new_name}**!")
    
    @commands.command()
    async def inventory(self, ctx):
        """View your inventory of items"""
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT inventory_id, item_name, item_type, rarity, quantity
            FROM inventory
            WHERE user_id = ?
            ORDER BY rarity, item_type
        ''', (ctx.author.id,))
        items = cursor.fetchall()
        
        if not items:
            await ctx.send("Your inventory is empty. Visit the market with `!market` to purchase items.")
            return
        
        embed = discord.Embed(
            title=f"🎒 {ctx.author.name}'s Inventory",
            description=f"You have {len(items)} different items.",
            color=0xf39c12
        )
        
        for item in items:
            item_id, name, item_type, rarity, quantity = item
            
            # Get color for rarity
            rarity_color = self.core.rarities[rarity]['color']
            
            # Add item type emoji
            type_emoji = {
                'Scroll': '📜',
                'Potion': '🧪',
                'Artifact': '🏺',
                'Charm': '🔮',
                'Food': '🍖'
            }.get(item_type, '📦')
            
            embed.add_field(
                name=f"ID #{item_id}: {name}",
                value=f"{type_emoji} {item_type} | {rarity} | Qty: {quantity}",
                inline=True
            )
        
        await ctx.send(embed=embed)
    
    @commands.command()
    async def battle(self, ctx, beast_id: int, opponent: discord.Member, opponent_beast_id: int):
        """Battle your beast against another player's beast"""
        # Get player beast
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT * FROM beasts WHERE beast_id = ? AND user_id = ?
        ''', (beast_id, ctx.author.id))
        player_beast = cursor.fetchone()
        
        if not player_beast:
            await ctx.send("Beast not found or doesn't belong to you.")
            return
        
        # Get opponent beast
        cursor.execute('''
            SELECT * FROM beasts WHERE beast_id = ? AND user_id = ?
        ''', (opponent_beast_id, opponent.id))
        opponent_beast = cursor.fetchone()
        
        if not opponent_beast:
            await ctx.send(f"Beast not found or doesn't belong to {opponent.name}.")
            return
        
        # Convert to dictionaries
        columns = [column[0] for column in cursor.description]
        player_beast_data = dict(zip(columns, player_beast))
        opponent_beast_data = dict(zip(columns, opponent_beast))
        
        # Check if opponent accepts the battle
        embed = discord.Embed(
            title="⚔️ Battle Challenge",
            description=f"{ctx.author.name} challenges {opponent.name} to a beast battle!\n\n" \
                        f"{player_beast_data['beast_name']} vs {opponent_beast_data['beast_name']}",
            color=0xe74c3c
        )
        
        battle_msg = await ctx.send(embed=embed)
        await battle_msg.add_reaction('✅')  # Accept
        await battle_msg.add_reaction('❌')  # Decline
        
        def check_reaction(reaction, user):
            return (
                user == opponent and 
                str(reaction.emoji) in ['✅', '❌'] and 
                reaction.message.id == battle_msg.id
            )
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', 
                check=check_reaction, 
                timeout=60.0
            )
            
            if str(reaction.emoji) == '❌':
                embed.description = f"{opponent.name} declined the battle challenge."
                await battle_msg.edit(embed=embed)
                return
            
            # Battle accepted, start the battle
            embed.description = f"Battle accepted! {player_beast_data['beast_name']} vs {opponent_beast_data['beast_name']}"
            embed.color = 0xf1c40f
            await battle_msg.edit(embed=embed)
            
            # Element advantages
            element_advantages = {
                'Fire': 'Air',
                'Air': 'Earth',
                'Earth': 'Water',
                'Water': 'Fire',
                'Light': 'Dark',
                'Dark': 'Light'
            }
            
            # Calculate battle stats with element bonus
            player_power = player_beast_data['power'] + player_beast_data['magic']
            opponent_power = opponent_beast_data['power'] + opponent_beast_data['magic']
            
            player_health = player_beast_data['health']
            opponent_health = opponent_beast_data['health']
            
            # Apply element advantage (25% boost)
            if element_advantages.get(player_beast_data['element']) == opponent_beast_data['element']:
                player_power = int(player_power * 1.25)
                battle_log = f"{player_beast_data['beast_name']} has elemental advantage!"
            elif element_advantages.get(opponent_beast_data['element']) == player_beast_data['element']:
                opponent_power = int(opponent_power * 1.25)
                battle_log = f"{opponent_beast_data['beast_name']} has elemental advantage!"
            else:
                battle_log = "No elemental advantage for either beast."
            
            # Battle animation
            embed = discord.Embed(
                title="⚔️ Beast Battle",
                description=f"{battle_log}\n\n{player_beast_data['beast_name']} HP: {player_health}\n{opponent_beast_data['beast_name']} HP: {opponent_health}",
                color=0xf1c40f
            )
            await battle_msg.edit(embed=embed)
            
            # Battle simulation
            round_num = 1
            attacker = "player" if random.random() < 0.5 else "opponent"
            
            while player_health > 0 and opponent_health > 0:
                await asyncio.sleep(2)  # Delay between rounds
                
                # Determine damage
                if attacker == "player":
                    # Player attacks
                    damage = max(5, int(player_power * random.uniform(0.8, 1.2)))
                    crit = random.random() < 0.1  # 10% crit chance
                    
                    if crit:
                        damage = int(damage * 1.5)
                        attack_text = f"**CRITICAL HIT!** {player_beast_data['beast_name']} deals {damage} damage!"
                    else:
                        attack_text = f"{player_beast_data['beast_name']} attacks for {damage} damage!"
                    
                    opponent_health -= damage
                    attacker = "opponent"  # Switch attacker
                else:
                    # Opponent attacks
                    damage = max(5, int(opponent_power * random.uniform(0.8, 1.2)))
                    crit = random.random() < 0.1  # 10% crit chance
                    
                    if crit:
                        damage = int(damage * 1.5)
                        attack_text = f"**CRITICAL HIT!** {opponent_beast_data['beast_name']} deals {damage} damage!"
                    else:
                        attack_text = f"{opponent_beast_data['beast_name']} attacks for {damage} damage!"
                    
                    player_health -= damage
                    attacker = "player"  # Switch attacker
                
                # Ensure health doesn't go below 0
                player_health = max(0, player_health)
                opponent_health = max(0, opponent_health)
                
                embed = discord.Embed(
                    title=f"⚔️ Beast Battle - Round {round_num}",
                    description=f"{attack_text}\n\n{player_beast_data['beast_name']} HP: {player_health}\n{opponent_beast_data['beast_name']} HP: {opponent_health}",
                    color=0xf1c40f
                )
                await battle_msg.edit(embed=embed)
                round_num += 1
            
            # Battle results
            winner = ctx.author if player_health > 0 else opponent
            winner_beast = player_beast_data if player_health > 0 else opponent_beast_data
            loser = opponent if player_health > 0 else ctx.author
            loser_beast = opponent_beast_data if player_health > 0 else player_beast_data
            
            # Award XP and Eldergems to winner
            if winner == ctx.author:
                xp_gain = random.randint(15, 30)
                gems_gain = random.randint(50, 100)
                
                cursor.execute('''
                    UPDATE beasts 
                    SET experience = experience + ? 
                    WHERE beast_id = ?
                ''', (xp_gain, beast_id))
                
                self.core.update_player_currency(ctx.author.id, eldergems=gems_gain)
            else:
                xp_gain = random.randint(15, 30)
                gems_gain = random.randint(50, 100)
                
                cursor.execute('''
                    UPDATE beasts 
                    SET experience = experience + ? 
                    WHERE beast_id = ?
                ''', (xp_gain, opponent_beast_id))
                
                self.core.update_player_currency(opponent.id, eldergems=gems_gain)
            
            self.bot.conn.commit()
            
            # Check if beast leveled up
            if winner == ctx.author:
                cursor.execute('''
                    SELECT level, experience FROM beasts WHERE beast_id = ?
                ''', (beast_id,))
            else:
                cursor.execute('''
                    SELECT level, experience FROM beasts WHERE beast_id = ?
                ''', (opponent_beast_id,))
            
            beast_stats = cursor.fetchone()
            current_level = beast_stats[0]
            current_exp = beast_stats[1]
            exp_needed = current_level * 100
            
            level_up_text = ""
            if current_exp >= exp_needed:
                # Level up the beast
                new_level = current_level + 1
                
                # Stat improvements
                power_gain = random.randint(3, 6)
                health_gain = random.randint(10, 20)
                magic_gain = random.randint(3, 6)
                
                if winner == ctx.author:
                    cursor.execute('''
                        UPDATE beasts 
                        SET level = ?, experience = ?,
                            power = power + ?, health = health + ?, magic = magic + ?
                        WHERE beast_id = ?
                    ''', (new_level, current_exp - exp_needed, power_gain, health_gain, magic_gain, beast_id))
                else:
                    cursor.execute('''
                        UPDATE beasts 
                        SET level = ?, experience = ?,
                            power = power + ?, health = health + ?, magic = magic + ?
                        WHERE beast_id = ?
                    ''', (new_level, current_exp - exp_needed, power_gain, health_gain, magic_gain, opponent_beast_id))
                
                self.bot.conn.commit()
                
                level_up_text = f"\n🎉 **{winner_beast['beast_name']} leveled up to level {new_level}!**"
                level_up_text += f"\nStats increased: Power +{power_gain}, Health +{health_gain}, Magic +{magic_gain}"
            
            embed = discord.Embed(
                title="🏆 Battle Results",
                description=f"**{winner_beast['beast_name']}** is victorious!\n\n{winner.name} wins {gems_gain} Eldergems and {winner_beast['beast_name']} gains {xp_gain} XP!{level_up_text}",
                color=0x2ecc71
            )
            await battle_msg.edit(embed=embed)
            
        except asyncio.TimeoutError:
            embed.description = "Battle challenge timed out."
            embed.color = 0x95a5a6
            await battle_msg.edit(embed=embed)
    
    @commands.command()
    async def train(self, ctx, beast_id: int):
        """Train your beast to gain experience and stats"""
        # Check if beast exists and belongs to user
        cursor = self.bot.conn.cursor()
        cursor.execute('''
            SELECT beast_name, level, experience FROM beasts 
            WHERE beast_id = ? AND user_id = ?
        ''', (beast_id, ctx.author.id))
        beast = cursor.fetchone()
        
        if not beast:
            await ctx.send("Beast not found or doesn't belong to you.")
            return
        
        beast_name, current_level, current_exp = beast
        
        # Check if player has training energy (mana crystals)
        player = self.core.get_player_data(ctx.author.id)
        if player['mana_crystals'] < 5:
            await ctx.send("You need 5 Mana Crystals to train your beast.")
            return
        
        # Deduct mana crystals
        self.core.update_player_currency(ctx.author.id, mana_crystals=-5)
        
        # Training animation
        training_types = [
            "physical endurance", "elemental control", 
            "magical focus", "combat technique", 
            "defensive maneuvers"
        ]
        training_type = random.choice(training_types)
        
        embed = discord.Embed(
            title=f"🏋️ Training {beast_name}",
            description=f"Training session focused on {training_type}...",
            color=0x3498db
        )
        message = await ctx.send(embed=embed)
        
        # Training progress
        progress_steps = ["🔄 Warming up...", "⚡ Increasing intensity...", "💪 Pushing limits..."]
        for step in progress_steps:
            await asyncio.sleep(1)
            embed.description = step
            await message.edit(embed=embed)
        
        # Calculate gains
        exp_gain = random.randint(15, 30)
        stat_type = random.choice(["power", "health", "magic"])
        stat_gain = random.randint(1, 3)
        
        # Apply gains
        cursor.execute('''
            UPDATE beasts
            SET experience = experience + ?,
                {} = {} + ?
            WHERE beast_id = ?
        '''.format(stat_type, stat_type), (exp_gain, stat_gain, beast_id))
        
        # Check if beast leveled up
        current_exp += exp_gain
        exp_needed = current_level * 100
        
        level_up_text = ""
        if current_exp >= exp_needed:
            # Level up the beast
            new_level = current_level + 1
            
            # Stat improvements
            power_gain = random.randint(3, 6)
            health_gain = random.randint(10, 20)
            magic_gain = random.randint(3, 6)
            
            cursor.execute('''
                UPDATE beasts 
                SET level = ?, experience = ?,
                    power = power + ?, health = health + ?, magic = magic + ?
                WHERE beast_id = ?
            ''', (new_level, current_exp - exp_needed, power_gain, health_gain, magic_gain, beast_id))
            
            level_up_text = f"\n🎉 **{beast_name} leveled up to level {new_level}!**"
            level_up_text += f"\nStats increased: Power +{power_gain}, Health +{health_gain}, Magic +{magic_gain}"
        
        self.bot.conn.commit()
        
        # Format stat type name for display
        stat_display = stat_type.capitalize()
        if stat_type == "health":
            stat_gain *= 3  # Health gains are larger
        
        # Final result
        embed = discord.Embed(
            title=f"🏆 Training Complete!",
            description=f"**{beast_name}** gained {exp_gain} experience and +{stat_gain} {stat_display}!{level_up_text}",
            color=0x2ecc71
        )
        
        # Show progress to next level if no level up
        if not level_up_text:
            progress = min(100, int((current_exp / exp_needed) * 100))
            embed.add_field(
                name="Experience Progress", 
                value=f"{current_exp}/{exp_needed} ({progress}%)",
                inline=False
            )
        
        await message.edit(embed=embed)


class GamblingCommands(commands.Cog):
    """Gambling and entertainment commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.core = self.bot.get_cog('CoreCommands')
    
    @commands.command()
    async def coinflip(self, ctx, bet: float):
        """Bet on a coin flip (heads or tails)"""
        player = self.core.get_player_data(ctx.author.id)
        
        # Validate bet
        if bet <= 0:
            await ctx.send("Your bet must be greater than 0 Eldergems.")
            return
        
        if bet > player['eldergems']:
            await ctx.send(f"You don't have enough Eldergems. Your balance: {player['eldergems']:.2f}")
            return
        
        # Coin flip animation
        embed = discord.Embed(
            title="🪙 Magical Coin Flip",
            description=f"Betting {bet:.2f} Eldergems...\nFlipping the coin...",
            color=0xf1c40f
        )
        message = await ctx.send(embed=embed)
        
        # Ask player to choose heads or tails
        await message.add_reaction('🧠')  # Heads
        await message.add_reaction('🦅')  # Tails
        
        embed.description = f"Betting {bet:.2f} Eldergems...\nChoose: 🧠 (Heads) or 🦅 (Tails)"
        await message.edit(embed=embed)
        
        def check_reaction(reaction, user):
            return (
                user == ctx.author and 
                str(reaction.emoji) in ['🧠', '🦅'] and 
                reaction.message.id == message.id
            )
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', 
                check=check_reaction, 
                timeout=30.0
            )
            
            player_choice = "Heads" if str(reaction.emoji) == '🧠' else "Tails"
            
            # Animation
            embed.description = f"Betting {bet:.2f} Eldergems on {player_choice}...\nThe coin spins in the air..."
            await message.edit(embed=embed)
            await asyncio.sleep(2)
            
            # Result
            result = "Heads" if random.random() < 0.5 else "Tails"
            
            if result == player_choice:
                # Win (1.8x bet)
                winnings = bet * 1.8
                self.core.update_player_currency(ctx.author.id, eldergems=winnings-bet)
                
                embed = discord.Embed(
                    title="🎉 You Won!",
                    description=f"The coin landed on **{result}**!\nYou win {winnings:.2f} Eldergems!",
                    color=0x2ecc71
                )
            else:
                # Loss
                self.core.update_player_currency(ctx.author.id, eldergems=-bet)
                
                embed = discord.Embed(
                    title="😢 You Lost",
                    description=f"The coin landed on **{result}**!\nYou lose {bet:.2f} Eldergems.",
                    color=0xe74c3c
                )
            
            # Show updated balance
            updated_player = self.core.get_player_data(ctx.author.id)
            embed.set_footer(text=f"Balance: {updated_player['eldergems']:.2f} Eldergems")
            
            await message.edit(embed=embed)
            
        except asyncio.TimeoutError:
            embed.description = "Bet canceled - you didn't make a choice in time."
            embed.color = 0x95a5a6
            await message.edit(embed=embed)
    
    @commands.command()
    async def slot(self, ctx, bet: float):
        """Play the magical slot machine"""
        player = self.core.get_player_data(ctx.author.id)
        
        # Validate bet
        if bet <= 0:
            await ctx.send("Your bet must be greater than 0 Eldergems.")
            return
        
        if bet > player['eldergems']:
            await ctx.send(f"You don't have enough Eldergems. Your balance: {player['eldergems']:.2f}")
            return
        
        # Deduct bet
        self.core.update_player_currency(ctx.author.id, eldergems=-bet)
        
        # Slot symbols
        symbols = ['🔥', '💧', '🌿', '💨', '🌑', '✨', '🐉', '🪄', '💎']
        
        # Multipliers for winning combinations
        multipliers = {
            3: {  # Three of a kind
                '🔥': 2.5, '💧': 2.5, '🌿': 2.5, '💨': 2.5, '🌑': 2.5, '✨': 2.5,
                '🐉': 5.0, '🪄': 10.0, '💎': 25.0
            },
            2: {  # Two of a kind
                '🐉': 1.5, '🪄': 2.0, '💎': 3.0
            }
        }
        
        # Slot animation
        embed = discord.Embed(
            title="🎰 Magical Slot Machine",
            description=f"Betting {bet:.2f} Eldergems...\nSpinning the reels...",
            color=0xf1c40f
        )
        message = await ctx.send(embed=embed)
        
        # Animation
        for _ in range(3):
            random_symbols = [random.choice(symbols) for _ in range(3)]
            embed.description = f"Betting {bet:.2f} Eldergems...\n[ {random_symbols[0]} | {random_symbols[1]} | {random_symbols[2]} ]"
            await message.edit(embed=embed)
            await asyncio.sleep(0.7)
        
        # Final result
        result = [random.choice(symbols) for _ in range(3)]
        
        # Check for wins
        symbol_counts = {}
        for symbol in result:
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        
        win_amount = 0
        win_description = ""
        
        for symbol, count in symbol_counts.items():
            if count == 3 and symbol in multipliers[3]:
                win_amount = bet * multipliers[3][symbol]
                win_description = f"Triple {symbol}! ({multipliers[3][symbol]}x)"
                break
            elif count == 2 and symbol in multipliers[2]:
                win_amount = bet * multipliers[2][symbol]
                win_description = f"Double {symbol}! ({multipliers[2][symbol]}x)"
                break
        
        # Special case: three different elements
        element_symbols = ['🔥', '💧', '🌿', '💨', '🌑', '✨']
        if all(s in element_symbols for s in result) and len(set(result)) == 3:
            win_amount = bet * 4.0
            win_description = "Elemental Harmony! (4.0x)"
        
        # Apply winnings
        if win_amount > 0:
            self.core.update_player_currency(ctx.author.id, eldergems=win_amount)
            
            embed = discord.Embed(
                title="🎉 You Won!",
                description=f"[ {result[0]} | {result[1]} | {result[2]} ]\n\n{win_description}\nYou win {win_amount:.2f} Eldergems!",
                color=0x2ecc71
            )
        else:
            embed = discord.Embed(
                title="😢 No Match",
                description=f"[ {result[0]} | {result[1]} | {result[2]} ]\n\nBetter luck next time!\nYou lose {bet:.2f} Eldergems.",
                color=0xe74c3c
            )
        
        # Show updated balance
        updated_player = self.core.get_player_data(ctx.author.id)
        embed.set_footer(text=f"Balance: {updated_player['eldergems']:.2f} Eldergems")
        
        await message.edit(embed=embed)
    
    @commands.command()
    async def elementalwheel(self, ctx, bet: float, element: str):
        """Bet on an elemental wheel spin"""
        player = self.core.get_player_data(ctx.author.id)
        
        # Validate bet
        if bet <= 0:
            await ctx.send("Your bet must be greater than 0 Eldergems.")
            return
        
        if bet > player['eldergems']:
            await ctx.send(f"You don't have enough Eldergems. Your balance: {player['eldergems']:.2f}")
            return
        
        # Validate element
        elements = {
            'fire': ('Fire', '🔥'),
            'water': ('Water', '💧'),
            'earth': ('Earth', '🌿'),
            'air': ('Air', '💨'),
            'dark': ('Dark', '🌑'),
            'light': ('Light', '✨')
        }
        
        element = element.lower()
        if element not in elements:
            await ctx.send(f"Invalid element. Choose from: {', '.join(elements.keys())}")
            return
        
        chosen_element, chosen_emoji = elements[element]
        
        # Deduct bet
        self.core.update_player_currency(ctx.author.id, eldergems=-bet)
        
        # Wheel spin animation
        embed = discord.Embed(
            title="🎡 Elemental Wheel of Fortune",
            description=f"Betting {bet:.2f} Eldergems on {chosen_emoji} {chosen_element}...\nSpinning the wheel...",
            color=0xf1c40f
        )
        message = await ctx.send(embed=embed)
        
        # Animation
        element_list = list(elements.values())
        for _ in range(5):
            random_element = random.choice(element_list)
            embed.description = f"Betting {bet:.2f} Eldergems on {chosen_emoji} {chosen_element}...\nWheel spins... {random_element[1]}"
            await message.edit(embed=embed)
            await asyncio.sleep(0.8)
        
        # Final result
        result = random.choices(
            element_list,
            weights=[16, 16, 16, 16, 16, 20],  # Light has slightly higher chance
            k=1
        )[0]
        
        result_name, result_emoji = result
        
        # Determine winnings
        if result_name == chosen_element:
            # Win (5x bet)
            winnings = bet * 5.0
            self.core.update_player_currency(ctx.author.id, eldergems=winnings)
            
            embed = discord.Embed(
                title="🎉 You Won!",
                description=f"The wheel stopped at {result_emoji} **{result_name}**!\nYou win {winnings:.2f} Eldergems!",
                color=0x2ecc71
            )
        else:
            embed = discord.Embed(
                title="😢 You Lost",
                description=f"The wheel stopped at {result_emoji} **{result_name}**!\nYou lose {bet:.2f} Eldergems.",
                color=0xe74c3c
            )
        
        # Show updated balance
        updated_player = self.core.get_player_data(ctx.author.id)
        embed.set_footer(text=f"Balance: {updated_player['eldergems']:.2f} Eldergems")
        
        await message.edit(embed=embed)


class MarketCommands(commands.Cog):
    """Market and trading commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.core = self.bot.get_cog('CoreCommands')
    
    @commands.command()
    async def market(self, ctx):
        """Browse the mystical marketplace"""
        # Generate random market items
        market_items = [
            {
                'id': 1,
                'name': 'Summon Scroll',
                'description': 'Summons a new mythical beast',
                'price': 300,
                'currency': 'Eldergems',
                'emoji': '📜'
            },
            {
                'id': 2,
                'name': 'Healing Potion',
                'description': 'Restores 50 health to a beast',
                'price': 75,
                'currency': 'Eldergems',
                'emoji': '🧪'
            },
            {
                'id': 3,
                'name': 'Power Crystal',
                'description': 'Permanently increases beast power by 5',
                'price': 500,
                'currency': 'Eldergems',
                'emoji': '💎'
            },
            {
                'id': 4,
                'name': 'Mystic Charm',
                'description': 'Permanently increases beast magic by 5',
                'price': 500,
                'currency': 'Eldergems',
                'emoji': '🔮'
            },
            {
                'id': 5,
                'name': 'Dragonfruit',
                'description': 'Special beast food - grants 30 experience',
                'price': 50,
                'currency': 'Eldergems',
                'emoji': '🍎'
            },
            {
                'id': 6,
                'name': 'Rare Candy',
                'description': 'Instantly levels up a beast once',
                'price': 30,
                'currency': 'Mana Crystals',
                'emoji': '🍬'
            },
            {
                'id': 7,
                'name': 'Element Stone',
                'description': 'Can change a beast\'s elemental affinity',
                'price': 100,
                'currency': 'Mana Crystals',
                'emoji': '🌀'
            }
        ]
        
        embed = discord.Embed(
            title="🛒 Mystical Marketplace",
            description="Welcome to the Marketplace, where magical treasures await!",
            color=0xf39c12
        )
        
        for item in market_items:
            embed.add_field(
                name=f"{item['emoji']} {item['name']} (ID: {item['id']})",
                value=f"{item['description']}\nPrice: {item['price']} {item['currency']}",
                inline=False
            )
        
        embed.set_footer(text="Use !buy <id> to purchase an item")
        await ctx.send(embed=embed)
    
    @commands.command()
    async def buy(self, ctx, item_id: int):
        """Purchase an item from the marketplace"""
        # Market items (same as in market command)
        market_items = [
            {
                'id': 1,
                'name': 'Summon Scroll',
                'description': 'Summons a new mythical beast',
                'price': 300,
                'currency': 'Eldergems',
                'emoji': '📜',
                'item_type': 'Scroll',
                'rarity': 'Common'
            },
            {
                'id': 2,
                'name': 'Healing Potion',
                'description': 'Restores 50 health to a beast',
                'price': 75,
                'currency': 'Eldergems',
                'emoji': '🧪',
                'item_type': 'Potion',
                'rarity': 'Common'
            },
            {
                'id': 3,
                'name': 'Power Crystal',
                'description': 'Permanently increases beast power by 5',
                'price': 500,
                'currency': 'Eldergems',
                'emoji': '💎',
                'item_type': 'Artifact',
                'rarity': 'Rare'
            },
            {
                'id': 4,
                'name': 'Mystic Charm',
                'description': 'Permanently increases beast magic by 5',
                'price': 500,
                'currency': 'Eldergems',
                'emoji': '🔮',
                'item_type': 'Charm',
                'rarity': 'Rare'
            },
            {
                'id': 5,
                'name': 'Dragonfruit',
                'description': 'Special beast food - grants 30 experience',
                'price': 50,
                'currency': 'Eldergems',
                'emoji': '🍎',
                'item_type': 'Food',
                'rarity': 'Common'
            },
            {
                'id': 6,
                'name': 'Rare Candy',
                'description': 'Instantly levels up a beast once',
                'price': 30,
                'currency': 'Mana Crystals',
                'emoji': '🍬',
                'item_type': 'Food',
                'rarity': 'Uncommon'
            },
            {
                'id': 7,
                'name': 'Element Stone',
                'description': 'Can change a beast\'s elemental affinity',
                'price': 100,
                'currency': 'Mana Crystals',
                'emoji': '🌀',
                'item_type': 'Artifact',
                'rarity': 'Epic'
            }
        ]
        
        # Find the item
        item = next((i for i in market_items if i['id'] == item_id), None)
        if not item:
            await ctx.send("Invalid item ID. Use `!market` to view available items.")
            return
        
        # Check if player has enough currency
        player = self.core.get_player_data(ctx.author.id)
        
        if item['currency'] == 'Eldergems' and player['eldergems'] < item['price']:
            await ctx.send(f"You don't have enough Eldergems. Your balance: {player['eldergems']:.2f}")
            return
        
        if item['currency'] == 'Mana Crystals' and player['mana_crystals'] < item['price']:
            await ctx.send(f"You don't have enough Mana Crystals. Your balance: {player['mana_crystals']}")
            return
        
        # Process purchase
        if item['currency'] == 'Eldergems':
            self.core.update_player_currency(ctx.author.id, eldergems=-item['price'])
        else:  # Mana Crystals
            self.core.update_player_currency(ctx.author.id, mana_crystals=-item['price'])
        
        # Special handling for Summon Scroll (immediate summon)
        if item['id'] == 1:
            await ctx.send(f"You purchased a Summon Scroll! Using it immediately...")
            
            # Forward to summon command
            beast_command = self.bot.get_command('summon')
            await ctx.invoke(beast_command)
            return
        
        # Add item to inventory for other items
        cursor = self.bot.conn.cursor()
        
        # Check if player already has this item
        cursor.execute('''
            SELECT inventory_id, quantity FROM inventory
            WHERE user_id = ? AND item_name = ?
        ''', (ctx.author.id, item['name']))
        existing_item = cursor.fetchone()
        
        if existing_item:
            # Update quantity
            cursor.execute('''
                UPDATE inventory
                SET quantity = quantity + 1
                WHERE inventory_id = ?
            ''', (existing_item[0],))
        else:
            # Add new item
            cursor.execute('''
                INSERT INTO inventory
                (user_id, item_name, item_type, rarity, quantity)
                VALUES (?, ?, ?, ?, 1)
            ''', (ctx.author.id, item['name'], item['item_type'],
