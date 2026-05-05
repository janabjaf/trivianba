"""
Discord UI Views (Buttons & Dropdowns) for NBAdex.
All views are timeout-aware and use interaction checks to prevent abuse.
"""
import discord
from typing import Callable, List, Optional


class JoinDraftView(discord.ui.View):
    """Persistent Join button shown when a draft is waiting for participants."""

    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=3600)  # 1 hour
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="✋ Join Draft", style=discord.ButtonStyle.green, custom_id="nbadex_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ctx_like = interaction
        draft = await self.cog.config.guild(interaction.guild).active_draft()
        if not draft:
            await interaction.response.send_message("No active draft found.", ephemeral=True)
            return
        if draft.get("status") != "waiting":
            await interaction.response.send_message("The draft has already started or ended.", ephemeral=True)
            return
        user_id = str(interaction.user.id)
        if user_id in draft["participants"]:
            await interaction.response.send_message("You've already joined this draft!", ephemeral=True)
            return
        if len(draft["participants"]) >= draft["num_teams"]:
            await interaction.response.send_message("This draft is already full!", ephemeral=True)
            return

        draft["participants"].append(user_id)
        draft["teams"][user_id] = []
        if draft["mode"] == "auction":
            draft["budgets"][user_id] = 200

        await self.cog.config.guild(interaction.guild).active_draft.set(draft)

        joined_count = len(draft["participants"])
        max_teams = draft["num_teams"]

        embed = discord.Embed(
            title="✅ Joined the Draft!",
            description=f"{interaction.user.mention} joined! ({joined_count}/{max_teams} teams)",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @discord.ui.button(label="📋 View Roster", style=discord.ButtonStyle.blurple, custom_id="nbadex_viewroster")
    async def view_roster_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        draft = await self.cog.config.guild(interaction.guild).active_draft()
        if not draft:
            await interaction.response.send_message("No active draft.", ephemeral=True)
            return
        participants = draft.get("participants", [])
        if not participants:
            await interaction.response.send_message("No one has joined yet.", ephemeral=True)
            return

        lines = []
        for uid in participants:
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f"User {uid}"
            lines.append(f"• {name}")

        embed = discord.Embed(
            title="📋 Draft Participants",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PickPlayerView(discord.ui.View):
    """
    Dropdown view for picking a player from the top available players.
    Shows up to 25 players at a time with navigation.
    """

    def __init__(self, cog, available_players: List[dict], page: int = 0, channel_id: int = None):
        super().__init__(timeout=120)
        self.cog = cog
        self.available_players = available_players  # sorted by ovr desc
        self.page = page
        self.channel_id = channel_id
        self._build_select()
        self._build_nav_buttons()

    def _build_select(self):
        # Remove existing selects
        for child in list(self.children):
            if isinstance(child, discord.ui.Select):
                self.remove_item(child)

        start = self.page * 20
        end = start + 20
        page_players = self.available_players[start:end]

        if not page_players:
            return

        options = []
        for p in page_players:
            pos_str = "/".join(p["positions"])
            era = p.get("era", "")
            label = f"{p['name']} ({pos_str})"[:100]
            desc = f"OVR: {p['ovr']} | {p['team']} | {era}"[:100]
            options.append(discord.SelectOption(
                label=label,
                value=p["name"],
                description=desc,
                emoji=self._tier_emoji(p.get("tier", 3)),
            ))

        select = discord.ui.Select(
            placeholder=f"🏀 Select a player to draft (Page {self.page + 1})...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"nbadex_pick_{self.page}"
        )
        select.callback = self.select_callback
        self.add_item(select)

    def _build_nav_buttons(self):
        # Remove existing buttons
        for child in list(self.children):
            if isinstance(child, discord.ui.Button):
                self.remove_item(child)

        total_pages = max(1, (len(self.available_players) + 19) // 20)

        prev_btn = discord.ui.Button(
            label="◀ Prev",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page == 0),
            custom_id="nbadex_prev"
        )
        prev_btn.callback = self.prev_callback
        self.add_item(prev_btn)

        page_btn = discord.ui.Button(
            label=f"Page {self.page + 1}/{total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            custom_id="nbadex_page_indicator"
        )
        self.add_item(page_btn)

        next_btn = discord.ui.Button(
            label="Next ▶",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total_pages - 1),
            custom_id="nbadex_next"
        )
        next_btn.callback = self.next_callback
        self.add_item(next_btn)

        auto_btn = discord.ui.Button(
            label="🤖 Auto Pick",
            style=discord.ButtonStyle.blurple,
            custom_id="nbadex_autopick_btn"
        )
        auto_btn.callback = self.autopick_callback
        self.add_item(auto_btn)

    def _tier_emoji(self, tier: int) -> str:
        return {1: "👑", 2: "⭐", 3: "🔥", 4: "💎", 5: "🏃"}.get(tier, "🏀")

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        select = None
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                select = child
                break
        if not select:
            return
        player_name = select.values[0]
        await self.cog._process_pick(interaction, player_name, from_view=True)
        self.stop()

    async def prev_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        self._build_select()
        self._build_nav_buttons()
        await interaction.edit_original_response(view=self)

    async def next_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        total_pages = max(1, (len(self.available_players) + 19) // 20)
        self.page = min(total_pages - 1, self.page + 1)
        self._build_select()
        self._build_nav_buttons()
        await interaction.edit_original_response(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the current drafter can interact — blocks any other user from hijacking a pick."""
        draft = await self.cog.config.guild(interaction.guild).active_draft()
        if not draft or draft.get("status") != "active":
            await interaction.response.send_message("No active draft right now.", ephemeral=True)
            return False
        order = draft.get("draft_order", [])
        idx = draft.get("current_pick_index", 0)
        if not order or idx >= len(order):
            await interaction.response.send_message("Draft order error.", ephemeral=True)
            return False
        current_uid = order[idx]
        if str(interaction.user.id) != current_uid:
            member = interaction.guild.get_member(int(current_uid))
            name = member.display_name if member else "another player"
            await interaction.response.send_message(
                f"⏳ It's **{name}'s** turn to pick — not yours!",
                ephemeral=True,
            )
            return False
        return True

    async def autopick_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.cog._process_pick(interaction, self.available_players[0]["name"], from_view=True, auto=True)
        self.stop()


class AuctionBidView(discord.ui.View):
    """
    View for auction draft bidding. Shows current player, top bid, and bid buttons.
    """

    def __init__(self, cog, player_name: str, current_bid: int, current_leader: str):
        super().__init__(timeout=30)
        self.cog = cog
        self.player_name = player_name
        self.current_bid = current_bid
        self.current_leader = current_leader
        self._build()

    def _build(self):
        for child in list(self.children):
            self.remove_item(child)

        for amount in [1, 5, 10, 25, 50]:
            btn = discord.ui.Button(
                label=f"+${amount}",
                style=discord.ButtonStyle.green,
                custom_id=f"nbadex_bid_{amount}"
            )
            btn.callback = self._make_bid_callback(amount)
            self.add_item(btn)

        pass_btn = discord.ui.Button(
            label="❌ Pass",
            style=discord.ButtonStyle.danger,
            custom_id="nbadex_bid_pass"
        )
        pass_btn.callback = self.pass_callback
        self.add_item(pass_btn)

    def _make_bid_callback(self, amount: int):
        async def callback(interaction: discord.Interaction):
            # Must defer BEFORE any async processing or Discord kills the interaction
            await interaction.response.defer(ephemeral=True)
            new_bid = self.current_bid + amount
            await self.cog._process_bid(interaction, self.player_name, new_bid)
        return callback

    async def pass_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.cog._process_bid_pass(interaction, self.player_name)


class ConfirmView(discord.ui.View):
    """Simple Yes/No confirmation view."""

    def __init__(self, *, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.confirmed: Optional[bool] = None
        self.interaction: Optional[discord.Interaction] = None

    @discord.ui.button(label="✅ Yes", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.interaction = interaction
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="❌ No", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.interaction = interaction
        self.stop()
        await interaction.response.defer()


class TeamRosterView(discord.ui.View):
    """View for displaying a team's full roster with position filtering."""

    def __init__(self, embed_builder: Callable, rosters: dict):
        super().__init__(timeout=120)
        self.embed_builder = embed_builder
        self.rosters = rosters
        self.names = list(rosters.keys())
        self.current_idx = 0
        self._update_buttons()

    def _update_buttons(self):
        for child in list(self.children):
            if isinstance(child, discord.ui.Button):
                self.remove_item(child)

        prev = discord.ui.Button(label="◀ Prev Team", style=discord.ButtonStyle.secondary,
                                  disabled=(self.current_idx == 0), custom_id="tr_prev")
        prev.callback = self.prev_team
        self.add_item(prev)

        indicator = discord.ui.Button(
            label=f"{self.names[self.current_idx]} ({self.current_idx + 1}/{len(self.names)})",
            style=discord.ButtonStyle.primary, disabled=True, custom_id="tr_ind"
        )
        self.add_item(indicator)

        nxt = discord.ui.Button(label="Next Team ▶", style=discord.ButtonStyle.secondary,
                                 disabled=(self.current_idx >= len(self.names) - 1), custom_id="tr_next")
        nxt.callback = self.next_team
        self.add_item(nxt)

    async def prev_team(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_idx = max(0, self.current_idx - 1)
        self._update_buttons()
        embed = self.embed_builder(self.names[self.current_idx], self.rosters[self.names[self.current_idx]])
        await interaction.edit_original_response(embed=embed, view=self)

    async def next_team(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_idx = min(len(self.names) - 1, self.current_idx + 1)
        self._update_buttons()
        embed = self.embed_builder(self.names[self.current_idx], self.rosters[self.names[self.current_idx]])
        await interaction.edit_original_response(embed=embed, view=self)


class RankingsView(discord.ui.View):
    """Paginated rankings view with position filter dropdown."""

    def __init__(self, cog, players: List[dict], position: str = "ALL", page: int = 0):
        super().__init__(timeout=120)
        self.cog = cog
        self.all_players = players
        self.position = position
        self.page = page
        self._filtered = self._filter()
        self._build()

    def _filter(self) -> List[dict]:
        if self.position == "ALL":
            return self.all_players
        return [p for p in self.all_players if self.position in p["positions"]]

    def _build(self):
        for child in list(self.children):
            self.remove_item(child)

        pos_select = discord.ui.Select(
            placeholder=f"Filter by position: {self.position}",
            options=[
                discord.SelectOption(label="All Players", value="ALL", default=(self.position == "ALL")),
                discord.SelectOption(label="Point Guard (PG)", value="PG", default=(self.position == "PG")),
                discord.SelectOption(label="Shooting Guard (SG)", value="SG", default=(self.position == "SG")),
                discord.SelectOption(label="Small Forward (SF)", value="SF", default=(self.position == "SF")),
                discord.SelectOption(label="Power Forward (PF)", value="PF", default=(self.position == "PF")),
                discord.SelectOption(label="Center (C)", value="C", default=(self.position == "C")),
            ],
            custom_id="rankings_pos_filter"
        )
        pos_select.callback = self.position_filter_callback
        self.add_item(pos_select)

        per_page = 15
        total_pages = max(1, (len(self._filtered) + per_page - 1) // per_page)

        prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary,
                                      disabled=(self.page == 0), custom_id="rank_prev")
        prev_btn.callback = self.prev_page
        self.add_item(prev_btn)

        page_btn = discord.ui.Button(
            label=f"Page {self.page + 1}/{total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            custom_id="rank_page"
        )
        self.add_item(page_btn)

        next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary,
                                      disabled=(self.page >= total_pages - 1), custom_id="rank_next")
        next_btn.callback = self.next_page
        self.add_item(next_btn)

    def build_embed(self) -> discord.Embed:
        per_page = 15
        start = self.page * per_page
        end = start + per_page
        page_players = self._filtered[start:end]

        pos_label = self.position if self.position != "ALL" else "All Positions"
        embed = discord.Embed(
            title=f"🏀 NBA All-Time Rankings — {pos_label}",
            color=discord.Color.orange(),
        )

        if not page_players:
            embed.description = "No players found for this filter."
            return embed

        lines = []
        for i, p in enumerate(page_players):
            rank = start + i + 1
            tier_emoji = {1: "👑", 2: "⭐", 3: "🔥", 4: "💎", 5: "🏃"}.get(p.get("tier", 3), "🏀")
            pos_str = "/".join(p["positions"])
            lines.append(
                f"`#{rank:>3}` {tier_emoji} **{p['name']}** `OVR {p['ovr']}` — {pos_str} | {p['era']}"
            )

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"{len(self._filtered)} players total | Use dropdown to filter by position")
        return embed

    async def position_filter_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        for child in self.children:
            if isinstance(child, discord.ui.Select):
                self.position = child.values[0]
                break
        self.page = 0
        self._filtered = self._filter()
        self._build()
        await interaction.edit_original_response(embed=self.build_embed(), view=self)

    async def prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.page = max(0, self.page - 1)
        self._build()
        await interaction.edit_original_response(embed=self.build_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        per_page = 15
        total_pages = max(1, (len(self._filtered) + per_page - 1) // per_page)
        self.page = min(total_pages - 1, self.page + 1)
        self._build()
        await interaction.edit_original_response(embed=self.build_embed(), view=self)
