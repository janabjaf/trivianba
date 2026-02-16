import discord
from redbot.core import commands, Config
import asyncio
import random
import json
import aiohttp
import io
from pathlib import Path

class F1Trivia(commands.Cog):
    """F1 Drivers Trivia game with ultra-reliable image fetching."""

    def __init__(self, bot):
        self.bot = bot
        self.games = {} # {channel_id: {'active': True, 'scores': {}}}
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        default_global = {
            "leaderboard": {} # {user_id: wins}
        }
        self.config.register_global(**default_global)
        
        # Load drivers (filtered list of easily findable drivers)
        data_path = Path(__file__).parent / "data" / "drivers.json"
        with open(data_path, "r", encoding="utf-8") as f:
            self.drivers_list = json.load(f)

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
        """Fetches a driver's image using Wikipedia's API with extreme reliability."""
        api_url = "https://en.wikipedia.org/w/api.php"
        headers = {'User-Agent': 'F1TriviaBot/1.4 (contact@example.com)'}
        
        async with aiohttp.ClientSession(headers=headers) as session:
            # Clean and prepare search terms
            clean_name = driver_name.replace("(racing driver)", "").strip()
            search_queries = [
                f"{clean_name} (racing driver)",
                f"{clean_name} (Formula One driver)",
                f"{clean_name} F1 driver",
                clean_name
            ]
            
            for query in search_queries:
                try:
                    # Search specifically for pages with images
                    search_params = {
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "format": "json",
                        "srlimit": 1
                    }
                    async with session.get(api_url, params=search_params, timeout=5) as resp:
                        if resp.status != 200: continue
                        search_data = await resp.json()
                        search_results = search_data.get("query", {}).get("search", [])
                        if not search_results: continue
                        
                        page_title = search_results[0].get("title")
                        
                        # Get the actual image with a larger size for better quality
                        img_params = {
                            "action": "query",
                            "titles": page_title,
                            "prop": "pageimages",
                            "format": "json",
                            "pithumbsize": 1000
                        }
                        
                        async with session.get(api_url, params=img_params, timeout=5) as img_resp:
                            if img_resp.status != 200: continue
                            img_data = await img_resp.json()
                            pages = img_data.get("query", {}).get("pages", {})
                            for pid in pages:
                                thumbnail = pages[pid].get("thumbnail", {}).get("source")
                                if thumbnail:
                                    # Final verification download
                                    async with session.get(thumbnail, timeout=5) as final_resp:
                                        if final_resp.status == 200:
                                            data = await final_resp.read()
                                            # Ensure it's not a tiny icon or broken link
                                            if len(data) > 5000: 
                                                return discord.File(io.BytesIO(data), filename="driver.jpg")
                except:
                    continue
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

        for round_num in range(1, 31):
            if ctx.channel.id not in self.games or not game['active']: break

            async with ctx.typing():
                image_file = None
                driver = ""
                # Ultra-aggressive retry logic
                for _ in range(20): # Increased to 20 attempts
                    potential_driver = random.choice(self.drivers_list)
                    image_file = await self.get_driver_image(potential_driver)
                    if image_file:
                        driver = potential_driver
                        break

            if not image_file:
                await ctx.send("❌ Internal Error: Could not load images. Please check bot connection.")
                break

            embed = discord.Embed(title=f"Round {round_num}/30: Who is this F1 Driver?", color=discord.Color.red())
            embed.set_image(url="attachment://driver.jpg")
            embed.set_footer(text="Type the full name or last name!")
            
            await ctx.send(file=image_file, embed=embed)

            def check(m):
                if m.channel != ctx.channel or m.author.bot: return False
                content = m.content.lower().strip()
                target = driver.lower()
                # Last name match logic
                names = target.split()
                return content == target or (len(names) > 1 and content == names[-1])

            try:
                msg = await self.bot.wait_for("message", check=check, timeout=15.0)
                author_id = msg.author.id
                game['scores'][author_id] = game['scores'].get(author_id, 0) + 1
                await ctx.send(f"✅ **Correct!** It was **{driver}**. {msg.author.mention} has {game['scores'][author_id]} points.")
                
                if game['scores'][author_id] >= 10:
                    await ctx.send(f"🏆 {msg.author.mention} wins with 10 points!")
                    async with self.config.leaderboard() as lb:
                        lb[str(author_id)] = lb.get(str(author_id), 0) + 1
                    del self.games[ctx.channel.id]
                    return
            except asyncio.TimeoutError:
                if game['active']:
                    await ctx.send(f"⏰ **Time's up!** It was **{driver}**.")
            
            await asyncio.sleep(2)

        if ctx.channel.id in self.games:
            scores = game['scores']
            if scores:
                winner_id = max(scores, key=scores.get)
                winner = ctx.guild.get_member(winner_id)
                await ctx.send(f"🏁 **Game Over!** Winner: {winner.mention if winner else f'User {winner_id}'} with {scores[winner_id]} points!")
                async with self.config.leaderboard() as lb:
                    lb[str(winner_id)] = lb.get(str(winner_id), 0) + 1
            else:
                await ctx.send("🏁 **Game Over!** No points scored.")
            del self.games[ctx.channel.id]

    @f1quiz.command(name="stop")
    async def f1_stop(self, ctx):
        """Stop the current game."""
        if ctx.channel.id in self.games:
            self.games[ctx.channel.id]['active'] = False
            await ctx.send("🛑 **Stopping F1 Quiz...**")
        else:
            await ctx.send("No game running.")

    @f1quiz.command(name="leaderboard")
    async def f1_leaderboard(self, ctx):
        """Show global top 10 players."""
        lb = await self.config.leaderboard()
        if not lb:
            await ctx.send("Leaderboard is empty.")
            return
        sorted_lb = sorted(lb.items(), key=lambda x: x[1], reverse=True)[:10]
        embed = discord.Embed(title="🏎️ F1 Trivia Leaderboard", color=discord.Color.red())
        embed.description = "\n".join([f"**{i+1}.** <@{uid}> — {w} wins" for i, (uid, w) in enumerate(sorted_lb)])
        await ctx.send(embed=embed)
