import discord
from redbot.core import commands, Config
import asyncio
import random
import json
import time
import aiohttp
import io
import urllib.parse
from pathlib import Path

class F1Trivia(commands.Cog):
    """F1 Drivers Trivia game with images!"""

    def __init__(self, bot):
        self.bot = bot
        self.games = {} # {channel_id: {'active': True, 'scores': {}}}
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        default_global = {
            "leaderboard": {} # {user_id: wins}
        }
        self.config.register_global(**default_global)
        
        # Load drivers
        data_path = Path(__file__).parent / "data" / "drivers.json"
        with open(data_path, "r", encoding="utf-8") as f:
            self.drivers = json.load(f)

    @commands.group(name="f1quiz")
    async def f1quiz(self, ctx):
        """F1 Trivia commands."""
        pass

    async def get_driver_image(self, driver_name):
        """Fetches a driver's image and returns a discord.File to ensure consistency."""
        # Use DuckDuckGo or direct sources if possible. 
        # For now, let's refine the query to be extremely specific.
        search_query = f"F1 driver {driver_name} racing suit portrait"
        encoded_query = urllib.parse.quote(search_query)
        
        # Swapping to a more reliable tag-based URL or a different provider if loremflickr fails
        # Trying a slightly different URL structure for loremflickr
        url = f"https://loremflickr.com/800/600/{encoded_query},racing,f1/all?random={int(time.time() * 1000)}"
        
        async with aiohttp.ClientSession() as session:
            try:
                # Add headers to look more like a browser
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                async with session.get(url, timeout=10, headers=headers) as response:
                    if response.status == 200:
                        data = await response.read()
                        # Verify data size and content type
                        if len(data) > 5000: # Increased minimum size to avoid "image not found" placeholders
                            return discord.File(io.BytesIO(data), filename="driver.jpg")
            except Exception:
                pass
        return None

    @f1quiz.command(name="start")
    async def f1_start(self, ctx):
        """Start a new game of F1 Trivia."""
        if ctx.channel.id in self.games:
            await ctx.send("A game is already running in this channel!")
            return

        self.games[ctx.channel.id] = {'active': True, 'scores': {}}
        game = self.games[ctx.channel.id]
        
        await ctx.send("Starting F1 Drivers Trivia! Identify the driver in the photo. First to 10 points or 30 rounds wins.\nYou have 15 seconds per round.")
        await asyncio.sleep(2)

        total_rounds = 30
        
        for round_num in range(1, total_rounds + 1):
            if ctx.channel.id not in self.games or not game['active']:
                break

            driver = random.choice(self.drivers)
            
            async with ctx.typing():
                # Attempt to get image up to 3 times for different drivers if one fails
                image_file = None
                for _ in range(3):
                    image_file = await self.get_driver_image(driver)
                    if image_file:
                        break
                    driver = random.choice(self.drivers)

            if not image_file:
                await ctx.send("Failed to load an image after several attempts, skipping this round...")
                continue

            embed = discord.Embed(title=f"Round {round_num}/{total_rounds}: Who is this F1 Driver?", color=discord.Color.red())
            embed.set_image(url="attachment://driver.jpg")
            embed.set_footer(text="Type the full name or just the last name in chat!")
            
            await ctx.send(file=image_file, embed=embed)

            def check(m):
                if m.channel != ctx.channel or m.author.bot:
                    return False
                
                content = m.content.lower().strip()
                driver_lower = driver.lower()
                
                # Full name match
                if content == driver_lower:
                    return True
                
                # Last name match
                names = driver_lower.split()
                if len(names) > 1 and content == names[-1]:
                    return True
                
                return False

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=15.0)
                
                # Correct guess
                author_id = msg.author.id
                game['scores'][author_id] = game['scores'].get(author_id, 0) + 1
                
                await ctx.send(f"🏁 Correct! It was **{driver}**. {msg.author.mention} now has {game['scores'][author_id]} points.")
                
                if game['scores'][author_id] >= 10:
                    await ctx.send(f"🏆 {msg.author.mention} has reached 10 points and WINS THE GAME!")
                    async with self.config.leaderboard() as lb:
                        lb[str(author_id)] = lb.get(str(author_id), 0) + 1
                    del self.games[ctx.channel.id]
                    return

            except asyncio.TimeoutError:
                if game['active']:
                    await ctx.send(f"⏰ Time's up! The driver was **{driver}**.")
            
            await asyncio.sleep(3)

        if ctx.channel.id in self.games:
            scores = game['scores']
            if scores:
                sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                winner_id, winner_score = sorted_scores[0]
                winner = ctx.guild.get_member(winner_id)
                winner_name = winner.mention if winner else f"User {winner_id}"
                await ctx.send(f"🏁 Game Over! Winner: {winner_name} with {winner_score} points!")
                async with self.config.leaderboard() as lb:
                    lb[str(winner_id)] = lb.get(str(winner_id), 0) + 1
            else:
                await ctx.send("🏁 Game Over! No points were scored.")
            
            del self.games[ctx.channel.id]

    @f1quiz.command(name="stop")
    async def f1_stop(self, ctx):
        """Stop the current game."""
        if ctx.channel.id in self.games:
            self.games[ctx.channel.id]['active'] = False
            await ctx.send("🛑 F1 Trivia stopping after this round...")
        else:
            await ctx.send("No F1 Trivia is running in this channel.")

    @f1quiz.command(name="leaderboard")
    async def f1_leaderboard(self, ctx):
        """Show the global F1 Trivia leaderboard."""
        lb = await self.config.leaderboard()
        if not lb:
            await ctx.send("The leaderboard is currently empty!")
            return

        sorted_lb = sorted(lb.items(), key=lambda x: x[1], reverse=True)[:10]
        
        embed = discord.Embed(title="🏎️ F1 Trivia Global Leaderboard", color=discord.Color.red())
        description = ""
        for i, (user_id, wins) in enumerate(sorted_lb, 1):
            user = self.bot.get_user(int(user_id))
            name = user.name if user else f"User {user_id}"
            description += f"**{i}.** {name} — {wins} wins\n"
        
        embed.description = description
        await ctx.send(embed=embed)
