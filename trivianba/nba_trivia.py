import discord
import random
import asyncio
from redbot.core import commands
from nba_api.stats.static import teams, players
from unidecode import unidecode

class NBATrivia(commands.Cog):
    """NBA Trivia Game: Guess Teams and Players!"""

    def __init__(self, bot):
        self.bot = bot
        self._teams = teams.get_teams()
        self._players = [p for p in players.get_players() if p['is_active']] 
        self.active_games = set()
        
        # Common team nicknames/short names mapping
        self.team_aliases = {
            'cleveland cavaliers': ['cavs'],
            'dallas mavericks': ['mavs'],
            'minnesota timberwolves': ['wolves', 't-wolves', 'twolves'],
            'philadelphia 76ers': ['sixers', '76ers'],
            'portland trail blazers': ['blazers'],
            'oklahoma city thunder': ['okc', 'thunder'],
            'san antonio spurs': ['spurs'],
            'golden state warriors': ['gsw', 'dubs'],
            'los angeles lakers': ['lakers', 'lal'],
            'los angeles clippers': ['clippers', 'lac', 'clips'],
            'new york knicks': ['knicks', 'nyk'],
            'brooklyn nets': ['nets', 'bkn'],
            'boston celtics': ['celtics', 'bos'],
            'chicago bulls': ['bulls', 'chi'],
            'miami heat': ['heat', 'mia'],
            'toronto raptors': ['raptors', 'raps', 'tor'],
            'milwaukee bucks': ['bucks', 'mil'],
            'detroit pistons': ['pistons', 'det'],
            'indiana pacers': ['pacers', 'ind'],
            'atlanta hawks': ['hawks', 'atl'],
            'charlotte hornets': ['hornets', 'cha'],
            'washington wizards': ['wizards', 'wiz', 'was'],
            'orlando magic': ['magic', 'orl'],
            'houston rockets': ['rockets', 'hou'],
            'memphis grizzlies': ['grizzlies', 'grizz', 'mem'],
            'new orleans pelicans': ['pelicans', 'pels', 'nop'],
            'utah jazz': ['jazz', 'uta'],
            'denver nuggets': ['nuggets', 'nuggs', 'den'],
            'phoenix suns': ['suns', 'phx'],
            'sacramento kings': ['kings', 'sac']
        }

    def normalize(self, text):
        """Normalize text for comparison (lowercase, remove accents, strip)."""
        return unidecode(text).lower().strip()

    def check_answer(self, message, answers):
        """Check if message content matches any of the valid answers."""
        content = self.normalize(message.content)
        for ans in answers:
            if self.normalize(ans) == content:
                return True
        return False

    async def run_game(self, ctx, game_type="team"):
        channel_id = ctx.channel.id
        if channel_id in self.active_games:
            await ctx.send("A game is already running in this channel!")
            return
        
        self.active_games.add(channel_id)
        scores = {}
        max_rounds = 50
        winning_score = 10
        round_num = 0

        await ctx.send(f"Starting {game_type.capitalize()} Trivia! First to {winning_score} points or {max_rounds} rounds wins!")

        try:
            while round_num < max_rounds:
                round_num += 1
                
                # Setup Question
                if game_type == "team":
                    if not self._teams:
                        await ctx.send("Error: No teams data loaded.")
                        break
                    item = random.choice(self._teams)
                    
                    full_name_lower = item['full_name'].lower()
                    correct_answers = [item['full_name'], item['nickname'], f"{item['city']} {item['nickname']}", item['abbreviation']]
                    
                    # Add common aliases if they exist
                    if full_name_lower in self.team_aliases:
                        correct_answers.extend(self.team_aliases[full_name_lower])
                    
                    image_url = f"https://a.espncdn.com/i/teamlogos/nba/500/{item['abbreviation'].lower()}.png"
                    title = f"Round {round_num}: Who is this NBA Team?"
                    answer_display = item['full_name']
                else: # player
                    if not self._players:
                        await ctx.send("Error: No players data loaded.")
                        break
                    item = random.choice(self._players)
                    # Allow Full Name, Last Name, and First Name (for unique famous players)
                    correct_answers = [item['full_name'], item['last_name'], item['first_name']]
                    # Updated URL to a more reliable source/resolution
                    image_url = f"https://cdn.nba.com/headshots/nba/latest/1040x760/{item['id']}.png"
                    title = f"Round {round_num}: Who is this NBA Player?"
                    answer_display = item['full_name']

                # Send Question Embed
                embed = discord.Embed(title=title, color=discord.Color.red() if game_type == "player" else discord.Color.blue())
                embed.set_image(url=image_url)
                embed.set_footer(text="You have 15 seconds to answer!")
                await ctx.send(embed=embed)

                # Wait for Answer
                def check(m):
                    return m.channel == ctx.channel and not m.author.bot and self.check_answer(m, correct_answers)

                try:
                    msg = await self.bot.wait_for("message", check=check, timeout=15.0)
                    user = msg.author
                    scores[user] = scores.get(user, 0) + 1
                    await ctx.send(f"Correct! {user.mention} guessed **{answer_display}**! (Score: {scores[user]})")
                    
                    if scores[user] >= winning_score:
                        await ctx.send(f"🏆 {user.mention} wins with {scores[user]} points!")
                        break

                except asyncio.TimeoutError:
                    await ctx.send(f"Time's up! The correct answer was **{answer_display}**.")
                
                await asyncio.sleep(2) # Brief pause before next round

        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
        finally:
            self.active_games.discard(channel_id)
            
            # Show Final Results if game ended without a winner (max rounds reached) or just summary
            if scores:
                sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                description = "\n".join([f"{u.mention}: {s}" for u, s in sorted_scores])
                embed = discord.Embed(title="Final Scores", description=description, color=discord.Color.gold())
                await ctx.send(embed=embed)
            else:
                await ctx.send("Game Over! No points scored.")

    @commands.command()
    async def teamtrivia(self, ctx):
        """Guess the NBA Team from its logo! (First to 10 or 50 rounds)"""
        await self.run_game(ctx, "team")

    @commands.command()
    async def playertrivia(self, ctx):
        """Guess the NBA Player from their headshot! (First to 10 or 50 rounds)"""
        await self.run_game(ctx, "player")
