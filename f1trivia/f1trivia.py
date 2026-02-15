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
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(title="🏎️ F1 Quiz Help", color=discord.Color.red())
            embed.add_field(name=".f1quiz start", value="Start a new 30-round trivia game (first to 10 wins).", inline=False)
            embed.add_field(name=".f1quiz stop", value="Stop the current game in the channel.", inline=False)
            embed.add_field(name=".f1quiz leaderboard", value="Show the global top 10 players.", inline=False)
            embed.set_footer(text="Identify the driver! Full names or last names work.")
            await ctx.send(embed=embed)

    async def get_driver_image(self, driver_name):
        """Fetches a driver's image using Wikipedia's API for maximum reliability."""
        # Wikipedia is the most stable source for historical driver portraits
        # Use the MediaWiki Action API to get the main image of the page
        api_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "titles": driver_name,
            "prop": "pageimages",
            "format": "json",
            "pithumbsize": 800
        }
        
        headers = {
            'User-Agent': 'F1TriviaBot/1.0 (https://github.com/jaffar21/red-cogs; contact@example.com)'
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.get(api_url, params=params, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        pages = data.get("query", {}).get("pages", {})
                        for page_id in pages:
                            page = pages[page_id]
                            thumbnail = page.get("thumbnail", {}).get("source")
                            if thumbnail:
                                # Fetch the actual image data
                                async with session.get(thumbnail, timeout=10) as img_resp:
                                    if img_resp.status == 200:
                                        img_data = await img_resp.read()
                                        if len(img_data) > 1000:
                                            return discord.File(io.BytesIO(img_data), filename="driver.jpg")
            except Exception:
                pass
        
        # Fallback to a different search query if the first title fails (e.g. adding "(racing driver)")
        if "(racing driver)" not in driver_name:
            return await self.get_driver_image(f"{driver_name} (racing driver)")
            
        return None

    @f1quiz.command(name="start")
    async def f1_start(self, ctx):
        """Start a new game of F1 Trivia."""
        if ctx.channel.id in self.games:
            await ctx.send("A game is already running in this channel!")
            return

        self.games[ctx.channel.id] = {'active': True, 'scores': {}}
        game = self.games[ctx.channel.id]
        
        await ctx.send("🏎️ **Starting F1 Drivers Trivia!**\nIdentify the driver in the photo. First to 10 points or 30 rounds wins.\nYou have 15 seconds per round.")
        await asyncio.sleep(2)

        total_rounds = 30
        
        for round_num in range(1, total_rounds + 1):
            if ctx.channel.id not in self.games or not game['active']:
                break

            driver = random.choice(self.drivers)
            
            async with ctx.typing():
                image_file = None
                # Attempt to get image for this driver or a fallback
                for _ in range(5): # Increase attempts to find a driver with a photo
                    image_file = await self.get_driver_image(driver)
                    if image_file:
                        break
                    driver = random.choice(self.drivers)

            if not image_file:
                await ctx.send("❌ Could not retrieve driver images. Please check the bot's internet connection.")
                break # Stop the game if we really can't get anything

            embed = discord.Embed(title=f"Round {round_num}/{total_rounds}: Who is this F1 Driver?", color=discord.Color.red())
            embed.set_image(url="attachment://driver.jpg")
            embed.set_footer(text="Type the full name or last name in chat!")
            
            await ctx.send(file=image_file, embed=embed)

            def check(m):
                if m.channel != ctx.channel or m.author.bot:
                    return False
                
                content = m.content.lower().strip()
                driver_clean = driver.replace("(racing driver)", "").strip().lower()
                
                # Direct match
                if content == driver_clean:
                    return True
                
                # Last name match
                names = driver_clean.split()
                if len(names) > 1 and content == names[-1]:
                    return True
                
                return False

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=15.0)
                
                # Correct guess
                author_id = msg.author.id
                game['scores'][author_id] = game['scores'].get(author_id, 0) + 1
                
                # Show the clean name in victory message
                clean_name = driver.replace("(racing driver)", "").strip()
                await ctx.send(f"✅ **Correct!** It was **{clean_name}**. {msg.author.mention} now has {game['scores'][author_id]} points.")
                
                if game['scores'][author_id] >= 10:
                    await ctx.send(f"🏆 {msg.author.mention} has reached 10 points and **WINS THE GAME!**")
                    async with self.config.leaderboard() as lb:
                        lb[str(author_id)] = lb.get(str(author_id), 0) + 1
                    del self.games[ctx.channel.id]
                    return

            except asyncio.TimeoutError:
                if game['active']:
                    clean_name = driver.replace("(racing driver)", "").strip()
                    await ctx.send(f"⏰ **Time's up!** The driver was **{clean_name}**.")
            
            await asyncio.sleep(3)

        if ctx.channel.id in self.games:
            scores = game['scores']
            if scores:
                sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                winner_id, winner_score = sorted_scores[0]
                winner = ctx.guild.get_member(winner_id)
                winner_name = winner.mention if winner else f"User {winner_id}"
                await ctx.send(f"🏁 **Game Over!** Winner: {winner_name} with {winner_score} points!")
                async with self.config.leaderboard() as lb:
                    lb[str(winner_id)] = lb.get(str(winner_id), 0) + 1
            else:
                await ctx.send("🏁 **Game Over!** No points were scored.")
            
            del self.games[ctx.channel.id]

    @f1quiz.command(name="stop")
    async def f1_stop(self, ctx):
        """Stop the current game."""
        if ctx.channel.id in self.games:
            self.games[ctx.channel.id]['active'] = False
            await ctx.send("🛑 **F1 Trivia stopping...**")
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
