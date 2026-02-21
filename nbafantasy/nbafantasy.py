import discord
from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import box
import asyncio
import time
import random
import requests

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
        for p in team_players:
            joined_fp = self.rosters_dict.get(str(p['id']), 0)
            earned_fp = p['fp'] - joined_fp
            options.append(discord.SelectOption(
                label=f"[{p.get('pos', 'G')}] {p['name']}",
                description=f"{p['team']} - Earned FP: {round(earned_fp, 1)}",
                value=str(p['id'])
            ))
            
        for i in range(0, len(options), 25):
            select = discord.ui.Select(
                placeholder=f"Select a player to DROP (Page {i//25 + 1})...", 
                options=options[i:i+25], 
                custom_id=f"drop_select_{i}"
            )
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

class DraftView(discord.ui.View):
    def __init__(self, cog, guild, available_players, current_picker_id):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.current_picker_id = current_picker_id
        
        options = []
        for p in available_players[:25]:
            options.append(discord.SelectOption(
                label=f"[{p.get('pos', 'G')}] {p['name']}",
                description=f"{p['team']} - FP: {p['fp']}",
                value=str(p['id'])
            ))
            
        if options:
            select = discord.ui.Select(placeholder="Draft a player...", options=options)
            select.callback = self.draft_callback
            self.add_item(select)

    async def draft_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.current_picker_id:
            return await interaction.response.send_message("It's not your turn to draft!", ephemeral=True)
            
        player_id = int(interaction.data['values'][0])
        await self.cog._perform_draft_pick(interaction, player_id)

class FreeAgentView(discord.ui.View):
    def __init__(self, cog, ctx, available_players):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.message = None
        
        options = []
        for p in available_players:
            options.append(discord.SelectOption(
                label=f"[{p.get('pos', 'G')}] {p['name']}",
                description=f"{p['team']} - Total Season FP: {p['fp']}",
                value=str(p['id'])
            ))
            
        for i in range(0, min(len(options), 100), 25): # Limit to 4 pages for stability
            select = discord.ui.Select(
                placeholder=f"Select a player to ADD (Page {i//25 + 1})...", 
                options=options[i:i+25], 
                custom_id=f"add_select_{i}"
            )
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
            return await interaction.response.send_message("Free Agency is currently locked.", ephemeral=True)
            
        player_id = int(interaction.data['values'][0])
        uid_str = str(self.ctx.author.id)
        
        player = next((p for p in self.cog.players_cache if p['id'] == player_id), None)
        if not player:
            return await interaction.response.send_message("Player not found.", ephemeral=True)

        settings = await self.cog.config.guild(self.ctx.guild).settings()
        async with self.cog.config.guild(self.ctx.guild).rosters() as rosters:
            if uid_str not in rosters: rosters[uid_str] = {}
            
            # Position/Max Check
            user_roster = rosters[uid_str]
            if len(user_roster) >= settings['max_players']:
                return await interaction.response.send_message(f"Roster full! Max {settings['max_players']} players.", ephemeral=True)
                
            pos_count = sum(1 for pid in user_roster.keys() if next((p['pos'] for p in self.cog.players_cache if str(p['id']) == pid), 'G') == player['pos'])
            if pos_count >= settings['positions'].get(player['pos'], 0):
                return await interaction.response.send_message(f"Your {player['pos']} spots are full! (Max {settings['positions'].get(player['pos'])})", ephemeral=True)

            # Ownership Check
            for team in rosters.values():
                if str(player_id) in team:
                    return await interaction.response.send_message("That player is already on another team!", ephemeral=True)
                    
            rosters[uid_str][str(player_id)] = player['fp']
            
            await interaction.response.send_message(f"✅ **{player['name']}** added successfully!", ephemeral=True)
            for child in self.children: child.disabled = True
            await interaction.message.edit(view=self)

class TradeView(discord.ui.View):
    def __init__(self, cog, sender, receiver, s_player, r_player):
        super().__init__(timeout=300)
        self.cog = cog
        self.sender = sender
        self.receiver = receiver
        self.s_player = s_player
        self.r_player = r_player

    @discord.ui.button(label="Accept Trade", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.receiver.id:
            return await interaction.response.send_message("Not your trade.", ephemeral=True)
        
        async with self.cog.config.guild(interaction.guild).rosters() as rosters:
            s_uid, r_uid = str(self.sender.id), str(self.receiver.id)
            # Remove
            s_val = rosters[s_uid].pop(str(self.s_player['id']))
            r_val = rosters[r_uid].pop(str(self.r_player['id']))
            # Add
            rosters[s_uid][str(self.r_player['id'])] = r_val
            rosters[r_uid][str(self.s_player['id'])] = s_val
            
        await interaction.response.send_message(f"✅ Trade Complete! {self.s_player['name']} <-> {self.r_player['name']}")
        self.stop()

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in [self.sender.id, self.receiver.id]:
            return await interaction.response.send_message("Not your trade.", ephemeral=True)
        await interaction.response.send_message("Trade declined.")
        self.stop()

class NBAFantasy(commands.Cog):
    """NBA Fantasy League with Drafting, Trading, and Positions!"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=928374928374, force_registration=True)
        
        default_guild = {
            "is_active": False,
            "fa_locked": False,
            "rosters": {}, 
            "scores": {},
            "settings": {
                "max_players": 10,
                "positions": {"G": 4, "F": 4, "C": 2},
                "point_values": {"pts": 1.0, "reb": 1.2, "ast": 1.5, "stl": 3.0, "blk": 3.0, "tov": -1.0}
            },
            "draft": {
                "order": [],
                "current_index": 0,
                "is_running": False,
                "round": 1
            }
        }
        self.config.register_guild(**default_guild)
        self.config.register_global(players_cache=[])
        self.players_cache = []
        self.last_fetch_error = None
        self._setup_session()
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
                await asyncio.sleep(43200) 
            except Exception as e:
                self.last_fetch_error = str(e)
                print(f"[NBAFantasy] Error fetching stats: {e}")
                await asyncio.sleep(300)

    def _setup_session(self):
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": "Mozilla/5.0"})

    async def _fetch_players(self):
        def fetch():
            url = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/statistics/byathlete?region=us&lang=en&contentorigin=espn&isqualified=false&limit=500"
            r = self._session.get(url, timeout=30)
            r.raise_for_status()
            return r.json().get("athletes", [])
            
        data = await asyncio.get_running_loop().run_in_executor(None, fetch)
        pv = {"pts": 1.0, "reb": 1.2, "ast": 1.5, "stl": 3.0, "blk": 3.0, "tov": -1.0}
        
        cached = []
        for p in data:
            athlete = p.get("athlete", {})
            try: pid = int(athlete.get("id", 0))
            except: continue
            
            pos = athlete.get("position", {}).get("abbreviation", "G")[0] # Just G, F, or C
            if pos not in ["G", "F", "C"]: pos = "G"
            
            stats = {"pts": 0, "reb": 0, "ast": 0, "stl": 0, "blk": 0, "tov": 0}
            for cat in p.get("categories", []):
                names, values = cat.get("names", []), cat.get("values", [])
                for k in stats.keys():
                    if k == "pts": search = "points"
                    elif k == "reb": search = "rebounds"
                    elif k == "ast": search = "assists"
                    elif k == "tov": search = "turnovers"
                    else: search = k
                    if search in names: stats[k] = float(values[names.index(search)])
            
            fp = sum(stats[k] * pv[k] for k in stats)
            cached.append({
                "id": pid, "name": athlete.get("displayName"), "team": athlete.get("teamShortName", "FA"),
                "pos": pos, "fp": round(fp, 1), "pts": stats["pts"]
            })
        self.players_cache = sorted(cached, key=lambda x: x['fp'], reverse=True)

    @commands.group(name="fantasy")
    async def fantasy(self, ctx):
        """NBA Fantasy League"""
        pass

    @fantasy.command(name="setup")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_setup(self, ctx):
        """Enable NBA Fantasy."""
        await self.config.guild(ctx.guild).is_active.set(True)
        await ctx.send("🏀 NBA Fantasy enabled! `[p]fantasy join` to start.")

    @fantasy.command(name="join")
    async def fantasy_join(self, ctx):
        """Join the league."""
        async with self.config.guild(ctx.guild).rosters() as rosters:
            if str(ctx.author.id) in rosters: return await ctx.send("Joined already.")
            rosters[str(ctx.author.id)] = {}
        await ctx.send("🎉 Joined!")

    @fantasy.command(name="settings")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_settings(self, ctx, key: str = None, value: str = None):
        """View or update settings. Keys: point_pts, point_reb, pos_g, pos_f, pos_c, etc."""
        async with self.config.guild(ctx.guild).settings() as s:
            if not key:
                embed = discord.Embed(title="NBA Fantasy Settings", color=discord.Color.blue())
                pv = s["point_values"]
                pos = s["positions"]
                embed.add_field(name="Scoring", value=f"PTS: {pv['pts']} | REB: {pv['reb']} | AST: {pv['ast']}\nSTL: {pv['stl']} | BLK: {pv['blk']} | TOV: {pv['tov']}", inline=False)
                embed.add_field(name="Roster Requirements", value=f"Guards: {pos['G']} | Forwards: {pos['F']} | Centers: {pos['C']}\nTotal: {s['max_players']}", inline=False)
                return await ctx.send(embed=embed)

            if key.startswith("point_"):
                stat = key.split("_")[1].lower()
                if stat in s["point_values"]: 
                    s["point_values"][stat] = float(value)
                    await ctx.send(f"✅ Updated {stat.upper()} to {value} points.")
            elif key.startswith("pos_"):
                p = key.split("_")[1].upper()
                if p in s["positions"]: 
                    s["positions"][p] = int(value)
                    s["max_players"] = sum(s["positions"].values())
                    await ctx.send(f"✅ Updated {p} requirement to {value}. New total roster size: {s['max_players']}.")
            else:
                await ctx.send("Invalid key. Use `point_pts`, `pos_g`, etc.")

    @fantasy.command(name="draft")
    @commands.admin_or_permissions(manage_guild=True)
    async def start_draft(self, ctx):
        """Start the draft."""
        rosters = await self.config.guild(ctx.guild).rosters()
        order = list(rosters.keys())
        random.shuffle(order)
        async with self.config.guild(ctx.guild).draft() as d:
            d.update({"order": order, "current_index": 0, "is_running": True, "round": 1})
        await self._announce_draft_turn(ctx)

    async def _announce_draft_turn(self, ctx):
        d = await self.config.guild(ctx.guild).draft()
        if not d["is_running"]: return
        uid = int(d["order"][d["current_index"]])
        user = ctx.guild.get_member(uid)
        avail = await self._get_avail(ctx.guild)
        view = DraftView(self, ctx.guild, avail, uid)
        await ctx.send(f"🏀 Round {d['round']}: {user.mention}'s turn!", view=view)

    async def _perform_draft_pick(self, interaction, pid):
        uid = str(interaction.user.id)
        player = next((p for p in self.players_cache if p['id'] == pid), None)
        
        settings = await self.config.guild(interaction.guild).settings()
        async with self.config.guild(interaction.guild).rosters() as rosters:
            if uid not in rosters: rosters[uid] = {}
            
            # Position Check
            user_roster = rosters[uid]
            pos_count = sum(1 for pid_str in user_roster.keys() if next((p['pos'] for p in self.players_cache if str(p['id']) == pid_str), 'G') == player['pos'])
            if pos_count >= settings['positions'].get(player['pos'], 0):
                return await interaction.response.send_message(f"Your {player['pos']} spots are full! Choose another position.", ephemeral=True)
                
            rosters[uid][str(pid)] = player['fp']
            
        await interaction.response.send_message(f"✅ Drafted **{player['name']}** ({player['pos']})!")
        
        async with self.config.guild(interaction.guild).draft() as d:
            d["current_index"] += 1
            if d["current_index"] >= len(d["order"]):
                d["current_index"] = 0
                d["round"] += 1
                if d["round"] > settings["max_players"]:
                    d["is_running"] = False
                    return await interaction.channel.send("🏆 **Draft Complete!** All rosters are set. Good luck this season!")
        
        # Determine next picker
        await self._announce_draft_turn(await self.bot.get_context(interaction.message))

    async def _get_avail(self, guild):
        rosters = await self.config.guild(guild).rosters()
        taken = {int(pid) for team in rosters.values() for pid in team}
        return [p for p in self.players_cache if p['id'] not in taken]

    @fantasy.command(name="team")
    async def fantasy_team(self, ctx, member: discord.Member = None):
        """View team and drop players."""
        target = member or ctx.author
        rosters = await self.config.guild(ctx.guild).rosters()
        if str(target.id) not in rosters: return await ctx.send("Not in league.")
        
        pids = [int(p) for p in rosters[str(target.id)].keys()]
        team = [p for p in self.players_cache if p['id'] in pids]
        
        embed = discord.Embed(title=f"{target.name}'s Team", color=0xffa500)
        for p in team:
            embed.add_field(name=f"[{p['pos']}] {p['name']}", value=f"{p['team']}", inline=True)
        
        view = TeamManagementView(self, ctx, team, rosters[str(target.id)]) if target == ctx.author else None
        await ctx.send(embed=embed, view=view)

    @fantasy.command(name="freeagents", aliases=["fa"])
    async def fantasy_fa(self, ctx):
        """Browse Free Agents."""
        avail = await self._get_avail(ctx.guild)
        embed = discord.Embed(title="Free Agents", color=0x0000ff)
        for p in avail[:10]:
            embed.add_field(name=f"[{p['pos']}] {p['name']}", value=f"FP: {p['fp']}", inline=True)
        await ctx.send(embed=embed, view=FreeAgentView(self, ctx, avail))

    @fantasy.command(name="trade")
    async def fantasy_trade(self, ctx, member: discord.Member, your_p: str, their_p: str):
        """Trade: [p]fantasy trade @user 'Your Player' 'Their Player'"""
        rosters = await self.config.guild(ctx.guild).rosters()
        s_id, r_id = str(ctx.author.id), str(member.id)
        if s_id not in rosters or r_id not in rosters: return await ctx.send("Both must be in league.")
        
        s_p = next((p for p in self.players_cache if (your_p.lower() in p['name'].lower() or your_p == str(p['id'])) and str(p['id']) in rosters[s_id]), None)
        r_p = next((p for p in self.players_cache if (their_p.lower() in p['name'].lower() or their_p == str(p['id'])) and str(p['id']) in rosters[r_id]), None)
        
        if not s_p or not r_p: return await ctx.send("Player(s) not found on respective rosters.")
        
        embed = discord.Embed(title="Trade Proposal", description=f"{ctx.author.mention} wants to trade **{s_p['name']}** for {member.mention}'s **{r_p['name']}**", color=0x00ff00)
        await ctx.send(content=member.mention, embed=embed, view=TradeView(self, ctx.author, member, s_p, r_p))

    @fantasy.command(name="search")
    async def fantasy_search(self, ctx, *, query: str):
        """Search players."""
        ms = [p for p in self.players_cache if query.lower() in p['name'].lower()][:10]
        if not ms: return await ctx.send("No matches.")
        e = discord.Embed(title="Results", color=0x00ffff)
        for p in ms: e.add_field(name=f"[{p['pos']}] {p['name']}", value=f"{p['team']} | FP: {p['fp']}", inline=False)
        await ctx.send(embed=e)
