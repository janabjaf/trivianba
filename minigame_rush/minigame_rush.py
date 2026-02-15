import discord
import asyncio
import random
import time
from redbot.core import commands

class MinigameRush(commands.Cog):
    """
    MinigameRush: Fast-paced competitive minigames.
    """

    def __init__(self, bot):
        self.bot = bot
        self.active_games = set()

    @commands.command()
    async def mg(self, ctx):
        """Start a random high-speed minigame!"""
        if ctx.channel.id in self.active_games:
            return await ctx.send("Wait for the current game to finish!")

        self.active_games.add(ctx.channel.id)
        
        games = [
            self.reaction_speed,
            self.math_rush,
            self.repeat_phrase,
            self.scramble_word,
            self.click_emoji,
            self.color_match,
            self.count_emojis,
            self.trivia_quick,
            self.reverse_phrase,
            self.memory_blink
        ]
        
        game = random.choice(games)
        try:
            await game(ctx)
        finally:
            self.active_games.remove(ctx.channel.id)

    async def reaction_speed(self, ctx):
        embed = discord.Embed(title="⚡ Reaction Speed", description="Wait for it...", color=discord.Color.yellow())
        msg = await ctx.send(embed=embed)
        await asyncio.sleep(random.uniform(2, 5))
        
        embed.description = "**CLICK NOW!** (Type `GO`!)"
        embed.color = discord.Color.green()
        await msg.edit(embed=embed)
        
        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content.lower() == "go"

        try:
            winner = await self.bot.wait_for("message", check=check, timeout=10)
            await ctx.send(f"🏆 {winner.author.mention} was the fastest!")
        except asyncio.TimeoutError:
            await ctx.send("Too slow! No one reacted.")

    async def math_rush(self, ctx):
        a, b = random.randint(10, 50), random.randint(10, 50)
        op = random.choice(['+', '-', '*'])
        if op == '*': a, b = random.randint(2, 12), random.randint(2, 12)
        
        answer = eval(f"{a} {op} {b}")
        embed = discord.Embed(title="🧮 Math Rush", description=f"Quick! What is **{a} {op} {b}**?", color=discord.Color.blue())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content == str(answer)

        try:
            winner = await self.bot.wait_for("message", check=check, timeout=15)
            await ctx.send(f"🏆 {winner.author.mention} got it right first!")
        except asyncio.TimeoutError:
            await ctx.send(f"Times up! The answer was {answer}.")

    async def repeat_phrase(self, ctx):
        phrases = ["Fastest finger first!", "Basketball is life", "Full court press", "Three point shot", "SLAM DUNK", "Alley-oop!"]
        phrase = random.choice(phrases)
        embed = discord.Embed(title="✍️ Type Fast!", description=f"Repeat this: **{phrase}**", color=discord.Color.purple())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content == phrase

        try:
            winner = await self.bot.wait_for("message", check=check, timeout=15)
            await ctx.send(f"🏆 {winner.author.mention} typed it first!")
        except asyncio.TimeoutError:
            await ctx.send("Too slow!")

    async def scramble_word(self, ctx):
        words = ["BASKETBALL", "COURT", "DRIBBLE", "WHISTLE", "JERSEY", "STADIUM", "REFREE", "TROPHY"]
        word = random.choice(words)
        scrambled = "".join(random.sample(word, len(word)))
        
        embed = discord.Embed(title="🧩 Unscramble!", description=f"Unscramble: **{scrambled}**", color=discord.Color.orange())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content.upper() == word

        try:
            winner = await self.bot.wait_for("message", check=check, timeout=15)
            await ctx.send(f"🏆 {winner.author.mention} solved it! The word was **{word}**.")
        except asyncio.TimeoutError:
            await ctx.send(f"Times up! The word was {word}.")

    async def click_emoji(self, ctx):
        emojis = ["🏀", "⚽", "🏈", "⚾", "🎾", "🏐", "🏉", "🎱"]
        target = random.choice(emojis)
        embed = discord.Embed(title="🎯 Emoji Hunt", description=f"Type the emoji: **{target}**", color=discord.Color.red())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content == target

        try:
            winner = await self.bot.wait_for("message", check=check, timeout=10)
            await ctx.send(f"🏆 {winner.author.mention} caught it!")
        except asyncio.TimeoutError:
            await ctx.send("No one found it.")

    async def color_match(self, ctx):
        colors = {"🔴": "RED", "🔵": "BLUE", "🟢": "GREEN", "🟡": "YELLOW", "⚪": "WHITE"}
        emoji, name = random.choice(list(colors.items()))
        
        embed = discord.Embed(title="🎨 Color Match", description=f"What color is this: {emoji}?", color=discord.Color.dark_grey())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content.upper() == name

        try:
            winner = await self.bot.wait_for("message", check=check, timeout=10)
            await ctx.send(f"🏆 {winner.author.mention} knows their colors!")
        except asyncio.TimeoutError:
            await ctx.send(f"Times up! It was {name}.")

    async def count_emojis(self, ctx):
        count = random.randint(5, 12)
        emoji = "🏀"
        display = emoji * count
        
        embed = discord.Embed(title="🔢 Count 'Em!", description=f"How many balls are there?\n\n{display}", color=discord.Color.dark_orange())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content == str(count)

        try:
            winner = await self.bot.wait_for("message", check=check, timeout=15)
            await ctx.send(f"🏆 {winner.author.mention} counted {count} correctly!")
        except asyncio.TimeoutError:
            await ctx.send(f"Times up! There were {count}.")

    async def trivia_quick(self, ctx):
        questions = [
            ("How many players are on the court per team in NBA?", "5"),
            ("Which team does LeBron James play for currently?", "Lakers"),
            ("What is the highest points scored in a single game by Wilt Chamberlain?", "100"),
            ("How many quarters are in an NBA game?", "4")
        ]
        q, a = random.choice(questions)
        
        embed = discord.Embed(title="💡 Quick Trivia", description=q, color=discord.Color.gold())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and (a.lower() in m.content.lower())

        try:
            winner = await self.bot.wait_for("message", check=check, timeout=15)
            await ctx.send(f"🏆 {winner.author.mention} is a pro! Answer: **{a}**")
        except asyncio.TimeoutError:
            await ctx.send(f"No one knew? It was {a}.")

    async def reverse_phrase(self, ctx):
        word = random.choice(["DUNK", "STADIUM", "PLAYOFF", "LEAGUE", "CHAMPION"])
        rev = word[::-1]
        
        embed = discord.Embed(title="🔃 Reverse It!", description=f"Type **{word}** BACKWARDS!", color=discord.Color.teal())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content.upper() == rev

        try:
            winner = await self.bot.wait_for("message", check=check, timeout=15)
            await ctx.send(f"🏆 {winner.author.mention} reversed it! **{rev}**")
        except asyncio.TimeoutError:
            await ctx.send(f"Too hard? It was {rev}.")

    async def memory_blink(self, ctx):
        num = random.randint(10000, 99999)
        msg = await ctx.send(f"🧠 **Remember this:** `{num}`")
        await asyncio.sleep(2)
        await msg.edit(content="🧠 **What was the number?**")

        def check(m):
            return m.channel == ctx.channel and not m.author.bot and m.content == str(num)

        try:
            winner = await self.bot.wait_for("message", check=check, timeout=10)
            await ctx.send(f"🏆 {winner.author.mention} has a perfect memory!")
        except asyncio.TimeoutError:
            await ctx.send(f"Times up! It was {num}.")
