import discord
from redbot.core import commands, Config
import asyncio
import time
import requests
import math
from collections import Counter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SLOTS = {
    "PG":   ["PG", "G", "UTIL"],
    "SG":   ["SG", "G", "UTIL", "SF"],
    "SF":   ["SF", "F", "UTIL", "SG", "PF"],
    "PF":   ["PF", "F", "UTIL", "SF", "C"],
    "C":    ["C", "UTIL", "PF", "F"],
    "G":    ["PG", "SG", "G", "UTIL"],
    "F":    ["SF", "PF", "F", "UTIL", "C"],
    "UTIL": ["UTIL"],
}

STAT_LABELS = {
    "pts": "Points (PTS)",
    "reb": "Rebounds (REB)",
    "ast": "Assists (AST)",
    "stl": "Steals (STL)",
    "blk": "Blocks (BLK)",
    "tov": "Turnovers (TOV)",
}

SLOT_DISPLAY_ORDER = ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def can_fit_roster(players, slots):
    """Backtracking check: can all players fit into the available slots?"""
    if len(players) > len(slots):
        return False
    reqs = [set(VALID_SLOTS.get(p.get("pos", "UTIL"), ["UTIL"])) for p in players]

    def solve(idx, avail):
        if idx == len(players):
            return True
        for i, slot in enumerate(avail):
            if slot in reqs[idx]:
                if solve(idx + 1, avail[:i] + avail[i + 1:]):
                    return True
        return False

    return solve(0, list(slots))


def calculate_fp(player, scoring):
    return round(
        player.get("pts", 0) * scoring.get("pts", 1.0)
        + player.get("reb", 0) * scoring.get("reb", 1.2)
        + player.get("ast", 0) * scoring.get("ast", 1.5)
        + player.get("stl", 0) * scoring.get("stl", 3.0)
        + player.get("blk", 0) * scoring.get("blk", 3.0)
        + player.get("tov", 0) * scoring.get("tov", -1.0),
        1,
    )


def player_status_str(player):
    label = player.get("status_label", "")
    if label:
        return f" [{label}]"
    if player.get("out", False):
        return " [OUT]"
    return ""


def safe_disable(view):
    for child in view.children:
        child.disabled = True


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------

class SearchModal(discord.ui.Modal, title="Search Player"):
    query = discord.ui.TextInput(label="Player Name", style=discord.TextStyle.short, placeholder="e.g. LeBron")

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.search_query = self.query.value.lower()
        self.parent_view.current_page = 0
        await self.parent_view.update_view(interaction)


class ScoringValueModal(discord.ui.Modal, title="Set Scoring Value"):
    value = discord.ui.TextInput(
        label="New Point Value",
        style=discord.TextStyle.short,
        placeholder="e.g. 1.5",
    )

    def __init__(self, cog, ctx, stat):
        super().__init__()
        self.cog = cog
        self.ctx = ctx
        self.stat = stat

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_val = float(self.value.value)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Invalid number. Please enter a decimal value like `1.5`.", ephemeral=True
            )
        async with self.cog.config.guild(self.ctx.guild).scoring_system() as scoring:
            scoring[self.stat] = new_val
        await interaction.response.send_message(
            f"✅ **{self.stat.upper()}** is now worth **{new_val}** FP.", ephemeral=True
        )


# ---------------------------------------------------------------------------
# Player list / FA / Draft browser
# ---------------------------------------------------------------------------

class PlayerListPagination(discord.ui.View):
    """Paginated player browser used for FA pickups, draft picks, and info lookups."""

    def __init__(self, cog, ctx, players, scoring, slots, action_type="fa"):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.all_players = players
        self.scoring = scoring
        self.slots = slots
        self.action_type = action_type   # "fa" | "draft" | "info"
        self.current_page = 0
        self.search_query = ""
        self.message = None
        self.update_items()

    # ── filtering / sorting ────────────────────────────────────────────────

    def get_filtered(self):
        players = self.all_players
        if self.search_query:
            players = [p for p in players if self.search_query in p["name"].lower()]
        return sorted(players, key=lambda p: calculate_fp(p, self.scoring), reverse=True)

    # ── UI rebuild ─────────────────────────────────────────────────────────

    def update_items(self):
        self.clear_items()
        filtered = self.get_filtered()
        max_pages = max(1, math.ceil(len(filtered) / 25))
        self.current_page = max(0, min(self.current_page, max_pages - 1))

        page_players = filtered[self.current_page * 25:(self.current_page + 1) * 25]

        if page_players:
            options = []
            for p in page_players:
                fp = calculate_fp(p, self.scoring)
                emoji = "🏥" if p.get("out") else "🏀"
                status = player_status_str(p)
                label = f"{p['name']} ({p['pos']}){status}"[:100]
                desc = f"{emoji} {p['team']} | FP: {fp} | PTS: {p['pts']}"[:100]
                options.append(discord.SelectOption(label=label, description=desc, value=str(p["id"])))

            placeholders = {
                "fa":    "Select a player to ADD...",
                "draft": "Select a player to DRAFT...",
                "info":  "Select a player to VIEW...",
            }
            sel = discord.ui.Select(
                placeholder=placeholders.get(self.action_type, "Select..."),
                options=options,
                row=0,
            )
            sel.callback = self.select_callback
            self.add_item(sel)

        search_btn = discord.ui.Button(label="🔍 Search", style=discord.ButtonStyle.secondary, row=1)
        search_btn.callback = self.search_callback
        self.add_item(search_btn)

        prev_btn = discord.ui.Button(
            label="◀ Prev", style=discord.ButtonStyle.primary,
            disabled=(self.current_page == 0), row=1,
        )
        prev_btn.callback = self.prev_callback
        self.add_item(prev_btn)

        next_btn = discord.ui.Button(
            label="Next ▶", style=discord.ButtonStyle.primary,
            disabled=(self.current_page >= max_pages - 1), row=1,
        )
        next_btn.callback = self.next_callback
        self.add_item(next_btn)

    # ── embed update ───────────────────────────────────────────────────────

    async def update_view(self, source):
        self.update_items()
        filtered = self.get_filtered()
        max_pages = max(1, math.ceil(len(filtered) / 25))

        if isinstance(source, discord.Interaction):
            embed = source.message.embeds[0]
        else:
            embed = source.embeds[0]

        embed.clear_fields()
        page_players = filtered[self.current_page * 25:(self.current_page + 1) * 25]
        for p in page_players[:10]:
            fp = calculate_fp(p, self.scoring)
            status = player_status_str(p)
            embed.add_field(
                name=f"{p['name']} ({p['pos']}){status}",
                value=f"{p['team']} | **FP: {fp}** | PTS: {p['pts']} REB: {p['reb']} AST: {p['ast']}",
                inline=True,
            )
        embed.set_footer(
            text=f"Page {self.current_page + 1}/{max_pages} | Search: {self.search_query or 'None'} | {len(filtered)} players"
        )

        if isinstance(source, discord.Interaction):
            if not source.response.is_done():
                await source.response.edit_message(embed=embed, view=self)
            else:
                await source.edit_original_response(embed=embed, view=self)
        else:
            await source.edit(embed=embed, view=self)

    # ── callbacks ──────────────────────────────────────────────────────────

    def _is_owner(self, interaction):
        return interaction.user.id == self.ctx.author.id

    async def search_callback(self, interaction: discord.Interaction):
        if self.action_type == "fa" and not self._is_owner(interaction):
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        await interaction.response.send_modal(SearchModal(self))

    async def prev_callback(self, interaction: discord.Interaction):
        if self.action_type == "fa" and not self._is_owner(interaction):
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        self.current_page -= 1
        await self.update_view(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        if self.action_type == "fa" and not self._is_owner(interaction):
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        self.current_page += 1
        await self.update_view(interaction)

    async def select_callback(self, interaction: discord.Interaction):
        player_id = int(interaction.data["values"][0])
        if self.action_type == "fa":
            if not self._is_owner(interaction):
                return await interaction.response.send_message("This is not your menu.", ephemeral=True)
            await self.cog.handle_fa_pickup(interaction, self, player_id)
        elif self.action_type == "draft":
            await self.cog.handle_draft_pick(interaction, self, player_id)
        elif self.action_type == "info":
            await self.cog.handle_player_info(interaction, player_id)

    async def on_timeout(self):
        safe_disable(self)
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Slot assignment
# ---------------------------------------------------------------------------

class SlotSelectionView(discord.ui.View):
    def __init__(self, cog, ctx, player, slots):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.player = player

        pos = player.get("pos", "UTIL")
        allowed = set(VALID_SLOTS.get(pos, ["UTIL"]))
        available = sorted(set(slots).intersection(allowed)) + ["BENCH"]

        options = [discord.SelectOption(label=s, value=s) for s in available]
        sel = discord.ui.Select(placeholder="Choose a slot...", options=options)
        sel.callback = self.slot_callback
        self.add_item(sel)

    async def slot_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        slot = interaction.data["values"][0]
        uid_str = str(self.ctx.author.id)

        async with self.cog.config.guild(self.ctx.guild).assignments() as asgn:
            if uid_str not in asgn:
                asgn[uid_str] = {}
            pid_str = str(self.player["id"])
            if slot == "BENCH":
                asgn[uid_str].pop(pid_str, None)
            else:
                asgn[uid_str][pid_str] = slot

        safe_disable(self)
        await interaction.response.edit_message(
            content=f"✅ **{self.player['name']}** assigned to **{slot}**!", view=self
        )


# ---------------------------------------------------------------------------
# Team management (drop + assign from team view)
# ---------------------------------------------------------------------------

class TeamManagementView(discord.ui.View):
    def __init__(self, cog, ctx, team_players, roster_dict, scoring, slots):
        super().__init__(timeout=180)
        self.cog = cog
        self.ctx = ctx
        self.team_players = team_players
        self.roster_dict = roster_dict
        self.scoring = scoring
        self.slots = slots
        self.message = None

        if not team_players:
            return

        drop_options = []
        for p in team_players[:25]:
            joined_fp = roster_dict.get(str(p["id"]), 0)
            earned = calculate_fp(p, scoring) - joined_fp
            drop_options.append(discord.SelectOption(
                label=f"{p['name']} ({p['pos']})",
                description=f"{p['team']} | Earned: {round(earned, 1)} FP",
                value=str(p["id"]),
            ))
        drop_sel = discord.ui.Select(placeholder="✂️ Drop a player...", options=drop_options, row=0)
        drop_sel.callback = self.drop_callback
        self.add_item(drop_sel)

        assign_options = [
            discord.SelectOption(label=f"{p['name']} ({p['pos']})", value=str(p["id"]))
            for p in team_players[:25]
        ]
        assign_sel = discord.ui.Select(placeholder="📌 Assign player to slot...", options=assign_options, row=1)
        assign_sel.callback = self.assign_callback
        self.add_item(assign_sel)

    async def assign_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        player_id = int(interaction.data["values"][0])
        player = next((p for p in self.team_players if p["id"] == player_id), None)
        if not player:
            return await interaction.response.send_message("Player not found.", ephemeral=True)
        view = SlotSelectionView(self.cog, self.ctx, player, self.slots)
        await interaction.response.send_message(f"Choose a slot for **{player['name']}**:", view=view, ephemeral=True)

    async def drop_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        player_id = int(interaction.data["values"][0])
        uid_str = str(self.ctx.author.id)

        player = next((p for p in self.cog.players_cache if p["id"] == player_id), None)

        async with self.cog.config.guild(self.ctx.guild).rosters() as rosters:
            if uid_str not in rosters or str(player_id) not in rosters[uid_str]:
                return await interaction.response.send_message(
                    "That player is not on your roster.", ephemeral=True
                )
            joined_fp = rosters[uid_str].pop(str(player_id))

        earned_fp = (calculate_fp(player, self.scoring) - joined_fp) if player else 0

        async with self.cog.config.guild(self.ctx.guild).scores() as scores:
            scores[uid_str] = scores.get(uid_str, 0.0) + earned_fp

        # Clear any slot assignment for this player
        async with self.cog.config.guild(self.ctx.guild).assignments() as asgn:
            if uid_str in asgn:
                asgn[uid_str].pop(str(player_id), None)

        if player:
            log_embed = discord.Embed(title="Transaction: Player Dropped", color=discord.Color.red())
            log_embed.add_field(name="User", value=self.ctx.author.mention, inline=True)
            log_embed.add_field(name="Player", value=f"{player['name']} ({player['pos']})", inline=True)
            log_embed.add_field(name="Earned FP", value=str(round(earned_fp, 1)), inline=True)
            await self.cog.log_transaction(self.ctx.guild, log_embed)

        pname = player["name"] if player else f"Player #{player_id}"
        await interaction.response.send_message(
            f"✅ Dropped **{pname}** from your roster. Banked **{round(earned_fp, 1)} FP**.", ephemeral=True
        )
        safe_disable(self)
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Trade flow
# ---------------------------------------------------------------------------

class MemberSelectForTradeView(discord.ui.View):
    """Step 1 of trade: choose who to trade with via UserSelect."""

    def __init__(self, cog, ctx):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.message = None

        sel = discord.ui.UserSelect(placeholder="Select the manager to trade with...", row=0)
        sel.callback = self.member_callback
        self.add_item(sel)

    async def member_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)

        target = interaction.data["resolved"]["members"]
        # UserSelect gives a dict of id -> member data
        if not target:
            return await interaction.response.send_message("No user selected.", ephemeral=True)

        target_id = int(list(target.keys())[0])
        target_member = interaction.guild.get_member(target_id)
        if not target_member:
            return await interaction.response.send_message("Could not resolve that user.", ephemeral=True)
        if target_member == self.ctx.author:
            return await interaction.response.send_message("You cannot trade with yourself.", ephemeral=True)

        rosters = await self.cog.config.guild(interaction.guild).rosters()
        p_uid = str(self.ctx.author.id)
        t_uid = str(target_member.id)

        if p_uid not in rosters or t_uid not in rosters:
            return await interaction.response.send_message("Both managers must be in the league.", ephemeral=True)

        p_pids = [int(pid) for pid in rosters[p_uid].keys()]
        t_pids = [int(pid) for pid in rosters[t_uid].keys()]

        if not p_pids or not t_pids:
            return await interaction.response.send_message("Both managers must have at least one player.", ephemeral=True)

        p_players = [p for p in self.cog.players_cache if p["id"] in p_pids]
        t_players = [p for p in self.cog.players_cache if p["id"] in t_pids]

        embed = discord.Embed(
            title=f"Propose Trade with {target_member.display_name}",
            description="Select one player to **GIVE** and one player to **RECEIVE**.",
            color=discord.Color.purple(),
        )
        view = TradeProposalView(self.cog, self.ctx, target_member, p_players, t_players)

        safe_disable(self)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = self.message

    async def on_timeout(self):
        safe_disable(self)
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


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

        give_opts = [
            discord.SelectOption(
                label=f"{p['name']} ({p['pos']})",
                description=p["team"],
                value=str(p["id"]),
            )
            for p in proposer_players[:25]
        ]
        give_sel = discord.ui.Select(placeholder="Player to GIVE away...", options=give_opts, row=0)
        give_sel.callback = self.give_callback
        self.add_item(give_sel)

        recv_opts = [
            discord.SelectOption(
                label=f"{p['name']} ({p['pos']})",
                description=p["team"],
                value=str(p["id"]),
            )
            for p in target_players[:25]
        ]
        recv_sel = discord.ui.Select(placeholder="Player to RECEIVE...", options=recv_opts, row=1)
        recv_sel.callback = self.receive_callback
        self.add_item(recv_sel)

        self.propose_btn = discord.ui.Button(
            label="📨 Send Trade Offer", style=discord.ButtonStyle.success, disabled=True, row=2
        )
        self.propose_btn.callback = self.propose_callback
        self.add_item(self.propose_btn)

        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, row=2)
        cancel_btn.callback = self.cancel_callback
        self.add_item(cancel_btn)

    def _check_owner(self, interaction):
        return interaction.user.id == self.ctx.author.id

    async def give_callback(self, interaction: discord.Interaction):
        if not self._check_owner(interaction):
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        self.give_id = int(interaction.data["values"][0])
        self._refresh_button()
        await interaction.response.edit_message(view=self)

    async def receive_callback(self, interaction: discord.Interaction):
        if not self._check_owner(interaction):
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        self.receive_id = int(interaction.data["values"][0])
        self._refresh_button()
        await interaction.response.edit_message(view=self)

    def _refresh_button(self):
        self.propose_btn.disabled = not (self.give_id and self.receive_id)

    async def cancel_callback(self, interaction: discord.Interaction):
        if not self._check_owner(interaction):
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        safe_disable(self)
        await interaction.response.edit_message(content="Trade cancelled.", embed=None, view=self)

    async def propose_callback(self, interaction: discord.Interaction):
        if not self._check_owner(interaction):
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)

        give_player = next((p for p in self.proposer_players if p["id"] == self.give_id), None)
        receive_player = next((p for p in self.target_players if p["id"] == self.receive_id), None)

        if not give_player or not receive_player:
            return await interaction.response.send_message("Could not find the selected players.", ephemeral=True)

        safe_disable(self)
        await interaction.response.edit_message(content="✅ Trade offer sent!", embed=None, view=self)

        embed = discord.Embed(
            title="⚖️ Trade Offer!",
            description=f"{interaction.user.mention} has proposed a trade to {self.target_member.mention}.",
            color=discord.Color.gold(),
        )
        embed.add_field(name=f"📤 {interaction.user.display_name} gives:", value=f"**{give_player['name']}** ({give_player['pos']})")
        embed.add_field(name=f"📥 {self.target_member.display_name} gives:", value=f"**{receive_player['name']}** ({receive_player['pos']})")
        embed.set_footer(text="This offer expires in 24 hours.")

        accept_view = TradeAcceptView(self.cog, self.ctx.author, self.target_member, self.give_id, self.receive_id)
        msg = await interaction.channel.send(content=self.target_member.mention, embed=embed, view=accept_view)
        accept_view.message = msg

    async def on_timeout(self):
        safe_disable(self)
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class TradeAcceptView(discord.ui.View):
    def __init__(self, cog, proposer, target, give_id, receive_id):
        super().__init__(timeout=86400)
        self.cog = cog
        self.proposer = proposer
        self.target = target
        self.give_id = give_id
        self.receive_id = receive_id
        self.message = None

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message("Only the trade target can accept this.", ephemeral=True)

        guild = interaction.guild
        rosters = await self.cog.config.guild(guild).rosters()
        scoring = await self.cog.config.guild(guild).scoring_system()
        slots = await self.cog.config.guild(guild).team_slots()

        p_uid = str(self.proposer.id)
        t_uid = str(self.target.id)

        if p_uid not in rosters or t_uid not in rosters:
            return await interaction.response.send_message("A manager is no longer in the league.", ephemeral=True)
        if str(self.give_id) not in rosters[p_uid] or str(self.receive_id) not in rosters[t_uid]:
            return await interaction.response.send_message(
                "One or both players are no longer on their respective rosters!", ephemeral=True
            )

        # Roster fit check after swap
        p_after_ids = [int(pid) for pid in rosters[p_uid].keys() if pid != str(self.give_id)] + [self.receive_id]
        t_after_ids = [int(pid) for pid in rosters[t_uid].keys() if pid != str(self.receive_id)] + [self.give_id]
        p_after = [p for p in self.cog.players_cache if p["id"] in p_after_ids]
        t_after = [p for p in self.cog.players_cache if p["id"] in t_after_ids]

        if not can_fit_roster(p_after, slots):
            return await interaction.response.send_message(
                f"❌ Trade invalid: {self.proposer.display_name} cannot fit the received player into their slots.", ephemeral=True
            )
        if not can_fit_roster(t_after, slots):
            return await interaction.response.send_message(
                "❌ Trade invalid: Your positional slots cannot accommodate the received player.", ephemeral=True
            )

        give_player = next((p for p in self.cog.players_cache if p["id"] == self.give_id), None)
        receive_player = next((p for p in self.cog.players_cache if p["id"] == self.receive_id), None)

        async with self.cog.config.guild(guild).rosters() as r:
            p_joined = r[p_uid].pop(str(self.give_id), 0)
            t_joined = r[t_uid].pop(str(self.receive_id), 0)

            # Swap players and set new FP baseline
            r[p_uid][str(self.receive_id)] = calculate_fp(receive_player, scoring) if receive_player else 0
            r[t_uid][str(self.give_id)] = calculate_fp(give_player, scoring) if give_player else 0

        # Bank earned FP for both sides
        p_earned = (calculate_fp(give_player, scoring) - p_joined) if give_player else 0
        t_earned = (calculate_fp(receive_player, scoring) - t_joined) if receive_player else 0

        async with self.cog.config.guild(guild).scores() as scores:
            scores[p_uid] = scores.get(p_uid, 0.0) + p_earned
            scores[t_uid] = scores.get(t_uid, 0.0) + t_earned

        # Clear old slot assignments for swapped players on both sides
        async with self.cog.config.guild(guild).assignments() as asgn:
            for uid, pid in [(p_uid, str(self.give_id)), (t_uid, str(self.receive_id))]:
                if uid in asgn:
                    asgn[uid].pop(pid, None)

        if give_player and receive_player:
            log_embed = discord.Embed(title="Transaction: Trade Accepted", color=discord.Color.gold())
            log_embed.add_field(name="Proposer", value=self.proposer.mention, inline=True)
            log_embed.add_field(name="Target", value=self.target.mention, inline=True)
            log_embed.add_field(name=f"{self.proposer.display_name} receives", value=f"{receive_player['name']} ({receive_player['pos']})", inline=False)
            log_embed.add_field(name=f"{self.target.display_name} receives", value=f"{give_player['name']} ({give_player['pos']})", inline=False)
            await self.cog.log_transaction(guild, log_embed)

        safe_disable(self)
        await interaction.message.edit(content="✅ **Trade Accepted and Processed!**", view=self)
        await interaction.response.send_message("Trade complete! Check `[p]fantasy team` to see your updated roster.", ephemeral=True)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.danger)
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message("Only the trade target can decline this.", ephemeral=True)
        safe_disable(self)
        await interaction.message.edit(content="❌ **Trade Declined.**", view=self)
        await interaction.response.send_message("Trade declined.", ephemeral=True)

    async def on_timeout(self):
        safe_disable(self)
        try:
            if self.message:
                await self.message.edit(content="⏱️ Trade offer expired.", view=self)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Admin: remove member (UserSelect)
# ---------------------------------------------------------------------------

class AdminRemoveMemberView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.message = None

        sel = discord.ui.UserSelect(placeholder="Select the manager to remove...")
        sel.callback = self.member_callback
        self.add_item(sel)

    async def member_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)

        target_id = int(list(interaction.data["resolved"]["members"].keys())[0])
        member = interaction.guild.get_member(target_id)
        uid_str = str(target_id)

        async with self.cog.config.guild(interaction.guild).rosters() as r:
            r.pop(uid_str, None)
        async with self.cog.config.guild(interaction.guild).scores() as s:
            s.pop(uid_str, None)
        async with self.cog.config.guild(interaction.guild).assignments() as a:
            a.pop(uid_str, None)
        # Also remove from draft order if present
        async with self.cog.config.guild(interaction.guild).draft_state() as ds:
            ds["order"] = [uid for uid in ds["order"] if uid != uid_str]

        name = member.display_name if member else f"User {target_id}"
        safe_disable(self)
        await interaction.response.edit_message(content=f"🗑️ **{name}** has been removed from the league.", view=self)

    async def on_timeout(self):
        safe_disable(self)
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Admin: force add (UserSelect → player list)
# ---------------------------------------------------------------------------

class AdminForceAddStep1(discord.ui.View):
    """Step 1: pick the member to add a player to."""

    def __init__(self, cog, ctx):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.message = None

        sel = discord.ui.UserSelect(placeholder="Select a manager to add a player to...")
        sel.callback = self.member_callback
        self.add_item(sel)

    async def member_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)

        target_id = int(list(interaction.data["resolved"]["members"].keys())[0])
        member = interaction.guild.get_member(target_id)
        uid_str = str(target_id)

        rosters = await self.cog.config.guild(interaction.guild).rosters()
        if uid_str not in rosters:
            return await interaction.response.send_message(
                f"{member.display_name if member else uid_str} hasn't joined the league.", ephemeral=True
            )

        taken_ids = {int(pid) for rd in rosters.values() for pid in rd.keys()}
        available = [p for p in self.cog.players_cache if p["id"] not in taken_ids]
        scoring = await self.cog.config.guild(interaction.guild).scoring_system()
        slots = await self.cog.config.guild(interaction.guild).team_slots()

        embed = discord.Embed(
            title=f"Force Add — Choose player for {member.display_name if member else uid_str}",
            description="Select a player from the dropdown.",
            color=discord.Color.green(),
        )
        view = AdminForceAddStep2(self.cog, self.ctx, uid_str, member, available, scoring, slots)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = self.message

    async def on_timeout(self):
        safe_disable(self)
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class AdminForceAddStep2(PlayerListPagination):
    """Step 2: paginated player list in 'forceadd' mode."""

    def __init__(self, cog, ctx, target_uid, target_member, players, scoring, slots):
        self.target_uid = target_uid
        self.target_member = target_member
        super().__init__(cog, ctx, players, scoring, slots, action_type="info")
        # Override action type label
        self.action_type = "forceadd"
        self.update_items()

    def update_items(self):
        # Reuse parent but rename select placeholder
        super().update_items()
        for child in self.children:
            if isinstance(child, discord.ui.Select) and child.row == 0:
                child.placeholder = "Select a player to FORCE ADD..."
                break

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)

        player_id = int(interaction.data["values"][0])
        player = next((p for p in self.cog.players_cache if p["id"] == player_id), None)
        if not player:
            return await interaction.response.send_message("Player not found.", ephemeral=True)

        rosters = await self.cog.config.guild(interaction.guild).rosters()
        for rd in rosters.values():
            if str(player_id) in rd:
                return await interaction.response.send_message(
                    f"**{player['name']}** is already on another team!", ephemeral=True
                )

        scoring = await self.cog.config.guild(interaction.guild).scoring_system()
        async with self.cog.config.guild(interaction.guild).rosters() as r:
            if self.target_uid not in r:
                r[self.target_uid] = {}
            r[self.target_uid][str(player_id)] = calculate_fp(player, scoring)

        name = self.target_member.display_name if self.target_member else self.target_uid
        safe_disable(self)
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"✅ Force-added **{player['name']}** to **{name}**'s roster.",
                color=discord.Color.green(),
            ),
            view=self,
        )


# ---------------------------------------------------------------------------
# Admin: force drop (UserSelect → their roster dropdown)
# ---------------------------------------------------------------------------

class AdminForceDropStep1(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.message = None

        sel = discord.ui.UserSelect(placeholder="Select a manager to drop a player from...")
        sel.callback = self.member_callback
        self.add_item(sel)

    async def member_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)

        target_id = int(list(interaction.data["resolved"]["members"].keys())[0])
        member = interaction.guild.get_member(target_id)
        uid_str = str(target_id)

        rosters = await self.cog.config.guild(interaction.guild).rosters()
        if uid_str not in rosters or not rosters[uid_str]:
            return await interaction.response.send_message(
                f"{member.display_name if member else uid_str} has no players on their roster.", ephemeral=True
            )

        scoring = await self.cog.config.guild(interaction.guild).scoring_system()
        team_pids = [int(pid) for pid in rosters[uid_str].keys()]
        team_players = [p for p in self.cog.players_cache if p["id"] in team_pids]

        options = []
        for p in team_players[:25]:
            joined_fp = rosters[uid_str].get(str(p["id"]), 0)
            earned = calculate_fp(p, scoring) - joined_fp
            options.append(discord.SelectOption(
                label=f"{p['name']} ({p['pos']})",
                description=f"{p['team']} | Earned: {round(earned, 1)} FP",
                value=str(p["id"]),
            ))

        embed = discord.Embed(
            title=f"Force Drop — {member.display_name if member else uid_str}'s Roster",
            description="Select a player to remove.",
            color=discord.Color.red(),
        )
        view = AdminForceDropStep2(self.cog, self.ctx, uid_str, member, team_players, rosters[uid_str], scoring)
        await interaction.response.edit_message(embed=embed, view=view)
        view.message = self.message

    async def on_timeout(self):
        safe_disable(self)
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class AdminForceDropStep2(discord.ui.View):
    def __init__(self, cog, ctx, target_uid, target_member, team_players, roster_dict, scoring):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.target_uid = target_uid
        self.target_member = target_member
        self.team_players = team_players
        self.roster_dict = roster_dict
        self.scoring = scoring
        self.message = None

        options = []
        for p in team_players[:25]:
            joined_fp = roster_dict.get(str(p["id"]), 0)
            earned = calculate_fp(p, scoring) - joined_fp
            options.append(discord.SelectOption(
                label=f"{p['name']} ({p['pos']})",
                description=f"{p['team']} | Earned: {round(earned, 1)} FP",
                value=str(p["id"]),
            ))

        sel = discord.ui.Select(placeholder="Choose a player to drop...", options=options)
        sel.callback = self.drop_callback
        self.add_item(sel)

    async def drop_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)

        player_id = int(interaction.data["values"][0])
        player = next((p for p in self.team_players if p["id"] == player_id), None)

        async with self.cog.config.guild(interaction.guild).rosters() as r:
            if self.target_uid not in r or str(player_id) not in r[self.target_uid]:
                return await interaction.response.send_message("Player no longer on that roster.", ephemeral=True)
            joined_fp = r[self.target_uid].pop(str(player_id))

        earned_fp = (calculate_fp(player, self.scoring) - joined_fp) if player else 0

        async with self.cog.config.guild(interaction.guild).scores() as scores:
            scores[self.target_uid] = scores.get(self.target_uid, 0.0) + earned_fp

        async with self.cog.config.guild(interaction.guild).assignments() as asgn:
            if self.target_uid in asgn:
                asgn[self.target_uid].pop(str(player_id), None)

        name = self.target_member.display_name if self.target_member else self.target_uid
        pname = player["name"] if player else f"Player #{player_id}"
        safe_disable(self)
        await interaction.response.edit_message(
            embed=discord.Embed(
                description=f"✅ Dropped **{pname}** from **{name}**'s roster. They banked **{round(earned_fp, 1)} FP**.",
                color=discord.Color.red(),
            ),
            view=self,
        )

    async def on_timeout(self):
        safe_disable(self)
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Admin: set scoring (select stat → modal)
# ---------------------------------------------------------------------------

class ScoringEditView(discord.ui.View):
    def __init__(self, cog, ctx, current_scoring):
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.message = None

        options = [
            discord.SelectOption(
                label=STAT_LABELS.get(stat, stat.upper()),
                description=f"Current: {val} FP per {stat.upper()}",
                value=stat,
            )
            for stat, val in current_scoring.items()
        ]
        sel = discord.ui.Select(placeholder="Choose a stat to edit...", options=options)
        sel.callback = self.stat_callback
        self.add_item(sel)

    async def stat_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("This is not your menu.", ephemeral=True)
        stat = interaction.data["values"][0]
        await interaction.response.send_modal(ScoringValueModal(self.cog, self.ctx, stat))

    async def on_timeout(self):
        safe_disable(self)
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Reset confirmation
# ---------------------------------------------------------------------------

class ConfirmResetView(discord.ui.View):
    def __init__(self, cog, ctx):
        super().__init__(timeout=30)
        self.cog = cog
        self.ctx = ctx
        self.message = None

    @discord.ui.button(label="⚠️ Yes, Reset Everything", style=discord.ButtonStyle.danger)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Only the command issuer can confirm.", ephemeral=True)
        await self.cog.config.guild(interaction.guild).rosters.set({})
        await self.cog.config.guild(interaction.guild).scores.set({})
        await self.cog.config.guild(interaction.guild).assignments.set({})
        await self.cog.config.guild(interaction.guild).draft_state.set({
            "is_active": False, "order": [], "current_pick": 0, "picks": [],
        })
        safe_disable(self)
        await interaction.response.edit_message(
            content="🔄 **Full reset complete.** All rosters, scores, assignments, and draft data have been cleared.",
            view=self,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Only the command issuer can cancel.", ephemeral=True)
        safe_disable(self)
        await interaction.response.edit_message(content="Reset cancelled.", view=self)

    async def on_timeout(self):
        safe_disable(self)
        try:
            if self.message:
                await self.message.edit(content="Reset confirmation timed out.", view=self)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main Cog
# ---------------------------------------------------------------------------

class NBAFantasy(commands.Cog):
    """Advanced NBAdex Fantasy League Cog."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=928374928375, force_registration=True)

        default_guild = {
            "is_active": False,
            "fa_locked": False,
            "rosters": {},
            "assignments": {},
            "scores": {},
            "team_slots": ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL", "UTIL", "UTIL"],
            "transaction_channel": None,
            "scoring_system": {
                "pts": 1.0, "reb": 1.2, "ast": 1.5,
                "stl": 3.0, "blk": 3.0, "tov": -1.0,
            },
            "draft_state": {
                "is_active": False,
                "order": [],
                "current_pick": 0,
                "picks": [],
            },
        }
        default_global = {"players_cache": []}

        self.config.register_guild(**default_guild)
        self.config.register_global(**default_global)
        self.players_cache = []
        self.last_fetch_error = None
        self._setup_session()
        self.bg_task = bot.loop.create_task(self.update_cache_loop())

    def cog_unload(self):
        self.bg_task.cancel()

    # ── background cache loop ──────────────────────────────────────────────

    async def update_cache_loop(self):
        await self.bot.wait_until_ready()
        self.players_cache = await self.config.players_cache()
        while True:
            try:
                await self._fetch_players()
                await self.config.players_cache.set(self.players_cache)
                self.last_fetch_error = None
                await asyncio.sleep(3600)
            except Exception as e:
                self.last_fetch_error = str(e)
                print(f"[NBAFantasy] Fetch error: {e}")
                await asyncio.sleep(300)

    def _setup_session(self):
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        })

    async def _fetch_players(self):
        def fetch():
            base = (
                "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/"
                "statistics/byathlete?region=us&lang=en&contentorigin=espn&isqualified=false&limit=500"
            )
            all_athletes = []
            page = 1
            max_pages = 1
            cat_maps = {}

            while page <= max_pages:
                try:
                    r = self._session.get(f"{base}&page={page}", timeout=30)
                    r.raise_for_status()
                    data = r.json()
                    if page == 1:
                        max_pages = data.get("pagination", {}).get("pages", 1)
                        for cat in data.get("categories", []):
                            cat_maps[cat["name"]] = {n: i for i, n in enumerate(cat.get("names", []))}
                    all_athletes.extend(data.get("athletes", []))
                    page += 1
                    time.sleep(1)
                except Exception as e:
                    print(f"[NBAFantasy] ESPN stats page {page} failed: {e}")
                    raise

            injuries = {}
            try:
                inj = self._session.get(
                    "http://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries", timeout=30
                )
                inj.raise_for_status()
                for team_inj in inj.json().get("injuries", []):
                    for inj_item in team_inj.get("injuries", []):
                        ath = inj_item.get("athlete", {})
                        if "id" in ath:
                            injuries[int(ath["id"])] = inj_item.get("status", "Out")
            except Exception as e:
                print(f"[NBAFantasy] Injuries fetch failed: {e}")

            return all_athletes, cat_maps, injuries

        loop = asyncio.get_running_loop()
        all_athletes, cat_maps, injuries = await loop.run_in_executor(None, fetch)

        cached = []
        for p in all_athletes:
            ath = p.get("athlete", {})
            try:
                pid = int(ath.get("id", 0))
            except (ValueError, TypeError):
                continue

            name = ath.get("displayName", "Unknown")
            team = ath.get("teamShortName", "FA")
            pos = ath.get("position", {}).get("abbreviation", "UTIL")

            is_out = False
            status_label = ""
            if pid in injuries:
                is_out = True
                status_label = str(injuries[pid]).upper()
            else:
                st = ath.get("status", {})
                stype = st.get("type", "active").lower()
                is_out = stype in ("out", "day-to-day", "injured", "suspended")
                if is_out:
                    status_label = st.get("abbreviation", "OUT").upper() or "OUT"

            pts = reb = ast = stl = blk = tov = 0.0
            for cat in p.get("categories", []):
                cname = cat.get("name")
                vals = cat.get("values", [])
                cmap = cat_maps.get(cname, {})

                def _get(key):
                    idx = cmap.get(key)
                    if idx is not None and idx < len(vals):
                        return float(vals[idx])
                    return 0.0

                pts = _get("points") or pts
                reb = _get("rebounds") or reb
                ast = _get("assists") or ast
                tov = _get("turnovers") or tov
                stl = _get("steals") or stl
                blk = _get("blocks") or blk

            cached.append({
                "id":           pid,
                "name":         name,
                "team":         team,
                "pos":          pos,
                "pts":          round(max(0.0, pts), 1),
                "reb":          round(max(0.0, reb), 1),
                "ast":          round(max(0.0, ast), 1),
                "stl":          round(max(0.0, stl), 1),
                "blk":          round(max(0.0, blk), 1),
                "tov":          round(max(0.0, tov), 1),
                "out":          is_out,
                "status_label": status_label,
            })

        self.players_cache = cached

    # ── transaction log ────────────────────────────────────────────────────

    async def log_transaction(self, guild, embed):
        chan_id = await self.config.guild(guild).transaction_channel()
        if not chan_id:
            return
        channel = guild.get_channel(chan_id)
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

    # ── shared handler: FA pickup ──────────────────────────────────────────

    async def handle_fa_pickup(self, interaction: discord.Interaction, view, player_id: int):
        fa_locked = await self.config.guild(interaction.guild).fa_locked()
        if fa_locked:
            return await interaction.response.send_message("🔒 Free Agency is locked.", ephemeral=True)

        uid_str = str(interaction.user.id)
        scoring = await self.config.guild(interaction.guild).scoring_system()
        slots = await self.config.guild(interaction.guild).team_slots()

        async with self.config.guild(interaction.guild).rosters() as rosters:
            if uid_str not in rosters:
                return await interaction.response.send_message("You haven't joined the league yet.", ephemeral=True)
            if len(rosters[uid_str]) >= len(slots):
                return await interaction.response.send_message(
                    f"Your roster is full ({len(slots)} players max).", ephemeral=True
                )
            for rd in rosters.values():
                if str(player_id) in rd:
                    return await interaction.response.send_message("That player is already on a team!", ephemeral=True)

            player = next((p for p in self.players_cache if p["id"] == player_id), None)
            if not player:
                return await interaction.response.send_message("Player not found. Try again shortly.", ephemeral=True)

            current_ids = [int(pid) for pid in rosters[uid_str].keys()]
            current_players = [p for p in self.players_cache if p["id"] in current_ids] + [player]

            if not can_fit_roster(current_players, slots):
                return await interaction.response.send_message(
                    f"**{player['name']}** doesn't fit your positional slots.", ephemeral=True
                )

            # Baseline = current FP so earned starts at 0
            rosters[uid_str][str(player_id)] = calculate_fp(player, scoring)

            log_embed = discord.Embed(title="Transaction: FA Pickup", color=discord.Color.green())
            log_embed.add_field(name="User", value=interaction.user.mention, inline=True)
            log_embed.add_field(name="Player", value=f"{player['name']} ({player['pos']})", inline=True)
            log_embed.add_field(name="Team", value=player["team"], inline=True)
            await self.log_transaction(interaction.guild, log_embed)

        await interaction.response.send_message(
            f"✅ **{player['name']}** added to your roster!", ephemeral=True
        )
        safe_disable(view)
        try:
            await view.message.edit(view=view)
        except Exception:
            pass

    # ── shared handler: draft pick ─────────────────────────────────────────

    async def handle_draft_pick(self, interaction: discord.Interaction, view, player_id: int):
        uid_str = str(interaction.user.id)
        scoring = await self.config.guild(interaction.guild).scoring_system()
        slots = await self.config.guild(interaction.guild).team_slots()

        # Read state (no context manager — we write separately below)
        draft_state = await self.config.guild(interaction.guild).draft_state()

        if not draft_state.get("is_active"):
            return await interaction.response.send_message("The draft is not active.", ephemeral=True)

        order = draft_state["order"]
        current_pick = draft_state["current_pick"]

        if current_pick >= len(order):
            return await interaction.response.send_message("The draft is already over!", ephemeral=True)
        if order[current_pick] != uid_str:
            on_clock = interaction.guild.get_member(int(order[current_pick]))
            name = on_clock.display_name if on_clock else f"<@{order[current_pick]}>"
            return await interaction.response.send_message(
                f"It's not your turn! Currently waiting on **{name}**.", ephemeral=True
            )

        rosters = await self.config.guild(interaction.guild).rosters()
        for rd in rosters.values():
            if str(player_id) in rd:
                return await interaction.response.send_message("That player is already drafted!", ephemeral=True)

        player = next((p for p in self.players_cache if p["id"] == player_id), None)
        if not player:
            return await interaction.response.send_message("Player not found. Try again shortly.", ephemeral=True)

        user_roster = rosters.get(uid_str, {})
        current_ids = [int(pid) for pid in user_roster.keys()]
        current_players = [p for p in self.players_cache if p["id"] in current_ids] + [player]

        if not can_fit_roster(current_players, slots):
            return await interaction.response.send_message(
                f"**{player['name']}** doesn't fit your positional slots.", ephemeral=True
            )

        # Save roster pick
        async with self.config.guild(interaction.guild).rosters() as r:
            if uid_str not in r:
                r[uid_str] = {}
            r[uid_str][str(player_id)] = calculate_fp(player, scoring)

        # Advance draft state (with race-condition safety check)
        async with self.config.guild(interaction.guild).draft_state() as ds:
            if ds["current_pick"] != current_pick or not ds["is_active"]:
                # Rollback
                async with self.config.guild(interaction.guild).rosters() as r:
                    if uid_str in r:
                        r[uid_str].pop(str(player_id), None)
                return await interaction.response.send_message(
                    "Draft state changed — please try again.", ephemeral=True
                )
            ds["picks"].append({
                "pick_number": current_pick + 1,
                "user_id":    uid_str,
                "player_id":  player_id,
                "player_name": player["name"],
            })
            ds["current_pick"] += 1
            next_pick = ds["current_pick"]
            if next_pick >= len(order):
                ds["is_active"] = False

        log_embed = discord.Embed(title="Transaction: Draft Pick", color=discord.Color.blue())
        log_embed.add_field(name="User", value=interaction.user.mention, inline=True)
        log_embed.add_field(name="Player", value=f"{player['name']} ({player['pos']})", inline=True)
        log_embed.add_field(name="Pick #", value=str(current_pick + 1), inline=True)
        await self.log_transaction(interaction.guild, log_embed)

        await interaction.response.send_message(
            f"📋 **Pick #{current_pick + 1}:** {interaction.user.mention} drafts **{player['name']}** ({player['pos']}, {player['team']})!"
        )

        if next_pick >= len(order):
            await interaction.channel.send(
                "🎉 **The Draft is complete!** Free Agency is now open unless locked by an admin."
            )
        else:
            next_uid = order[next_pick]
            next_member = interaction.guild.get_member(int(next_uid))
            mention = next_member.mention if next_member else f"<@{next_uid}>"
            await interaction.channel.send(f"📢 {mention}, you're on the clock! **Pick #{next_pick + 1}** — use `[p]fantasy draft board`.")

        safe_disable(view)
        try:
            await view.message.edit(view=view)
        except Exception:
            pass

    # ── shared handler: player info popup ─────────────────────────────────

    async def handle_player_info(self, interaction: discord.Interaction, player_id: int):
        player = next((p for p in self.players_cache if p["id"] == player_id), None)
        if not player:
            return await interaction.response.send_message("Player not found.", ephemeral=True)

        scoring = await self.config.guild(interaction.guild).scoring_system()
        fp = calculate_fp(player, scoring)
        status = player_status_str(player)
        color = discord.Color.red() if player.get("out") else discord.Color.blue()

        embed = discord.Embed(
            title=f"{player['name']} ({player['pos']}){status}",
            description=f"Team: **{player['team']}**",
            color=color,
        )
        embed.add_field(name="Fantasy Points", value=f"**{fp} FP**", inline=False)
        embed.add_field(name="PTS", value=player["pts"], inline=True)
        embed.add_field(name="REB", value=player["reb"], inline=True)
        embed.add_field(name="AST", value=player["ast"], inline=True)
        embed.add_field(name="STL", value=player["stl"], inline=True)
        embed.add_field(name="BLK", value=player["blk"], inline=True)
        embed.add_field(name="TOV", value=player["tov"], inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ======================================================================
    # Commands
    # ======================================================================

    @commands.group(name="fantasy", aliases=["nbafantasy", "nbaf"])
    async def fantasy(self, ctx):
        """Advanced NBA Fantasy League commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    # ── info & help ────────────────────────────────────────────────────────

    @fantasy.command(name="guide")
    async def fantasy_guide(self, ctx):
        """Show the full guide on how to play NBAdex Fantasy."""
        embed = discord.Embed(title="🏀 NBAdex Fantasy League — Player Guide", color=discord.Color.green())
        embed.add_field(
            name="1. Joining",
            value="Use `[p]fantasy join` to enter the league (must be set up by an admin first).",
            inline=False,
        )
        embed.add_field(
            name="2. Draft",
            value="Admins run `[p]fantasy draft setup @user1 @user2 …` then `[p]fantasy draft start`. "
                  "Use `[p]fantasy draft board` to pick when it's your turn.",
            inline=False,
        )
        embed.add_field(
            name="3. Free Agency",
            value="After the draft, use `[p]fantasy freeagents` to browse and sign available players.",
            inline=False,
        )
        embed.add_field(
            name="4. Managing Your Team",
            value="`[p]fantasy team` — view your roster and drop/assign players via dropdowns.",
            inline=False,
        )
        embed.add_field(
            name="5. Trading",
            value="`[p]fantasy trade` — opens a menu to choose a trade partner and select players.",
            inline=False,
        )
        embed.add_field(
            name="6. Scoring",
            value="FP = PTS×1.0 + REB×1.2 + AST×1.5 + STL×3.0 + BLK×3.0 + TOV×(−1.0). "
                  "Earned FP is locked in when a player joins your roster.",
            inline=False,
        )
        embed.add_field(
            name="7. Standings",
            value="`[p]fantasy standings` — see the full leaderboard.",
            inline=False,
        )
        await ctx.send(embed=embed)

    @fantasy.command(name="status")
    async def fantasy_status(self, ctx):
        """View the current league status."""
        is_active = await self.config.guild(ctx.guild).is_active()
        fa_locked = await self.config.guild(ctx.guild).fa_locked()
        rosters = await self.config.guild(ctx.guild).rosters()
        draft_state = await self.config.guild(ctx.guild).draft_state()
        err = self.last_fetch_error

        color = discord.Color.green() if is_active else discord.Color.red()
        embed = discord.Embed(title="🏀 Fantasy League Status", color=color)
        embed.add_field(name="League", value="✅ Active" if is_active else "❌ Inactive", inline=True)
        embed.add_field(name="Free Agency", value="🔒 Locked" if fa_locked else "🔓 Open", inline=True)
        embed.add_field(name="Teams Joined", value=str(len(rosters)), inline=True)

        if draft_state["is_active"]:
            pick = draft_state["current_pick"]
            order = draft_state["order"]
            on_clock_id = order[pick] if pick < len(order) else None
            on_clock = ctx.guild.get_member(int(on_clock_id)).display_name if on_clock_id and ctx.guild.get_member(int(on_clock_id)) else f"<@{on_clock_id}>"
            embed.add_field(name="Draft", value=f"🟢 In Progress — Pick #{pick + 1}\n🎯 On the clock: **{on_clock}**", inline=False)
        else:
            picks_made = len(draft_state.get("picks", []))
            embed.add_field(
                name="Draft",
                value=f"⚪ Not active ({picks_made} picks recorded)" if picks_made else "⚪ Not started",
                inline=False,
            )

        embed.add_field(
            name="Player Data",
            value=f"{'⚠️ Last fetch failed: ' + err if err else '✅ OK'} ({len(self.players_cache)} players cached)",
            inline=False,
        )
        await ctx.send(embed=embed)

    # ── setup & admin ──────────────────────────────────────────────────────

    @fantasy.command(name="setup")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_setup(self, ctx):
        """Enable NBA Fantasy in this server."""
        await self.config.guild(ctx.guild).is_active.set(True)
        await ctx.send("🏀 NBA Fantasy is now **active**! Users can `[p]fantasy join`.")

    @fantasy.command(name="settings")
    async def fantasy_settings(self, ctx):
        """View current league settings."""
        slots = await self.config.guild(ctx.guild).team_slots()
        scoring = await self.config.guild(ctx.guild).scoring_system()
        chan_id = await self.config.guild(ctx.guild).transaction_channel()

        embed = discord.Embed(title="⚙️ Fantasy League Settings", color=discord.Color.blurple())
        embed.add_field(name="Roster Slots", value=", ".join(slots), inline=False)
        score_str = "\n".join(f"**{STAT_LABELS.get(k, k.upper())}**: {v} FP" for k, v in scoring.items())
        embed.add_field(name="Scoring System", value=score_str, inline=False)
        chan = ctx.guild.get_channel(chan_id) if chan_id else None
        embed.add_field(name="Transaction Log Channel", value=chan.mention if chan else "Not set", inline=False)
        await ctx.send(embed=embed)

    @fantasy.command(name="setslots")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_setslots(self, ctx, *slots: str):
        """Set roster positional slots. Example: `[p]fantasy setslots PG SG SF PF C UTIL UTIL`"""
        if not slots:
            return await ctx.send_help(ctx.command)
        valid = set(VALID_SLOTS.keys())
        slots = [s.upper() for s in slots]
        bad = [s for s in slots if s not in valid]
        if bad:
            return await ctx.send(f"Invalid slot(s): {', '.join(bad)}. Valid: {', '.join(valid)}")
        await self.config.guild(ctx.guild).team_slots.set(list(slots))
        await ctx.send(f"✅ Roster slots updated to: **{', '.join(slots)}** ({len(slots)} slots total)")

    @fantasy.command(name="setscoring")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_setscoring(self, ctx):
        """Edit scoring multipliers via dropdown + modal."""
        scoring = await self.config.guild(ctx.guild).scoring_system()
        embed = discord.Embed(
            title="⚙️ Edit Scoring System",
            description="Select a stat from the dropdown to change its FP value.",
            color=discord.Color.blurple(),
        )
        for stat, val in scoring.items():
            embed.add_field(name=STAT_LABELS.get(stat, stat.upper()), value=f"{val} FP", inline=True)
        view = ScoringEditView(self, ctx, scoring)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @fantasy.group(name="config")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_config(self, ctx):
        """Admin configuration for the league."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @fantasy_config.command(name="channel")
    async def fantasy_config_channel(self, ctx, channel: discord.TextChannel = None):
        """Set (or clear) the channel for transaction logs."""
        if channel:
            await self.config.guild(ctx.guild).transaction_channel.set(channel.id)
            await ctx.send(f"✅ Transaction logs → {channel.mention}")
        else:
            await self.config.guild(ctx.guild).transaction_channel.set(None)
            await ctx.send("❌ Transaction logging disabled.")

    # ── join ───────────────────────────────────────────────────────────────

    @fantasy.command(name="join")
    async def fantasy_join(self, ctx):
        """Join the server's NBA Fantasy league."""
        is_active = await self.config.guild(ctx.guild).is_active()
        if not is_active:
            return await ctx.send("The fantasy league is not currently active.")
        uid_str = str(ctx.author.id)
        async with self.config.guild(ctx.guild).rosters() as rosters:
            if uid_str in rosters:
                return await ctx.send("You've already joined the league!")
            rosters[uid_str] = {}
        async with self.config.guild(ctx.guild).scores() as scores:
            scores[uid_str] = 0.0
        await ctx.send(f"🎉 Welcome to the league, **{ctx.author.display_name}**! Use `[p]fantasy freeagents` to build your roster.")

    # ── team view ──────────────────────────────────────────────────────────

    @fantasy.command(name="team")
    async def fantasy_team(self, ctx, member: discord.Member = None):
        """View your team (or another manager's). Includes drop & assign controls."""
        target = member or ctx.author
        uid_str = str(target.id)

        rosters = await self.config.guild(ctx.guild).rosters()
        if uid_str not in rosters:
            return await ctx.send(f"**{target.display_name}** hasn't joined the league yet.")
        if not self.players_cache:
            return await ctx.send("Player data is still loading. Try again shortly.")

        player_dict = rosters[uid_str]
        if isinstance(player_dict, list):
            async with self.config.guild(ctx.guild).rosters() as r:
                r[uid_str] = {}
            player_dict = {}

        player_ids = [int(pid) for pid in player_dict.keys()]
        team_players = [p for p in self.players_cache if p["id"] in player_ids]
        scores = await self.config.guild(ctx.guild).scores()
        scoring = await self.config.guild(ctx.guild).scoring_system()
        slots = await self.config.guild(ctx.guild).team_slots()
        assignments = await self.config.guild(ctx.guild).assignments()
        user_asgn = assignments.get(uid_str, {})

        banked_fp = scores.get(uid_str, 0.0)
        embed = discord.Embed(title=f"🏀 {target.display_name}'s Fantasy Team", color=discord.Color.orange())
        embed.set_thumbnail(url=target.display_avatar.url)

        if not team_players:
            embed.description = f"**Banked FP:** {round(banked_fp, 1)}\n\nRoster is empty — use `[p]fantasy freeagents` to add players!"
            return await ctx.send(embed=embed)

        slot_counts = Counter(slots)
        assigned_display = []
        bench_display = []
        assigned_pids = set()
        current_roster_fp = 0.0

        for p in team_players:
            pid_str = str(p["id"])
            slot = user_asgn.get(pid_str)
            if slot and slot_counts[slot] > 0:
                assigned_display.append((slot, p))
                slot_counts[slot] -= 1
                assigned_pids.add(pid_str)

        for p in team_players:
            if str(p["id"]) not in assigned_pids:
                bench_display.append(("BENCH", p))

        empty_slots = [(slot, None) for slot, cnt in slot_counts.items() for _ in range(cnt)]
        assigned_display.sort(key=lambda x: SLOT_DISPLAY_ORDER.index(x[0]) if x[0] in SLOT_DISPLAY_ORDER else 99)
        final_display = assigned_display + empty_slots + bench_display

        for slot, p in final_display:
            if p:
                joined_fp = player_dict.get(str(p["id"]), calculate_fp(p, scoring))
                earned = calculate_fp(p, scoring) - joined_fp
                current_roster_fp += earned
                status = player_status_str(p)
                embed.add_field(
                    name=f"[{slot}] {p['name']} ({p['pos']}){status}",
                    value=f"{p['team']} | +**{round(earned, 1)} FP**",
                    inline=False,
                )
            else:
                embed.add_field(name=f"[{slot}] — EMPTY", value="\u200b", inline=False)

        total_fp = banked_fp + current_roster_fp
        embed.description = (
            f"**Total FP: {round(total_fp, 1)}** "
            f"*(Banked: {round(banked_fp, 1)} + Active: {round(current_roster_fp, 1)})*"
        )
        if target == ctx.author:
            embed.set_footer(text="Use the dropdowns below to drop players or change slot assignments.")
            view = TeamManagementView(self, ctx, team_players, player_dict, scoring, slots)
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
        else:
            await ctx.send(embed=embed)

    # ── free agency ────────────────────────────────────────────────────────

    @fantasy.command(name="freeagents", aliases=["fa"])
    async def fantasy_freeagents(self, ctx):
        """Browse and sign available free agents."""
        if not self.players_cache:
            return await ctx.send("Player data is still loading. Try again shortly.")
        fa_locked = await self.config.guild(ctx.guild).fa_locked()
        if fa_locked:
            return await ctx.send("🔒 Free Agency is locked.")
        rosters = await self.config.guild(ctx.guild).rosters()
        if str(ctx.author.id) not in rosters:
            return await ctx.send("You haven't joined the league yet. Use `[p]fantasy join`.")

        taken = {int(pid) for rd in rosters.values() for pid in rd.keys()}
        available = [p for p in self.players_cache if p["id"] not in taken]
        scoring = await self.config.guild(ctx.guild).scoring_system()
        slots = await self.config.guild(ctx.guild).team_slots()

        embed = discord.Embed(
            title="📋 Free Agents",
            description=f"**{len(available)}** players available. Select one from the dropdown to add them.",
            color=discord.Color.blue(),
        )
        view = PlayerListPagination(self, ctx, available, scoring, slots, action_type="fa")
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        await view.update_view(msg)

    # ── player lookup ──────────────────────────────────────────────────────

    @fantasy.command(name="player")
    async def fantasy_player(self, ctx):
        """Browse and look up any NBA player's stats via dropdown."""
        if not self.players_cache:
            return await ctx.send("Player data is still loading. Try again shortly.")
        scoring = await self.config.guild(ctx.guild).scoring_system()
        slots = await self.config.guild(ctx.guild).team_slots()

        embed = discord.Embed(
            title="🔍 Player Lookup",
            description="Search or browse players. Select one to see their full stats.",
            color=discord.Color.blue(),
        )
        view = PlayerListPagination(self, ctx, list(self.players_cache), scoring, slots, action_type="info")
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        await view.update_view(msg)

    # ── standings ──────────────────────────────────────────────────────────

    @fantasy.command(name="standings")
    async def fantasy_standings(self, ctx):
        """View the full league leaderboard."""
        rosters = await self.config.guild(ctx.guild).rosters()
        if not rosters:
            return await ctx.send("Nobody has joined the league yet.")
        scoring = await self.config.guild(ctx.guild).scoring_system()
        scores = await self.config.guild(ctx.guild).scores()

        leaderboard = []
        for uid_str, player_dict in rosters.items():
            if not isinstance(player_dict, dict):
                continue
            team_players = [p for p in self.players_cache if p["id"] in [int(pid) for pid in player_dict.keys()]]
            roster_fp = sum(calculate_fp(p, scoring) - player_dict.get(str(p["id"]), 0) for p in team_players)
            total = scores.get(uid_str, 0.0) + roster_fp
            best = max(team_players, key=lambda p: calculate_fp(p, scoring) - player_dict.get(str(p["id"]), 0), default=None)
            leaderboard.append((uid_str, round(total, 1), best, player_dict))

        leaderboard.sort(key=lambda x: x[1], reverse=True)
        medals = ["🥇", "🥈", "🥉"]

        embed = discord.Embed(title="🏆 NBAdex Fantasy Standings", color=discord.Color.gold())
        for idx, (uid_str, score, best, player_dict) in enumerate(leaderboard, 1):
            member = ctx.guild.get_member(int(uid_str))
            name = member.display_name if member else f"User {uid_str}"
            medal = medals[idx - 1] if idx <= 3 else f"#{idx}"
            mvp = ""
            if best:
                earned = calculate_fp(best, scoring) - player_dict.get(str(best["id"]), 0)
                mvp = f"\n*MVP: {best['name']} (+{round(earned, 1)} FP)*"
            embed.add_field(
                name=f"{medal} {name}",
                value=f"**{score} FP**{mvp}",
                inline=False,
            )
        await ctx.send(embed=embed)

    # ── trade ──────────────────────────────────────────────────────────────

    @fantasy.command(name="trade")
    async def fantasy_trade(self, ctx):
        """Propose a trade with another manager — fully dropdown driven."""
        rosters = await self.config.guild(ctx.guild).rosters()
        uid_str = str(ctx.author.id)
        if uid_str not in rosters:
            return await ctx.send("You haven't joined the league yet.")
        if not rosters[uid_str]:
            return await ctx.send("You need at least one player on your roster to trade.")

        embed = discord.Embed(
            title="⚖️ Propose a Trade",
            description="Select the manager you want to trade with.",
            color=discord.Color.purple(),
        )
        view = MemberSelectForTradeView(self, ctx)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    # ── lock / unlock ──────────────────────────────────────────────────────

    @fantasy.command(name="lock")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_lock(self, ctx):
        """Lock free agency."""
        await self.config.guild(ctx.guild).fa_locked.set(True)
        await ctx.send("🔒 Free Agency is now **locked**.")

    @fantasy.command(name="unlock")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_unlock(self, ctx):
        """Unlock free agency."""
        await self.config.guild(ctx.guild).fa_locked.set(False)
        await ctx.send("🔓 Free Agency is now **open**.")

    # ── remove ─────────────────────────────────────────────────────────────

    @fantasy.command(name="remove")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_remove(self, ctx):
        """Remove a manager from the league via dropdown."""
        rosters = await self.config.guild(ctx.guild).rosters()
        if not rosters:
            return await ctx.send("Nobody is in the league.")
        embed = discord.Embed(
            title="🗑️ Remove a Manager",
            description="Select the manager to fully remove from the league.",
            color=discord.Color.red(),
        )
        view = AdminRemoveMemberView(self, ctx)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    # ── reset ──────────────────────────────────────────────────────────────

    @fantasy.command(name="reset")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_reset(self, ctx):
        """Reset the entire league (rosters, scores, draft, assignments)."""
        embed = discord.Embed(
            title="⚠️ Confirm Full Reset",
            description=(
                "This will permanently delete **ALL** rosters, scores, assignments, and draft data.\n\n"
                "There is no undo. Are you sure?"
            ),
            color=discord.Color.red(),
        )
        view = ConfirmResetView(self, ctx)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    # ── update stats ───────────────────────────────────────────────────────

    @fantasy.command(name="update")
    @commands.is_owner()
    async def fantasy_update(self, ctx):
        """Force refresh NBA player stats (bot owner only)."""
        msg = await ctx.send("🏀 Fetching latest stats…")
        try:
            await self._fetch_players()
            await self.config.players_cache.set(self.players_cache)
            self.last_fetch_error = None
            await msg.edit(content=f"✅ Updated **{len(self.players_cache)}** players successfully!")
        except Exception as e:
            self.last_fetch_error = str(e)
            await msg.edit(content=f"❌ Fetch failed: {e}")

    # ── forceadd ──────────────────────────────────────────────────────────

    @fantasy.command(name="forceadd")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_forceadd(self, ctx):
        """Admin: Force add a player to any manager's roster via dropdowns."""
        if not self.players_cache:
            return await ctx.send("Player data is still loading.")
        embed = discord.Embed(
            title="➕ Force Add Player",
            description="Select the manager to add a player to.",
            color=discord.Color.green(),
        )
        view = AdminForceAddStep1(self, ctx)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    # ── forcedrop ─────────────────────────────────────────────────────────

    @fantasy.command(name="forcedrop")
    @commands.admin_or_permissions(manage_guild=True)
    async def fantasy_forcedrop(self, ctx):
        """Admin: Force drop a player from any manager's roster via dropdowns."""
        embed = discord.Embed(
            title="✂️ Force Drop Player",
            description="Select the manager to drop a player from.",
            color=discord.Color.red(),
        )
        view = AdminForceDropStep1(self, ctx)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    # ── draft group ────────────────────────────────────────────────────────

    @fantasy.group(name="draft")
    async def fantasy_draft(self, ctx):
        """Draft management commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @fantasy_draft.command(name="setup")
    @commands.admin_or_permissions(manage_guild=True)
    async def draft_setup(self, ctx, *members: discord.Member):
        """Configure the snake draft order. Example: `[p]fantasy draft setup @a @b @c`"""
        if not members:
            return await ctx.send("Please mention at least one member.")
        if len(members) > 25:
            return await ctx.send("Maximum 25 participants per draft.")

        slots = await self.config.guild(ctx.guild).team_slots()
        num_rounds = len(slots)
        base = [str(m.id) for m in members]

        full_order = []
        for rnd in range(num_rounds):
            full_order.extend(base if rnd % 2 == 0 else reversed(base))

        async with self.config.guild(ctx.guild).draft_state() as ds:
            ds["order"] = full_order
            ds["current_pick"] = 0
            ds["picks"] = []
            ds["is_active"] = False

        embed = discord.Embed(title="✅ Draft Configured", color=discord.Color.green())
        embed.add_field(name="Participants", value=", ".join(m.display_name for m in members), inline=False)
        embed.add_field(name="Rounds", value=str(num_rounds), inline=True)
        embed.add_field(name="Total Picks", value=str(len(full_order)), inline=True)
        embed.add_field(name="Format", value="Snake Draft", inline=True)
        embed.set_footer(text="Use `[p]fantasy draft start` when ready to begin.")
        await ctx.send(embed=embed)

    @fantasy_draft.command(name="start")
    @commands.admin_or_permissions(manage_guild=True)
    async def draft_start(self, ctx):
        """Start the draft (locks free agency automatically)."""
        async with self.config.guild(ctx.guild).draft_state() as ds:
            if not ds["order"]:
                return await ctx.send("Draft order not configured. Use `[p]fantasy draft setup` first.")
            if ds["is_active"]:
                return await ctx.send("The draft is already in progress.")
            ds["is_active"] = True
            first_uid = ds["order"][ds["current_pick"]]

        await self.config.guild(ctx.guild).fa_locked.set(True)
        first = ctx.guild.get_member(int(first_uid))
        mention = first.mention if first else f"<@{first_uid}>"
        embed = discord.Embed(
            title="🎉 The Draft Has Begun!",
            description=f"Free Agency is now locked.\n\n📢 {mention}, you're **on the clock**!\nUse `[p]fantasy draft board` to make your pick.",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @fantasy_draft.command(name="stop")
    @commands.admin_or_permissions(manage_guild=True)
    async def draft_stop(self, ctx):
        """Stop (cancel) the draft early."""
        async with self.config.guild(ctx.guild).draft_state() as ds:
            ds["is_active"] = False
        await ctx.send("🛑 Draft has been stopped.")

    @fantasy_draft.command(name="board")
    async def draft_board(self, ctx):
        """Open the draft board and make your pick."""
        if not self.players_cache:
            return await ctx.send("Player data is still loading. Try again shortly.")

        state = await self.config.guild(ctx.guild).draft_state()
        if not state["is_active"]:
            return await ctx.send("The draft is not currently active.")

        uid_str = str(ctx.author.id)
        if uid_str not in state["order"]:
            return await ctx.send("You are not a participant in this draft.")

        order = state["order"]
        current_pick = state["current_pick"]
        on_clock_uid = order[current_pick]

        rosters = await self.config.guild(ctx.guild).rosters()
        taken = {int(pid) for rd in rosters.values() if isinstance(rd, dict) for pid in rd.keys()}
        available = [p for p in self.players_cache if p["id"] not in taken]
        scoring = await self.config.guild(ctx.guild).scoring_system()
        slots = await self.config.guild(ctx.guild).team_slots()

        on_clock_member = ctx.guild.get_member(int(on_clock_uid))
        on_clock_name = on_clock_member.display_name if on_clock_member else f"<@{on_clock_uid}>"

        embed = discord.Embed(
            title="📋 Draft Board",
            description=(
                f"**Pick #{current_pick + 1}** of {len(order)}\n"
                f"🎯 On the clock: **{on_clock_name}**\n\n"
                f"{len(available)} players remaining."
            ),
            color=discord.Color.green(),
        )

        view = PlayerListPagination(self, ctx, available, scoring, slots, action_type="draft")
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        await view.update_view(msg)

    @fantasy_draft.command(name="picks")
    async def draft_picks(self, ctx):
        """View all picks made so far in the draft."""
        state = await self.config.guild(ctx.guild).draft_state()
        picks = state.get("picks", [])
        if not picks:
            return await ctx.send("No picks have been made yet.")

        embed = discord.Embed(
            title="📋 Draft Picks History",
            color=discord.Color.blue(),
        )
        lines = []
        for pick in picks:
            member = ctx.guild.get_member(int(pick["user_id"]))
            name = member.display_name if member else f"<@{pick['user_id']}>"
            lines.append(f"**#{pick['pick_number']}** — {name} → {pick['player_name']}")

        # Discord embed field limit is 1024 chars
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 1024:
                embed.add_field(name="\u200b", value=chunk, inline=False)
                chunk = ""
            chunk += line + "\n"
        if chunk:
            embed.add_field(name="\u200b", value=chunk, inline=False)

        order = state.get("order", [])
        total = len(order)
        embed.set_footer(text=f"{len(picks)}/{total} picks made")
        await ctx.send(embed=embed)
