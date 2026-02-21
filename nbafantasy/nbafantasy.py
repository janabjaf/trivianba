import discord
from redbot.core import commands, Config, checks
from redbot.core.utils.chat_formatting import box
import asyncio
import time
import requests
import math

VALID_SLOTS = {
    "PG": ["PG", "G", "UTIL"],
    "SG": ["SG", "G", "UTIL", "SF"],
    "SF": ["SF", "F", "UTIL", "SG", "PF"],
    "PF": ["PF", "F", "UTIL", "SF", "C"],
    "C":  ["C", "UTIL", "PF", "F"],
    "G":  ["PG", "SG", "G", "UTIL"],
    "F":  ["SF", "PF", "F", "UTIL", "C"],
    "UTIL": ["UTIL"]
}

def can_fit_roster(players, slots):
    if len(players) > len(slots): return False
    
    # Pre-calculate allowed slots for each player to avoid repeated lookups
    player_requirements = []
    for p in players:
        pos = p.get('pos', 'UTIL')
        # Handle ESPN's potentially grouped positions like "G" or "F"
        allowed = set(VALID_SLOTS.get(pos, ["UTIL"]))
        player_requirements.append(allowed)

    def solve(player_idx, available_slots):
        if player_idx == len(players): return True
        
        allowed_for_this_player = player_requirements[player_idx]
        
        for i, slot in enumerate(available_slots):
            if slot in allowed_for_this_player:
                # Optimized recursion: pass a new list without the used slot
                if solve(player_idx + 1, available_slots[:i] + available_slots[i+1:]):
                    return True
        return False
        
    return solve(0, list(slots))

def assign_slots(players, slots):
    unassigned_players = list(players)
    remaining_slots = list(slots)
    
    def rank_slot(s):
        if s == 'UTIL': return 3
        if s in ('G', 'F'): return 2
        return 1
        
    sorted_slots = sorted(remaining_slots, key=rank_slot)
    
    assignment_map = []
    for s in sorted_slots:
        placed = False
        for i, p in enumerate(unassigned_players):
            pos = p.get('pos', 'UTIL')
            allowed = VALID_SLOTS.get(pos, ["UTIL"])
            if s in allowed:
                assignment_map.append((s, p))
                unassigned_players.pop(i)
                placed = True
                break
        if not placed:
            assignment_map.append((s, None))
            
    final_display = []
    temp_map = list(assignment_map)
    for s in slots:
        for i, (assigned_s, p) in enumerate(temp_map):
            if assigned_s == s:
                final_display.append((s, p))
                temp_map.pop(i)
                break
                
    for p in unassigned_players:
        final_display.append(("BENCH", p))
        
    return final_display

def calculate_fp(player, scoring_system):
    return round(
        player.get('pts', 0) * scoring_system.get('pts', 1.0) +
        player.get('reb', 0) * scoring_system.get('reb', 1.2) +
        player.get('ast', 0) * scoring_system.get('ast', 1.5) +
        player.get('stl', 0) * scoring_system.get('stl', 3.0) +
        player.get('blk', 0) * scoring_system.get('blk', 3.0) +
        player.get('tov', 0) * scoring_system.get('tov', -1.0), 
        1
    )

class SearchModal(discord.ui.Modal, title='Search Player'):
    query = discord.ui.TextInput(label='Player Name', style=discord.TextStyle.short)
    
    def __init__(self, view):
        super().__init__()
        self.parent_view = view
        
    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.search_query = self.query.value.lower()
        self.parent_view.current_page = 0
        await self.parent_view.update_view(interaction)

class PlayerListPagination(discord.ui.View):
    def __init__(self, cog, ctx, available_players, scoring_system, slots, action_type="fa"):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.all_players = available_players
        self.scoring_system = scoring_system
        self.slots = slots
        self.action_type = action_type
        self.current_page = 0
        self.search_query = ""
        self.message = None
        self.update_items()

    def get_filtered_players(self):
        players = self.all_players
        if self.search_query:
            players = [p for p in players if self.search_query in p['name'].lower()]
        players.sort(key=lambda x: calculate_fp(x, self.scoring_system), reverse=True)
        return players

    def update_items(self):
        self.clear_items()
        filtered = self.get_filtered_players()
        max_pages = max(1, math.ceil(len(filtered) / 25))
        self.current_page = min(self.current_page, max_pages - 1)
        if self.current_page < 0: self.current_page = 0
        
        start_idx = self.current_page * 25
        page_players = filtered[start_idx:start_idx+25]
        
        search_btn = discord.ui.Button(label="Search", style=discord.ButtonStyle.secondary, row=1)
        search_btn.callback = self.search_callback
        self.add_item(search_btn)
        
        prev_btn = discord.ui.Button(label="Prev", style=discord.ButtonStyle.primary, disabled=(self.current_page == 0), row=1)
        prev_btn.callback = self.prev_callback
        self.add_item(prev_btn)
        
        next_btn = discord.ui.Button(label="Next", style=discord.ButtonStyle.primary, disabled=(self.current_page >= max_pages - 1), row=1)
        next_btn.callback = self.next_callback
        self.add_item(next_btn)

        if page_players:
            options = []
            for p in page_players:
                fp = calculate_fp(p, self.scoring_system)
                status_emoji = "🏥" if p.get('out', False) else "🏀"
                options.append(discord.SelectOption(
                    label=f"{p['name']} ({p['pos']})",
                    description=f"{status_emoji} {p['team']} | FP: {fp} | PTS: {p['pts']}",
                    value=str(p['id'])
                ))
            
            placeholder = "Select a player to ADD..." if self.action_type == "fa" else "Select a player to DRAFT..."
            select = discord.ui.Select(placeholder=placeholder, options=options, custom_id="player_select", row=0)
            select.callback = self.select_callback
            self.add_item(select)
            
    async def update_view(self, interaction_or_message):
        self.update_items()
        filtered = self.get_filtered_players()
        max_pages = max(1, math.ceil(len(filtered) / 25))
        
        if isinstance(interaction_or_message, discord.Interaction):
            embed = interaction_or_message.message.embeds[0]
        else:
            embed = interaction_or_message.embeds[0]
            
        embed.clear_fields()
        page_players = filtered[self.current_page * 25:(self.current_page + 1) * 25]
        for p in page_players[:10]:
            fp = calculate_fp(p, self.scoring_system)
            status = " [OUT]" if p.get('out', False) else ""
            embed.add_field(name=f"{p['name']} ({p['pos']}){status}", value=f"{p['team']} | FP: {fp} | PTS: {p['pts']} REB: {p['reb']} AST: {p['ast']}", inline=True)
            
        embed.set_footer(text=f"Page {self.current_page + 1}/{max_pages} | Search: {self.search_query or 'None'}")
        
        if isinstance(interaction_or_message, discord.Interaction):
            if not interaction_or_message.response.is_done():
                await interaction_or_message.response.edit_message(embed=embed, view=self)
            else:
                await interaction_or_message.edit_original_response(embed=embed, view=self)
        else:
            await interaction_or_message.edit(embed=embed, view=self)

    async def search_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id and self.action_type == "fa":
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        modal = SearchModal(self)
        await interaction.response.send_modal(modal)
        
    async def prev_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id and self.action_type == "fa":
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        self.current_page -= 1
        await self.update_view(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id and self.action_type == "fa":
            return await interaction.response.send_message("Not your menu.", ephemeral=True)
        self.current_page += 1
        await self.update_view(interaction)

    async def select_callback(self, interaction: discord.Interaction):
        if self.action_type == "fa":
            if interaction.user.id != self.ctx.author.id:
                return await interaction.response.send_message("Not your menu.", ephemeral=True)
            await self.cog.handle_fa_pickup(interaction, self, int(interaction.data['values'][0]))
        else:
            await self.cog.handle_draft_pick(interaction, self, int(interaction.data['values'][0]))

    async def on_timeout(self):
        for child in self.children: child.disabled = True
        try:
            if self.message: await self.message.edit(view=self)
        except: pass

class TeamManagementView(discord.ui.View):
    def __init__(self, cog, ctx, team_players, rosters_dict, scoring_system):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.rosters_dict = rosters_dict
        self.scoring_system = scoring_system
        self.message = None
        
        if not team_players: return
            
        options = []
        for p in team_players[:25]:
            joined_fp = self.rosters_dict.get(str(p['id']), 0)
            earned_fp = calculate_fp(p, self.scoring_system) - joined_fp
            options.append(discord.SelectOption(
                label=f"{p['name']} ({p['pos']})",
                description=f"{p['team']} - Earned FP: {round(earned_fp, 1)}",
                value=str(p['id'])
            ))
            
        select = discord.ui.Select(placeholder="Select a player to DROP...", options=options, custom_id="drop_select")
        select.callback = self.drop_callback
        self.add_item(select)

    async def drop_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id: return await interaction.response.send_message("Not your menu.", ephemeral=True)
        player_id = int(interaction.data['values'][0])
        uid_str = str(self.ctx.author.id)
        
        async with self.cog.config.guild(self.ctx.guild).rosters() as rosters:
            if uid_str in rosters and str(player_id) in rosters[uid_str]:
                joined_fp = rosters[uid_str].pop(str(player_id))
                player = next((p for p in self.cog.players_cache if p['id'] == player_id), None)
                if player:
                    earned_fp = calculate_fp(player, self.scoring_system) - joined_fp
                    async with self.cog.config.guild(self.ctx.guild).scores() as scores:
                        scores[uid_str] = scores.get(uid_str, 0.0) + earned_fp
                await interaction.response.send_message("Player dropped successfully.", ephemeral=True)
                for child in self.children: child.disabled = True
                await interaction.message.edit(view=self)
            else:
                await interaction.response.send_message("Failed to drop player.", ephemeral=True)

class TradeProposalView(discord.ui.View):
    def __init__(self, cog, ctx, target_member, proposer_players, target_players):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.target_member = target_member
        self.proposer_players = proposer_players
        self.target_players = target_players
        self.give_id = None
        self.receive_id = None
        self.message = None
        
        give_options = [discord.SelectOption(label=f"{p['name']} ({p['pos']})", value=str(p['id'])) for p in proposer_players]
        self.give_select = discord.ui.Select(placeholder="Select player to GIVE...", options=give_options, custom_id="give_select")
        self.give_select.callback = self.give_callback
        self.add_item(self.give_select)
        
        receive_options = [discord.SelectOption(label=f"{p['name']} ({p['pos']})", value=str(p['id'])) for p in target_players]
        self.receive_select = discord.ui.Select(placeholder="Select player to RECEIVE...", options=receive_options, custom_id="receive_select")
        self.receive_select.callback = self.receive_callback
        self.add_item(self.receive_select)
        
        self.propose_btn = discord.ui.Button(label="Propose Trade", style=discord.ButtonStyle.success, disabled=True)
        self.propose_btn.callback = self.propose_callback
        self.add_item(self.propose_btn)
        
    async def give_callback(self, interaction):
        if interaction.user.id != self.ctx.author.id: return await interaction.response.send_message("Not your menu.", ephemeral=True)
        self.give_id = int(interaction.data['values'][0])
        self.check_ready()
        await interaction.response.edit_message(view=self)
        
    async def receive_callback(self, interaction):
        if interaction.user.id != self.ctx.author.id: return await interaction.response.send_message("Not your menu.", ephemeral=True)
        self.receive_id = int(interaction.data['values'][0])
        self.check_ready()
        await interaction.response.edit_message(view=self)
        
    def check_ready(self):
        if self.give_id and self.receive_id:
            self.propose_btn.disabled = False
            
    async def propose_callback(self, interaction):
        if interaction.user.id != self.ctx.author.id: return await interaction.response.send_message("Not your menu.", ephemeral=True)
        
        give_player = next(p for p in self.proposer_players if p['id'] == self.give_id)
        receive_player = next(p for p in self.target_players if p['id'] == self.receive_id)
        
        for child in self.children: child.disabled = True
        await interaction.message.edit(view=self)
        
        embed = discord.Embed(title="Trade Offer!", description=f"{interaction.user.mention} has proposed a trade to {self.target_member.mention}.", color=discord.Color.gold())
        embed.add_field(name=f"{interaction.user.display_name} Receives:", value=f"**{receive_player['name']}**")
        embed.add_field(name=f"{self.target_member.display_name} Receives:", value=f"**{give_player['name']}**")
        
        view = TradeAcceptView(self.cog, self.ctx.author, self.target_member, self.give_id, self.receive_id)
        msg = await interaction.channel.send(content=self.target_member.mention, embed=embed, view=view)
        view.message = msg
        await interaction.response.send_message("Trade proposed!", ephemeral=True)

class TradeAcceptView(discord.ui.View):
    def __init__(self, cog, proposer, target, give_id, receive_id):
        super().__init__(timeout=86400)
        self.cog = cog
        self.proposer = proposer
        self.target = target
        self.give_id = give_id
        self.receive_id = receive_id
        self.message = None
        
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept_btn(self, interaction, button):
        if interaction.user.id != self.target.id: return await interaction.response.send_message("Only the target can accept this trade.", ephemeral=True)
        
        guild = interaction.guild
        rosters = await self.cog.config.guild(guild).rosters()
        scoring_system = await self.cog.config.guild(guild).scoring_system()
        slots = await self.cog.config.guild(guild).team_slots()
        
        p_uid = str(self.proposer.id)
        t_uid = str(self.target.id)
        
        if p_uid not in rosters or t_uid not in rosters:
            return await interaction.response.send_message("One of the users is no longer in the league.", ephemeral=True)
            
        if str(self.give_id) not in rosters[p_uid] or str(self.receive_id) not in rosters[t_uid]:
            return await interaction.response.send_message("The players are no longer on the respective rosters!", ephemeral=True)
            
        p_current_ids = [int(pid) for pid in rosters[p_uid].keys() if pid != str(self.give_id)] + [self.receive_id]
        t_current_ids = [int(pid) for pid in rosters[t_uid].keys() if pid != str(self.receive_id)] + [self.give_id]
        
        p_players = [p for p in self.cog.players_cache if p['id'] in p_current_ids]
        t_players = [p for p in self.cog.players_cache if p['id'] in t_current_ids]
        
        if not can_fit_roster(p_players, slots):
            return await interaction.response.send_message(f"Trade invalid: {self.proposer.display_name} cannot fit the received player in their positional slots.", ephemeral=True)
        if not can_fit_roster(t_players, slots):
            return await interaction.response.send_message(f"Trade invalid: You cannot fit the received player in your positional slots.", ephemeral=True)
            
        async with self.cog.config.guild(guild).rosters() as r:
            give_player = next((p for p in self.cog.players_cache if p['id'] == self.give_id), None)
            receive_player = next((p for p in self.cog.players_cache if p['id'] == self.receive_id), None)
            
            p_joined_fp = r[p_uid].pop(str(self.give_id))
            t_joined_fp = r[t_uid].pop(str(self.receive_id))
            
            if give_player and receive_player:
                p_earned = calculate_fp(give_player, scoring_system) - p_joined_fp
                t_earned = calculate_fp(receive_player, scoring_system) - t_joined_fp
                
                async with self.cog.config.guild(guild).scores() as scores:
                    scores[p_uid] = scores.get(p_uid, 0.0) + p_earned
                    scores[t_uid] = scores.get(t_uid, 0.0) + t_earned
                    
            r[p_uid][str(self.receive_id)] = calculate_fp(receive_player, scoring_system)
            r[t_uid][str(self.give_id)] = calculate_fp(give_player, scoring_system)
            
        for child in self.children: child.disabled = True
        await interaction.message.edit(content="✅ Trade Accepted and Processed!", view=self)
        await interaction.response.send_message("Trade successful.", ephemeral=True)
        
    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_btn(self, interaction, button):
        if interaction.user.id != self.target.id: return await interaction.response.send_message("Only the target can decline this trade.", ephemeral=True)
        for child in self.children: child.disabled = True
        await interaction.message.edit(content="❌ Trade Declined.", view=self)
        await interaction.response.send_message("Trade declined.", ephemeral=True)


class NBAFantasy(commands.Cog):
    """Advanced NBA Fantasy League within Discord!"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=928374928375, force_registration=True)
        
        default_guild = {
            "is_active": False,
            "fa_locked": False,
            "rosters": {},
            "scores": {},
            "team_slots": ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL", "UTIL", "UTIL"],
            "scoring_system": {
                "pts": 1.0, "reb": 1.2, "ast": 1.5, "stl": 3.0, "blk": 3.0, "tov": -1.0
            },
            "draft_state": {
                "is_active": False,
                "order": [],
                "current_pick": 0,
                "picks": []
            }
        }
        default_global = {
            "players_cache": []
        }
        
        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
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
                await asyncio.sleep(43200) # 12 hours
            except Exception as e:
                self.last_fetch_error = str(e)
                print(f"[NBAFantasy] Error fetching NBA stats: {e}")
                await asyncio.sleep(300) # 5 mins

    def _setup_session(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        })

    async def _fetch_players(self):
        def fetch():
            base_url = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/statistics/byathlete?region=us&lang=en&contentorigin=espn&isqualified=false&limit=500"
            players_data = []
            page = 1
            max_pages = 1
            
            while page <= max_pages:
                try:
                    response = self._session.get(f"{base_url}&page={page}", timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    
                    if page == 1 and "pagination" in data:
                        max_pages = data["pagination"].get("pages", 1)
                        
                    players_data.extend(data.get("athletes", []))
                    page += 1
                    time.sleep(1)
                except Exception as e:
                    print(f"[NBAFantasy] ESPN API fetch failed on page {page}: {e}")
                    raise e
                    
            return players_data
            
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, fetch)
        
        cached = []
        for p in data:
            athlete = p.get("athlete", {})
            try:
                player_id = int(athlete.get("id", 0))
            except ValueError:
                continue
                
            name = athlete.get("displayName", "Unknown Player")
            team = athlete.get("teamShortName", "FA")
            pos = athlete.get("position", {}).get("abbreviation", "UTIL")
            
            # Check for injury status
            status_text = athlete.get("status", {}).get("type", "active")
            is_out = status_text.lower() in ["out", "day-to-day", "injured", "suspended"]
            
            categories = p.get("categories", [])
            pts = reb = ast = stl = blk = tov = 0.0
            
            for cat in categories:
                cat_name = cat.get("name")
                names = cat.get("names", [])
                values = cat.get("values", [])
                
                if cat_name == "offensive":
                    if "points" in names: pts = float(values[names.index("points")])
                    if "rebounds" in names: reb = float(values[names.index("rebounds")])
                    if "assists" in names: ast = float(values[names.index("assists")])
                    if "turnovers" in names: tov = float(values[names.index("turnovers")])
                elif cat_name == "defensive":
                    if "steals" in names: stl = float(values[names.index("steals")])
                    if "blocks" in names: blk = float(values[names.index("blocks")])
                    
            pts = max(0, pts)
            reb = max(0, reb)
            ast = max(0, ast)
            
            cached.append({
                "id": player_id,
                "name": name,
                "team": team,
                "pos": pos,
                "pts": round(pts, 1),
                "reb": round(reb, 1),
                "ast": round(ast, 1),
                "stl": round(stl, 1),
                "blk": round(blk, 1),
                "tov": round(tov, 1),
                "out": is_out
            })
        
        self.players_cache = cached

    @commands.group(name="fantasy", aliases=["nbafantasy", "nbaf"])
    async def fantasy(self, ctx):
        """Advanced NBA Fantasy League!"""
        pass

    @fantasy.command(name="guide")
    async def fantasy_guide(self, ctx):
        """Show a guide on how to play NBA Fantasy."""
        guide_text = (
            "🏀 **NBA Fantasy Guide** 🏀\n\n"
            "**1. Joining the League**\n"
            "Use `[p]fantasy join` to enter the server's fantasy league. "
            "Once joined, you'll need to build a roster by drafting or picking up players.\n\n"
            "**2. The Draft**\n"
            "Admins can set up a draft using `[p]fantasy draft setup`. During a draft, players are selected "
            "one by one. Use `[p]fantasy draft board` to see who's available and make your selection when it's your turn.\n\n"
            "**3. Managing Your Team**\n"
            "Use `[p]fantasy team` to view your current roster. You can drop players to make room for new ones. "
            "Your team must fit into specific positional slots (PG, SG, etc.), which you can view with `[p]fantasy settings`.\n\n"
            "**4. Free Agency**\n"
            "When the draft is over, any unpicked players become Free Agents. Use `[p]fantasy freeagents` to "
            "browse and add them to your team.\n\n"
            "**5. Trading**\n"
            "Trade players with other managers using `[p]fantasy trade @user`. Both parties must have "
            "valid roster space for the trade to be processed.\n\n"
            "**6. Scoring**\n"
            "Points are earned based on real-life NBA stats. You earn 'Earned FP' from the moment a player "
            "joins your roster. Check the standings with `[p]fantasy standings`!"
        )
        embed = discord.Embed(title="NBA Fantasy Player Guide", description=guide_text, color=discord.Color.green())
        await ctx.send(embed=embed)

    @fantasy.command(name="setup")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_setup(self, ctx):
        """Enable NBA Fantasy in this server."""
        await self.config.guild(ctx.guild).is_active.set(True)
        await ctx.send("🏀 NBA Fantasy has been enabled for this server! Users can now `[p]fantasy join`.")

    @fantasy.command(name="settings")
    async def fantasy_settings(self, ctx):
        """View the current league settings."""
        slots = await self.config.guild(ctx.guild).team_slots()
        scoring = await self.config.guild(ctx.guild).scoring_system()
        
        embed = discord.Embed(title="NBA Fantasy Settings", color=discord.Color.blurple())
        embed.add_field(name="Roster Slots", value=", ".join(slots), inline=False)
        
        score_str = "\n".join([f"**{k.upper()}**: {v}" for k, v in scoring.items()])
        embed.add_field(name="Scoring System", value=score_str, inline=False)
        
        await ctx.send(embed=embed)

    @fantasy.command(name="setslots")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_setslots(self, ctx, *slots: str):
        """Set the required positional slots for a team.
        Example: [p]fantasy setslots PG SG SF PF C UTIL UTIL
        Valid options: PG, SG, SF, PF, C, G, F, UTIL"""
        if not slots:
            return await ctx.send_help(ctx.command)
        valid = set(VALID_SLOTS.keys())
        slots = [s.upper() for s in slots]
        for s in slots:
            if s not in valid:
                return await ctx.send(f"Invalid slot '{s}'. Valid slots are: {', '.join(valid)}")
        await self.config.guild(ctx.guild).team_slots.set(slots)
        await ctx.send(f"✅ Roster slots updated! Teams now consist of {len(slots)} players: {', '.join(slots)}")

    @fantasy.command(name="setscoring")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_setscoring(self, ctx, stat: str, value: float):
        """Set the point value for a specific stat.
        Example: [p]fantasy setscoring pts 1.0"""
        stat = stat.lower()
        async with self.config.guild(ctx.guild).scoring_system() as scoring:
            if stat not in scoring:
                return await ctx.send(f"Invalid stat. Valid stats: {', '.join(scoring.keys())}")
            scoring[stat] = value
        await ctx.send(f"✅ Scoring updated: **{stat.upper()}** is now worth **{value}** FP.")

    @fantasy.command(name="join")
    async def fantasy_join(self, ctx):
        """Join the server's NBA Fantasy league."""
        is_active = await self.config.guild(ctx.guild).is_active()
        if not is_active: return await ctx.send("League is not active.")
            
        async with self.config.guild(ctx.guild).rosters() as rosters:
            uid_str = str(ctx.author.id)
            if uid_str in rosters: return await ctx.send("You have already joined!")
            rosters[uid_str] = {}
            
        async with self.config.guild(ctx.guild).scores() as scores:
            scores[str(ctx.author.id)] = 0.0
            
        await ctx.send("🎉 You have successfully joined the fantasy league!")

    @fantasy.command(name="team")
    async def fantasy_team(self, ctx, member: discord.Member = None):
        """View your team or another member's team."""
        target = member or ctx.author
        uid_str = str(target.id)
        
        rosters = await self.config.guild(ctx.guild).rosters()
        if uid_str not in rosters:
            return await ctx.send("This user hasn't joined the league yet.")
            
        if not self.players_cache:
            return await ctx.send("Player data is updating. Please try again later.")
            
        player_dict = rosters[uid_str]
        if isinstance(player_dict, list):
            async with self.config.guild(ctx.guild).rosters() as r: r[uid_str] = {}
            player_dict = {}
            
        player_ids = [int(pid) for pid in player_dict.keys()]
        team_players = [p for p in self.players_cache if p['id'] in player_ids]
        
        scores = await self.config.guild(ctx.guild).scores()
        scoring_system = await self.config.guild(ctx.guild).scoring_system()
        slots = await self.config.guild(ctx.guild).team_slots()
        
        accumulated_fp = scores.get(uid_str, 0.0)
        
        embed = discord.Embed(title=f"{target.display_name}'s Fantasy Team", color=discord.Color.orange())
        embed.set_thumbnail(url=target.display_avatar.url)
        
        if not team_players:
            embed.description = f"**Total Team FP:** {round(accumulated_fp, 1)}\n\nTeam is empty!"
            return await ctx.send(embed=embed)
            
        current_roster_fp = 0
        assigned = assign_slots(team_players, slots)
        
        for slot, p in assigned:
            if p:
                joined_fp = player_dict.get(str(p['id']), calculate_fp(p, scoring_system))
                earned_fp = calculate_fp(p, scoring_system) - joined_fp
                current_roster_fp += earned_fp
                status_mark = "🏥 " if p.get('out', False) else ""
                embed.add_field(name=f"[{slot}] {status_mark}{p['name']} ({p['pos']})", value=f"{p['team']} | Earned FP: {round(earned_fp, 1)}", inline=False)
            else:
                embed.add_field(name=f"[{slot}] EMPTY", value="--", inline=False)
            
        total_team_fp = accumulated_fp + current_roster_fp
        
        if target == ctx.author:
            embed.description = f"**Total Team FP:** {round(total_team_fp, 1)}\n*Use the dropdown below to drop a player.*"
            view = TeamManagementView(self, ctx, team_players, player_dict, scoring_system)
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
        else:
            embed.description = f"**Total Team FP:** {round(total_team_fp, 1)}"
            await ctx.send(embed=embed)

    @fantasy.group(name="draft")
    async def fantasy_draft(self, ctx):
        """Draft management commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)
        
    @fantasy_draft.command(name="setup")
    @commands.admin_or_permissions(manage_guild=True)
    async def draft_setup(self, ctx, *members: discord.Member):
        """Setup the draft order (snake draft).
        Example: [p]fantasy draft setup @user1 @user2 @user3"""
        if not members: return await ctx.send("Please mention at least one member.")
        
        slots = await self.config.guild(ctx.guild).team_slots()
        num_rounds = len(slots)
        
        base_order = [str(m.id) for m in members]
        full_order = []
        for r in range(num_rounds):
            if r % 2 == 0:
                full_order.extend(base_order)
            else:
                full_order.extend(reversed(base_order))
                
        async with self.config.guild(ctx.guild).draft_state() as state:
            state['order'] = full_order
            state['current_pick'] = 0
            state['picks'] = []
            state['is_active'] = False
            
        names = [m.display_name for m in members]
        await ctx.send(f"✅ Draft order configured for {len(members)} players and {num_rounds} rounds!\nOrder: {', '.join(names)}\n\nUse `[p]fantasy draft start` to begin.")

    @fantasy_draft.command(name="start")
    @commands.admin_or_permissions(manage_guild=True)
    async def draft_start(self, ctx):
        """Start the draft."""
        async with self.config.guild(ctx.guild).draft_state() as state:
            if not state['order']: return await ctx.send("Draft order not set! Use `[p]fantasy draft setup` first.")
            state['is_active'] = True
            first_user_id = state['order'][state['current_pick']]
            
        await self.config.guild(ctx.guild).fa_locked.set(True)
        first_user = ctx.guild.get_member(int(first_user_id))
        mention = first_user.mention if first_user else f"<@{first_user_id}>"
        await ctx.send(f"🎉 **The Draft has begun!** Free agency is locked.\n📢 {mention}, you are on the clock! Use `[p]fantasy draft board` to make your pick.")

    @fantasy_draft.command(name="stop")
    @commands.admin_or_permissions(manage_guild=True)
    async def draft_stop(self, ctx):
        """Stop the draft early."""
        async with self.config.guild(ctx.guild).draft_state() as state:
            state['is_active'] = False
        await ctx.send("🛑 Draft has been stopped.")

    @fantasy_draft.command(name="board")
    async def draft_board(self, ctx):
        """View the draft board and pick players."""
        state = await self.config.guild(ctx.guild).draft_state()
        if not state['is_active']:
            return await ctx.send("Draft is not currently active.")
            
        rosters = await self.config.guild(ctx.guild).rosters()
        taken_ids = set()
        for team_dict in rosters.values():
            if isinstance(team_dict, dict):
                taken_ids.update(int(pid) for pid in team_dict.keys())
                
        available_players = [p for p in self.players_cache if p['id'] not in taken_ids]
        scoring_system = await self.config.guild(ctx.guild).scoring_system()
        slots = await self.config.guild(ctx.guild).team_slots()
        
        embed = discord.Embed(
            title="Draft Board", 
            description=f"Select a player from the dropdown to draft them.\n**Current Pick: #{state['current_pick']+1}** (<@{state['order'][state['current_pick']]}>'s turn)", 
            color=discord.Color.green()
        )
        
        view = PlayerListPagination(self, ctx, available_players, scoring_system, slots, action_type="draft")
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        await view.update_view(msg)

    @fantasy.command(name="trade")
    async def fantasy_trade(self, ctx, member: discord.Member):
        """Propose a trade with another member."""
        if member == ctx.author: return await ctx.send("You cannot trade with yourself.")
        
        rosters = await self.config.guild(ctx.guild).rosters()
        p_uid = str(ctx.author.id)
        t_uid = str(member.id)
        
        if p_uid not in rosters or t_uid not in rosters:
            return await ctx.send("Both users must be in the league.")
            
        p_pids = [int(pid) for pid in rosters[p_uid].keys()]
        t_pids = [int(pid) for pid in rosters[t_uid].keys()]
        
        if not p_pids or not t_pids:
            return await ctx.send("Both users must have at least one player to trade.")
            
        p_players = [p for p in self.players_cache if p['id'] in p_pids]
        t_players = [p for p in self.players_cache if p['id'] in t_pids]
        
        embed = discord.Embed(title="Propose Trade", description="Select one player to give and one to receive.", color=discord.Color.purple())
        view = TradeProposalView(self, ctx, member, p_players, t_players)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @fantasy.command(name="freeagents", aliases=["fa"])
    async def fantasy_freeagents(self, ctx):
        """Browse and pick up available free agents."""
        fa_locked = await self.config.guild(ctx.guild).fa_locked()
        if fa_locked: return await ctx.send("🔒 Free Agency is currently locked.")
            
        rosters = await self.config.guild(ctx.guild).rosters()
        if str(ctx.author.id) not in rosters: return await ctx.send("You haven't joined yet.")
            
        taken_ids = set()
        for team_dict in rosters.values():
            if isinstance(team_dict, dict): taken_ids.update(int(pid) for pid in team_dict.keys())
            
        available_players = [p for p in self.players_cache if p['id'] not in taken_ids]
        scoring_system = await self.config.guild(ctx.guild).scoring_system()
        slots = await self.config.guild(ctx.guild).team_slots()
        
        embed = discord.Embed(title="Free Agents", description="Select a player from the dropdown to add to your team.", color=discord.Color.blue())
        view = PlayerListPagination(self, ctx, available_players, scoring_system, slots, action_type="fa")
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        await view.update_view(msg)

    async def handle_fa_pickup(self, interaction, view, player_id):
        fa_locked = await self.config.guild(interaction.guild).fa_locked()
        if fa_locked: return await interaction.response.send_message("Free Agency is currently locked.", ephemeral=True)
            
        uid_str = str(interaction.user.id)
        scoring_system = await self.config.guild(interaction.guild).scoring_system()
        slots = await self.config.guild(interaction.guild).team_slots()
        
        async with self.config.guild(interaction.guild).rosters() as rosters:
            if len(rosters[uid_str]) >= len(slots):
                return await interaction.response.send_message(f"Your roster is full (max {len(slots)}).", ephemeral=True)
                
            for team_dict in rosters.values():
                if str(player_id) in team_dict:
                    return await interaction.response.send_message("Player is already on another team!", ephemeral=True)
                    
            player = next((p for p in self.players_cache if p['id'] == player_id), None)
            
            current_player_ids = [int(pid) for pid in rosters[uid_str].keys()]
            current_players = [p for p in self.players_cache if p['id'] in current_player_ids]
            current_players.append(player)
            
            if not can_fit_roster(current_players, slots):
                return await interaction.response.send_message(f"Cannot add {player['name']} because they do not fit your positional slots {slots}.", ephemeral=True)
                
            rosters[uid_str][str(player_id)] = calculate_fp(player, scoring_system)
            
            await interaction.response.send_message(f"**{player['name']}** added successfully!", ephemeral=True)
            for child in view.children: child.disabled = True
            if not interaction.response.is_done():
                await interaction.response.edit_message(view=view)
            else:
                await interaction.message.edit(view=view)

    async def handle_draft_pick(self, interaction, view, player_id):
        uid_str = str(interaction.user.id)
        
        async with self.config.guild(interaction.guild).draft_state() as draft_state:
            if not draft_state.get('is_active'): return await interaction.response.send_message("Draft is not active.", ephemeral=True)
            order = draft_state['order']
            current_pick = draft_state['current_pick']
            if current_pick >= len(order): return await interaction.response.send_message("Draft is already over!", ephemeral=True)
            if order[current_pick] != uid_str:
                return await interaction.response.send_message("It is not your turn!", ephemeral=True)
                
            rosters = await self.config.guild(interaction.guild).rosters()
            scoring_system = await self.config.guild(interaction.guild).scoring_system()
            slots = await self.config.guild(interaction.guild).team_slots()
            
            for team_dict in rosters.values():
                if str(player_id) in team_dict:
                    return await interaction.response.send_message("Player is already on another team!", ephemeral=True)
                    
            player = next((p for p in self.players_cache if p['id'] == player_id), None)
            
            user_roster = rosters.get(uid_str, {})
            current_player_ids = [int(pid) for pid in user_roster.keys()]
            current_players = [p for p in self.players_cache if p['id'] in current_player_ids]
            current_players.append(player)
            
            if not can_fit_roster(current_players, slots):
                return await interaction.response.send_message(f"Cannot draft {player['name']} because they do not fit your positional slots {slots}.", ephemeral=True)
                
            async with self.config.guild(interaction.guild).rosters() as r:
                if uid_str not in r: r[uid_str] = {}
                r[uid_str][str(player_id)] = calculate_fp(player, scoring_system)
                
            draft_state['picks'].append({
                "pick_number": current_pick + 1,
                "user_id": uid_str,
                "player_id": player_id,
                "player_name": player['name']
            })
            
            draft_state['current_pick'] += 1
            next_pick = draft_state['current_pick']
            
            await interaction.response.send_message(f"You drafted **{player['name']}**!", ephemeral=False)
            
            if next_pick >= len(order):
                draft_state['is_active'] = False
                await interaction.channel.send("🎉 **The Draft has concluded!** Free Agency is now open (unless locked by admins).")
            else:
                next_user_id = order[next_pick]
                next_user = interaction.guild.get_member(int(next_user_id))
                mention = next_user.mention if next_user else f"<@{next_user_id}>"
                await interaction.channel.send(f"📢 {mention}, you are on the clock! Pick #{next_pick + 1}")
                
            for child in view.children: child.disabled = True
            await interaction.message.edit(view=view)

    @fantasy.command(name="standings")
    async def fantasy_standings(self, ctx):
        """View the league standings."""
        rosters = await self.config.guild(ctx.guild).rosters()
        if not rosters: return await ctx.send("No one has joined the league yet.")
            
        scoring_system = await self.config.guild(ctx.guild).scoring_system()
        scores = await self.config.guild(ctx.guild).scores()
        leaderboard = []
        
        for uid_str, player_dict in rosters.items():
            if isinstance(player_dict, list): continue
            team_players = [p for p in self.players_cache if p['id'] in [int(pid) for pid in player_dict.keys()]]
            current_roster_fp = sum(calculate_fp(p, scoring_system) - player_dict.get(str(p['id']), 0) for p in team_players)
            total_fp = scores.get(uid_str, 0.0) + current_roster_fp
            
            best_player = None
            if team_players:
                best_player = max(team_players, key=lambda p: calculate_fp(p, scoring_system) - player_dict.get(str(p['id']), 0))
            leaderboard.append((uid_str, round(total_fp, 1), best_player, player_dict))
            
        leaderboard.sort(key=lambda x: x[1], reverse=True)
        embed = discord.Embed(title="🏆 NBA Fantasy Standings", color=discord.Color.gold())
        
        for idx, (uid_str, score, best_player, player_dict) in enumerate(leaderboard, 1):
            user = ctx.guild.get_member(int(uid_str))
            name = user.display_name if user else f"User {uid_str}"
            
            top_player_str = ""
            if best_player:
                earned_fp = calculate_fp(best_player, scoring_system) - player_dict.get(str(best_player['id']), 0)
                top_player_str = f"\n*MVP: {best_player['name']} (+{round(earned_fp, 1)} FP)*"
                
            embed.add_field(name=f"{idx}. {name}", value=f"**{score}** Fantasy Points{top_player_str}", inline=False)
            
        await ctx.send(embed=embed)

    @fantasy.command(name="lock")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_lock(self, ctx):
        await self.config.guild(ctx.guild).fa_locked.set(True)
        await ctx.send("🔒 Free Agency locked.")

    @fantasy.command(name="unlock")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_unlock(self, ctx):
        """Unlock free agency so players can be picked up."""
        await self.config.guild(ctx.guild).fa_locked.set(False)
        await ctx.send("🔓 Free Agency unlocked.")

    @fantasy.command(name="remove")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_remove(self, ctx, member: discord.Member):
        """Remove a member's team from the fantasy league."""
        uid_str = str(member.id)
        async with self.config.guild(ctx.guild).rosters() as rosters:
            if uid_str in rosters: del rosters[uid_str]
        async with self.config.guild(ctx.guild).scores() as scores:
            if uid_str in scores: del scores[uid_str]
        await ctx.send(f"🗑️ Removed **{member.display_name}**.")

    @fantasy.command(name="reset")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_reset(self, ctx):
        """Reset the fantasy league completely (rosters, scores, drafts)."""
        await ctx.send("⚠️ Type `yes` to confirm complete reset.")
        def check(m): return m.author == ctx.author and m.channel == ctx.channel
        try:
            msg = await self.bot.wait_for("message", check=check, timeout=30.0)
            if msg.content.lower() == "yes":
                await self.config.guild(ctx.guild).rosters.set({})
                await self.config.guild(ctx.guild).scores.set({})
                await self.config.guild(ctx.guild).draft_state.set({"is_active": False, "order": [], "current_pick": 0, "picks": []})
                await ctx.send("🔄 Reset complete.")
            else:
                await ctx.send("Cancelled.")
        except asyncio.TimeoutError:
            await ctx.send("Timeout.")

    @fantasy.command(name="update")
    @commands.is_owner()
    async def fantasy_update(self, ctx):
        """Force an update of NBA player stats manually."""
        msg = await ctx.send("🏀 Fetching stats...")
        try:
            await self._fetch_players()
            await self.config.players_cache.set(self.players_cache)
            self.last_fetch_error = None
            await ctx.send(f"✅ Updated {len(self.players_cache)} players!")
        except Exception as e:
            self.last_fetch_error = str(e)
            await ctx.send(f"❌ Failed: {e}")

    @fantasy.command(name="player")
    async def fantasy_player(self, ctx, *, name: str):
        """View a specific player's real-life stats and fantasy points."""
        if not self.players_cache:
            return await ctx.send("Player data is updating. Please try again later.")
        
        matches = [p for p in self.players_cache if name.lower() in p['name'].lower()]
        if not matches:
            return await ctx.send(f"No player found matching '{name}'.")
            
        scoring_system = await self.config.guild(ctx.guild).scoring_system()
        player = matches[0]
        fp = calculate_fp(player, scoring_system)
        
        status = " [OUT]" if player.get('out', False) else ""
        embed = discord.Embed(title=f"{player['name']} ({player['pos']}){status}", description=f"Team: **{player['team']}**", color=discord.Color.blue())
        embed.add_field(name="Fantasy Points (FP)", value=f"**{fp}**", inline=False)
        embed.add_field(name="Points (PTS)", value=player['pts'], inline=True)
        embed.add_field(name="Rebounds (REB)", value=player['reb'], inline=True)
        embed.add_field(name="Assists (AST)", value=player['ast'], inline=True)
        embed.add_field(name="Steals (STL)", value=player['stl'], inline=True)
        embed.add_field(name="Blocks (BLK)", value=player['blk'], inline=True)
        embed.add_field(name="Turnovers (TOV)", value=player['tov'], inline=True)
        
        await ctx.send(embed=embed)

    @fantasy.command(name="forceadd")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_forceadd(self, ctx, member: discord.Member, *, player_name: str):
        """Admin command to force add a player to a member's roster."""
        uid_str = str(member.id)
        rosters = await self.config.guild(ctx.guild).rosters()
        if uid_str not in rosters:
            return await ctx.send("That member hasn't joined the fantasy league.")
            
        matches = [p for p in self.players_cache if player_name.lower() in p['name'].lower()]
        if not matches:
            return await ctx.send(f"No player found matching '{player_name}'.")
            
        player = matches[0]
        player_id = str(player['id'])
        
        for team_dict in rosters.values():
            if player_id in team_dict:
                return await ctx.send(f"{player['name']} is already on another team!")
                
        scoring_system = await self.config.guild(ctx.guild).scoring_system()
        async with self.config.guild(ctx.guild).rosters() as r:
            r[uid_str][player_id] = calculate_fp(player, scoring_system)
            
        await ctx.send(f"✅ Successfully force-added **{player['name']}** to **{member.display_name}**'s roster.")

    @fantasy.command(name="forcedrop")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_forcedrop(self, ctx, member: discord.Member, *, player_name: str):
        """Admin command to force drop a player from a member's roster."""
        uid_str = str(member.id)
        rosters = await self.config.guild(ctx.guild).rosters()
        if uid_str not in rosters:
            return await ctx.send("That member hasn't joined the fantasy league.")
            
        team_dict = rosters[uid_str]
        team_pids = [int(pid) for pid in team_dict.keys()]
        team_players = [p for p in self.players_cache if p['id'] in team_pids]
        
        matches = [p for p in team_players if player_name.lower() in p['name'].lower()]
        if not matches:
            return await ctx.send(f"No player found matching '{player_name}' on that roster.")
            
        player = matches[0]
        player_id = str(player['id'])
        
        async with self.config.guild(ctx.guild).rosters() as r:
            joined_fp = r[uid_str].pop(player_id)
            scoring_system = await self.config.guild(ctx.guild).scoring_system()
            earned_fp = calculate_fp(player, scoring_system) - joined_fp
            
            async with self.config.guild(ctx.guild).scores() as scores:
                scores[uid_str] = scores.get(uid_str, 0.0) + earned_fp
                
        await ctx.send(f"✅ Successfully force-dropped **{player['name']}** from **{member.display_name}**'s roster. They kept their earned {round(earned_fp, 1)} FP.")
