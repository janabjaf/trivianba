import discord
from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import box
import asyncio
from nba_api.stats.endpoints import leaguedashplayerstats

class TeamManagementView(discord.ui.View):
    def __init__(self, cog, ctx, team_players, rosters_dict):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.rosters_dict = rosters_dict
        self.message = None
        
        if not team_players:
            return
            
        options = []
        for p in team_players[:25]:
            joined_fp = self.rosters_dict.get(str(p['id']), 0)
            earned_fp = p['fp'] - joined_fp
            options.append(discord.SelectOption(
                label=p['name'],
                description=f"{p['team']} - Earned FP: {round(earned_fp, 1)}",
                value=str(p['id'])
            ))
            
        select = discord.ui.Select(placeholder="Select a player to DROP...", options=options, custom_id="drop_select")
        select.callback = self.drop_callback
        self.add_item(select)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except:
            pass

    async def drop_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
            
        player_id = int(interaction.data['values'][0])
        uid_str = str(self.ctx.author.id)
        
        async with self.cog.config.guild(self.ctx.guild).rosters() as rosters:
            if uid_str in rosters and str(player_id) in rosters[uid_str]:
                joined_fp = rosters[uid_str].pop(str(player_id))
                
                # Add earned points to permanent score
                player = next((p for p in self.cog.players_cache if p['id'] == player_id), None)
                if player:
                    earned_fp = player['fp'] - joined_fp
                    async with self.cog.config.guild(self.ctx.guild).scores() as scores:
                        scores[uid_str] = scores.get(uid_str, 0.0) + earned_fp
                        
                await interaction.response.send_message("Player dropped successfully.", ephemeral=True)
                for child in self.children:
                    child.disabled = True
                await interaction.message.edit(view=self)
            else:
                await interaction.response.send_message("Failed to drop player.", ephemeral=True)

class FreeAgentView(discord.ui.View):
    def __init__(self, cog, ctx, available_players):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.message = None
        
        options = []
        for p in available_players[:25]:
            options.append(discord.SelectOption(
                label=p['name'],
                description=f"{p['team']} - Total Season FP: {p['fp']}",
                value=str(p['id'])
            ))
            
        if options:
            select = discord.ui.Select(placeholder="Select a player to ADD...", options=options, custom_id="add_select")
            select.callback = self.add_callback
            self.add_item(select)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except:
            pass

    async def add_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
            
        fa_locked = await self.cog.config.guild(self.ctx.guild).fa_locked()
        if fa_locked:
            return await interaction.response.send_message("Free Agency is currently locked by admins.", ephemeral=True)
            
        player_id = int(interaction.data['values'][0])
        uid_str = str(self.ctx.author.id)
        
        async with self.cog.config.guild(self.ctx.guild).rosters() as rosters:
            if uid_str not in rosters:
                rosters[uid_str] = {}
                
            if len(rosters[uid_str]) >= 10:
                return await interaction.response.send_message("Your roster is full (max 10). Drop someone first.", ephemeral=True)
                
            # Check if anyone else has this player
            for team_dict in rosters.values():
                if isinstance(team_dict, dict) and str(player_id) in team_dict:
                    return await interaction.response.send_message("That player is already on another team!", ephemeral=True)
                elif isinstance(team_dict, list) and player_id in team_dict:
                    return await interaction.response.send_message("That player is already on another team!", ephemeral=True)
                    
            player = next((p for p in self.cog.players_cache if p['id'] == player_id), None)
            if not player:
                return await interaction.response.send_message("Player not found in cache. Please try again later.", ephemeral=True)
                
            rosters[uid_str][str(player_id)] = player['fp']
            
            await interaction.response.send_message(f"**{player['name']}** added to your team successfully!", ephemeral=True)
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)


class NBAFantasy(commands.Cog):
    """NBA Fantasy League within Discord!"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=928374928374, force_registration=True)
        
        default_guild = {
            "is_active": False,
            "fa_locked": False,
            "rosters": {}, # uid_str: {str(player_id): joined_fp}
            "scores": {}   # uid_str: accumulated_fp
        }
        default_global = {
            "players_cache": []
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.players_cache = []
        self.last_fetch_error = None
        self.bg_task = bot.loop.create_task(self.update_cache_loop())

    def cog_unload(self):
        self.bg_task.cancel()

    async def update_cache_loop(self):
        await self.bot.wait_until_ready()
        self.players_cache = await self.config.players_cache()
        while True:
            try:
                await self._fetch_players()
                await self.config.players_cache.set(self.players_cache)
                self.last_fetch_error = None
                await asyncio.sleep(43200) # Update every 12 hours
            except Exception as e:
                self.last_fetch_error = str(e)
                print(f"[NBAFantasy] Error fetching NBA stats: {e}")
                await asyncio.sleep(300) # Retry after 5 minutes on error

    async def _fetch_players(self):
        def fetch():
            # NBA API requires specific headers including origin and token to bypass Akamai
            custom_headers = {
                'Host': 'stats.nba.com',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:72.0) Gecko/20100101 Firefox/72.0',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'x-nba-stats-origin': 'stats',
                'x-nba-stats-token': 'true',
                'Connection': 'keep-alive',
                'Referer': 'https://stats.nba.com/',
                'Pragma': 'no-cache',
                'Cache-Control': 'no-cache'
            }
            import time
            for attempt in range(3):
                try:
                    stats = leaguedashplayerstats.LeagueDashPlayerStats(timeout=30, headers=custom_headers)
                    return stats.get_normalized_dict()['LeagueDashPlayerStats']
                except Exception as e:
                    if attempt == 2:
                        raise e
                    time.sleep(3)
            
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, fetch)
        
        cached = []
        for p in data:
            fp = (p['PTS'] * 1 +
                  p['REB'] * 1.2 +
                  p['AST'] * 1.5 +
                  p['STL'] * 3 +
                  p['BLK'] * 3 +
                  p['TOV'] * -1)
            cached.append({
                "id": p['PLAYER_ID'],
                "name": p['PLAYER_NAME'],
                "team": p['TEAM_ABBREVIATION'],
                "fp": round(fp, 1),
                "pts": p['PTS'],
                "reb": p['REB'],
                "ast": p['AST']
            })
        
        self.players_cache = sorted(cached, key=lambda x: x['fp'], reverse=True)

    @commands.group(name="fantasy", aliases=["nbafantasy", "nbaf"])
    async def fantasy(self, ctx):
        """Main command for NBA Fantasy"""
        pass

    @fantasy.command(name="setup")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_setup(self, ctx):
        """Enable NBA Fantasy in this server."""
        await self.config.guild(ctx.guild).is_active.set(True)
        await ctx.send("🏀 NBA Fantasy has been enabled for this server! Users can now `[p]fantasy join`.")

    @fantasy.command(name="join")
    async def fantasy_join(self, ctx):
        """Join the server's NBA Fantasy league."""
        is_active = await self.config.guild(ctx.guild).is_active()
        if not is_active:
            return await ctx.send("Fantasy league is not active in this server. An admin must run `[p]fantasy setup` first.")
            
        async with self.config.guild(ctx.guild).rosters() as rosters:
            uid_str = str(ctx.author.id)
            if uid_str in rosters:
                return await ctx.send("You have already joined the league!")
            rosters[uid_str] = {}
            
        async with self.config.guild(ctx.guild).scores() as scores:
            scores[str(ctx.author.id)] = 0.0
            
        await ctx.send("🎉 You have successfully joined the fantasy league! Use `[p]fantasy freeagents` to pick up players.")

    @fantasy.command(name="team")
    async def fantasy_team(self, ctx, member: discord.Member = None):
        """View your team or another member's team."""
        target = member or ctx.author
        uid_str = str(target.id)
        
        rosters = await self.config.guild(ctx.guild).rosters()
        
        if uid_str not in rosters:
            if member:
                return await ctx.send(f"{target.display_name} hasn't joined the league yet.")
            return await ctx.send("You haven't joined the league yet. Use `[p]fantasy join`.")
            
        if not self.players_cache:
            if self.last_fetch_error:
                return await ctx.send(f"❌ **NBA API Error:** The bot could not fetch player stats.\n`{self.last_fetch_error}`\n\nThe bot owner can try `[p]fantasy update`.")
            return await ctx.send("Player data is currently updating. Please try again later.")
            
        player_dict = rosters[uid_str]
        
        # Check if the data is from the old list format and reset if needed to avoid crash
        if isinstance(player_dict, list):
            async with self.config.guild(ctx.guild).rosters() as r:
                r[uid_str] = {}
            player_dict = {}
            
        player_ids = [int(pid) for pid in player_dict.keys()]
        team_players = [p for p in self.players_cache if p['id'] in player_ids]
        
        scores = await self.config.guild(ctx.guild).scores()
        accumulated_fp = scores.get(uid_str, 0.0)
        
        embed = discord.Embed(title=f"{target.display_name}'s Fantasy Team", color=discord.Color.orange())
        embed.set_thumbnail(url=target.display_avatar.url)
        
        if not team_players:
            embed.description = f"**Total Team FP:** {round(accumulated_fp, 1)}\n\nThis team is empty! Use `[p]fantasy freeagents` to pick up players."
            return await ctx.send(embed=embed)
            
        current_roster_fp = 0
        for p in team_players:
            joined_fp = player_dict.get(str(p['id']), p['fp'])
            earned_fp = p['fp'] - joined_fp
            embed.add_field(name=p['name'], value=f"{p['team']} | Earned FP: {round(earned_fp, 1)}", inline=True)
            current_roster_fp += earned_fp
            
        total_team_fp = accumulated_fp + current_roster_fp
        
        if target == ctx.author:
            embed.description = f"**Total Team FP:** {round(total_team_fp, 1)}\n*Use the dropdown below to drop a player.*"
            view = TeamManagementView(self, ctx, team_players, player_dict)
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
        else:
            embed.description = f"**Total Team FP:** {round(total_team_fp, 1)}"
            await ctx.send(embed=embed)

    @fantasy.command(name="freeagents", aliases=["fa"])
    async def fantasy_freeagents(self, ctx):
        """Browse and pick up available free agents."""
        fa_locked = await self.config.guild(ctx.guild).fa_locked()
        if fa_locked:
            return await ctx.send("🔒 Free Agency is currently locked by the admins.")
            
        rosters = await self.config.guild(ctx.guild).rosters()
        uid_str = str(ctx.author.id)
        
        if uid_str not in rosters:
            return await ctx.send("You haven't joined the league yet. Use `[p]fantasy join`.")
            
        if not self.players_cache:
            if self.last_fetch_error:
                return await ctx.send(f"❌ **NBA API Error:** The bot could not fetch player stats.\n`{self.last_fetch_error}`\n\nThe bot owner can try `[p]fantasy update`.")
            return await ctx.send("Player data is currently updating. Please try again later.")
            
        taken_ids = set()
        for team_dict in rosters.values():
            if isinstance(team_dict, dict):
                taken_ids.update(int(pid) for pid in team_dict.keys())
            elif isinstance(team_dict, list):
                taken_ids.update(team_dict)
            
        available_players = [p for p in self.players_cache if p['id'] not in taken_ids]
        
        if not available_players:
            return await ctx.send("No free agents available.")
            
        embed = discord.Embed(
            title="Top Available Free Agents", 
            description="Select a player from the dropdown to add to your team.\nPlayers are sorted by Total Season FP.", 
            color=discord.Color.blue()
        )
        
        for p in available_players[:10]:
            embed.add_field(name=p['name'], value=f"{p['team']} | FP: {p['fp']} | PTS: {p['pts']}", inline=True)
            
        view = FreeAgentView(self, ctx, available_players)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @fantasy.command(name="standings")
    async def fantasy_standings(self, ctx):
        """View the league standings."""
        rosters = await self.config.guild(ctx.guild).rosters()
        
        if not rosters:
            return await ctx.send("No one has joined the league yet.")
            
        if not self.players_cache:
            if self.last_fetch_error:
                return await ctx.send(f"❌ **NBA API Error:** The bot could not fetch player stats.\n`{self.last_fetch_error}`\n\nThe bot owner can try `[p]fantasy update`.")
            return await ctx.send("Player data is currently updating. Please try again later.")
            
        scores = await self.config.guild(ctx.guild).scores()
        leaderboard = []
        
        for uid_str, player_dict in rosters.items():
            if isinstance(player_dict, list):
                continue # Skip old corrupted data if it exists
                
            team_players = [p for p in self.players_cache if p['id'] in [int(pid) for pid in player_dict.keys()]]
            current_roster_fp = sum(p['fp'] - player_dict.get(str(p['id']), p['fp']) for p in team_players)
            
            total_fp = scores.get(uid_str, 0.0) + current_roster_fp
            
            # Find best current player
            best_player = None
            if team_players:
                best_player = max(team_players, key=lambda p: p['fp'] - player_dict.get(str(p['id']), p['fp']))
                
            leaderboard.append((uid_str, round(total_fp, 1), best_player, player_dict))
            
        leaderboard.sort(key=lambda x: x[1], reverse=True)
        
        embed = discord.Embed(title="🏆 NBA Fantasy Standings", color=discord.Color.gold())
        
        for idx, (uid_str, score, best_player, player_dict) in enumerate(leaderboard, 1):
            user = ctx.guild.get_member(int(uid_str))
            name = user.display_name if user else f"User {uid_str}"
            
            top_player_str = ""
            if best_player:
                earned_fp = best_player['fp'] - player_dict.get(str(best_player['id']), best_player['fp'])
                top_player_str = f"\n*MVP: {best_player['name']} (+{round(earned_fp, 1)} FP)*"
                
            embed.add_field(name=f"{idx}. {name}", value=f"**{score}** Fantasy Points{top_player_str}", inline=False)
            
        await ctx.send(embed=embed)

    @fantasy.command(name="lock")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_lock(self, ctx):
        """Lock free agency (Admin)."""
        await self.config.guild(ctx.guild).fa_locked.set(True)
        await ctx.send("🔒 Free Agency has been locked. Players can no longer be picked up.")

    @fantasy.command(name="unlock")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_unlock(self, ctx):
        """Unlock free agency (Admin)."""
        await self.config.guild(ctx.guild).fa_locked.set(False)
        await ctx.send("🔓 Free Agency has been unlocked. Players can now be picked up.")

    @fantasy.command(name="remove")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_remove(self, ctx, member: discord.Member):
        """Remove a user's team from the league (Admin)."""
        uid_str = str(member.id)
        
        async with self.config.guild(ctx.guild).rosters() as rosters:
            if uid_str in rosters:
                del rosters[uid_str]
                
        async with self.config.guild(ctx.guild).scores() as scores:
            if uid_str in scores:
                del scores[uid_str]
                
        await ctx.send(f"🗑️ Successfully removed **{member.display_name}** from the fantasy league.")

    @fantasy.command(name="reset")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_reset(self, ctx):
        """Reset the entire fantasy league (Admin)."""
        await ctx.send("⚠️ Are you sure you want to completely wipe all rosters and scores for this server? Type `yes` to confirm.")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30.0)
        except asyncio.TimeoutError:
            return await ctx.send("Reset cancelled due to timeout.")

        if msg.content.lower() == "yes":
            await self.config.guild(ctx.guild).rosters.set({})
            await self.config.guild(ctx.guild).scores.set({})
            await ctx.send("🔄 The fantasy league has been completely reset. All teams and scores are wiped.")
        else:
            await ctx.send("Reset cancelled.")

    @fantasy.command(name="update")
    @commands.is_owner()
    async def fantasy_update(self, ctx):
        """Force update the player stats cache (Bot Owner only)."""
        await ctx.send("Fetching latest stats from NBA API... This may take a moment.")
        try:
            await self._fetch_players()
            await ctx.send(f"✅ Successfully updated stats for {len(self.players_cache)} players!")
        except Exception as e:
            await ctx.send(f"❌ Failed to update stats: {box(str(e))}")