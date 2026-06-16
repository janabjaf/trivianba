import asyncio
import discord
from typing import List, Optional, Any, Dict
from abc import ABC, abstractmethod


# ── Utility Views ─────────────────────────────────────────────────────────────

class VoteButton(discord.ui.Button):
    def __init__(self, label: str, choice_idx: int, view_ref: "VotingView"):
        super().__init__(
            label=label[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"vb_{id(view_ref)}_{choice_idx}",
            row=choice_idx // 5,
        )
        self.choice_idx = choice_idx
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction):
        vr = self.view_ref
        if interaction.user not in vr.eligible_voters:
            await interaction.response.send_message("You are not in this game!", ephemeral=True)
            return
        if interaction.user in vr.votes:
            await interaction.response.send_message("You already voted!", ephemeral=True)
            return
        vr.votes[interaction.user] = self.choice_idx
        await interaction.response.send_message(
            f"✅ Voted for **{vr.options[self.choice_idx]}**!", ephemeral=True
        )
        if len(vr.votes) >= len(vr.eligible_voters):
            vr.stop()


class VoteSelect(discord.ui.Select):
    def __init__(self, options: List[str], view_ref: "VotingView"):
        super().__init__(
            placeholder="Choose your vote...",
            options=[
                discord.SelectOption(label=o[:100], value=str(i))
                for i, o in enumerate(options[:25])
            ],
            custom_id=f"vs_{id(view_ref)}",
        )
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction):
        vr = self.view_ref
        if interaction.user not in vr.eligible_voters:
            await interaction.response.send_message("You are not in this game!", ephemeral=True)
            return
        if interaction.user in vr.votes:
            await interaction.response.send_message("You already voted!", ephemeral=True)
            return
        choice = int(self.values[0])
        vr.votes[interaction.user] = choice
        await interaction.response.send_message(
            f"✅ Voted for **{vr.options[choice]}**!", ephemeral=True
        )
        if len(vr.votes) >= len(vr.eligible_voters):
            vr.stop()


class VotingView(discord.ui.View):
    """Reusable voting view. Supports up to 25 options via buttons (≤5) or select (≤25)."""

    def __init__(self, eligible_voters: list, options: List[str], timeout: float = 30.0,
                 exclude: Optional[discord.Member] = None):
        super().__init__(timeout=timeout)
        self.votes: Dict[discord.Member, int] = {}
        self.eligible_voters = [v for v in eligible_voters if v != exclude]
        self.options = options

        if len(options) <= 5:
            for i, opt in enumerate(options):
                self.add_item(VoteButton(label=opt, choice_idx=i, view_ref=self))
        else:
            self.add_item(VoteSelect(options=options, view_ref=self))

    def tally(self) -> Dict[int, int]:
        counts: Dict[int, int] = {}
        for choice in self.votes.values():
            counts[choice] = counts.get(choice, 0) + 1
        return counts

    def winner_idx(self) -> Optional[int]:
        t = self.tally()
        if not t:
            return None
        return max(t, key=t.get)


class SubmitButton(discord.ui.Button):
    """Button that opens a modal for text submission."""

    def __init__(self, label: str, modal_factory, row: int = 0):
        super().__init__(label=label, style=discord.ButtonStyle.green, row=row)
        self._modal_factory = modal_factory

    async def callback(self, interaction: discord.Interaction):
        modal = self._modal_factory(interaction.user)
        await interaction.response.send_modal(modal)


class SubmitView(discord.ui.View):
    """View with a single submit button."""

    def __init__(self, label: str, modal_factory, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.add_item(SubmitButton(label=label, modal_factory=modal_factory))


class LobbyView(discord.ui.View):
    """The join/leave lobby view used before every game starts."""

    def __init__(self, game: "BaseGame"):
        super().__init__(timeout=35.0)
        self.game = game
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label="🎮  Join Game", style=discord.ButtonStyle.green, row=0)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self.game
        if interaction.user in g.players:
            await interaction.response.send_message("You're already in the game!", ephemeral=True)
            return
        if len(g.players) >= g.GAME_INFO["max_players"]:
            await interaction.response.send_message("Sorry, the game is full!", ephemeral=True)
            return
        g.players.append(interaction.user)
        await interaction.response.send_message(
            f"✅ You joined **{g.GAME_INFO['name']}**! ({len(g.players)}/{g.GAME_INFO['max_players']} players)",
            ephemeral=True,
        )
        await self.refresh_lobby()

    @discord.ui.button(label="🚪  Leave", style=discord.ButtonStyle.red, row=0)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        g = self.game
        if interaction.user not in g.players:
            await interaction.response.send_message("You are not in this game!", ephemeral=True)
            return
        g.players.remove(interaction.user)
        await interaction.response.send_message("You left the game.", ephemeral=True)
        await self.refresh_lobby()

    async def refresh_lobby(self):
        if self.message:
            try:
                await self.message.edit(embed=self.game.make_lobby_embed())
            except discord.HTTPException:
                pass

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ── Ephemeral Role View ────────────────────────────────────────────────────────

class SecretRoleView(discord.ui.View):
    """One shared button in the channel. Each player clicks it to see their embed ephemerally."""

    def __init__(
        self,
        roles: Dict[discord.Member, discord.Embed],
        button_label: str = "🔍 View My Secret Role",
    ):
        super().__init__(timeout=300.0)
        self._roles = roles
        btn = discord.ui.Button(label=button_label[:80], style=discord.ButtonStyle.green)
        btn.callback = self._on_click
        self.add_item(btn)

    async def _on_click(self, interaction: discord.Interaction):
        embed = self._roles.get(interaction.user)
        if embed is None:
            await interaction.response.send_message("You're not in this game!", ephemeral=True)
            return
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ── Secret Input View ─────────────────────────────────────────────────────────

class SecretInputView(discord.ui.View):
    """One button for a specific player. Clicking opens a modal so they can type a secret word."""

    def __init__(
        self,
        target: discord.Member,
        modal_title: str,
        field_label: str,
        placeholder: str = "",
        button_label: str = "✏️ Set Your Word",
        timeout: float = 60.0,
    ):
        super().__init__(timeout=timeout)
        self.target = target
        self.value: Optional[str] = None
        self._done = asyncio.Event()
        self._modal_title = modal_title
        self._field_label = field_label
        self._placeholder = placeholder

        btn = discord.ui.Button(label=button_label[:80], style=discord.ButtonStyle.green)
        btn.callback = self._on_click
        self.add_item(btn)

    async def _on_click(self, interaction: discord.Interaction):
        if interaction.user != self.target:
            await interaction.response.send_message(
                f"Only **{self.target.display_name}** can use this button!", ephemeral=True
            )
            return
        if self._done.is_set():
            await interaction.response.send_message("Already submitted!", ephemeral=True)
            return

        view_ref = self
        modal_title = self._modal_title
        field_label = self._field_label
        placeholder = self._placeholder

        class _InputModal(discord.ui.Modal):
            def __init__(self_m):
                super().__init__(title=modal_title[:45])
                self_m.word_input = discord.ui.TextInput(
                    label=field_label[:45],
                    placeholder=placeholder[:100],
                    max_length=100,
                    required=True,
                )
                self_m.add_item(self_m.word_input)

            async def on_submit(self_m, inter: discord.Interaction):
                view_ref.value = self_m.word_input.value.strip()
                await inter.response.send_message("✅ Set! Only you know what it is.", ephemeral=True)
                view_ref._done.set()
                view_ref.stop()

        await interaction.response.send_modal(_InputModal())

    async def wait_for_input(self) -> Optional[str]:
        """Await up to timeout seconds for the player to submit. Returns value or None."""
        try:
            await asyncio.wait_for(self._done.wait(), timeout=self.timeout)
        except asyncio.TimeoutError:
            pass
        return self.value


# ── Base Game ─────────────────────────────────────────────────────────────────

class BaseGame(ABC):
    GAME_INFO: Dict[str, Any] = {
        "name": "Base Game",
        "description": "Base game class",
        "min_players": 2,
        "max_players": 20,
        "emoji": "🎮",
        "duration": "varies",
        "category": "General",
    }

    def __init__(self):
        self.players: List[discord.Member] = []
        self.channel: Optional[discord.TextChannel] = None
        self.cog: Any = None
        self.running: bool = False
        self._stop_event = asyncio.Event()
        self._active_views: List[discord.ui.View] = []

    # ── Lobby ─────────────────────────────────────────────────────────────────

    def make_lobby_embed(self) -> discord.Embed:
        info = self.GAME_INFO
        player_list = "\n".join(f"• {p.display_name}" for p in self.players) or "*Nobody yet…*"
        embed = discord.Embed(
            title=f"{info['emoji']}  {info['name']} — Lobby",
            description=f"*{info['description']}*\n\n"
                        f"**Duration:** {info['duration']}  •  "
                        f"**Players needed:** {info['min_players']}–{info['max_players']}\n\n"
                        f"**Joined ({len(self.players)}/{info['max_players']}):**\n{player_list}",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="⏱ Game starts in 30 seconds • Click Join to play!")
        return embed

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def force_end(self):
        self.running = False
        self._stop_event.set()
        for view in self._active_views:
            try:
                view.stop()
                for item in view.children:
                    item.disabled = True
            except Exception:
                pass
        try:
            embed = discord.Embed(
                title="🛑  Game Ended",
                description="The game was forcefully ended by an admin.",
                color=discord.Color.red(),
            )
            await self.channel.send(embed=embed)
        except Exception:
            pass

    def track_view(self, view: discord.ui.View) -> discord.ui.View:
        self._active_views.append(view)
        return view

    async def wait_or_stop(self, seconds: float) -> bool:
        """Sleep for `seconds`. Returns True if force-stopped early."""
        stop_task = asyncio.ensure_future(self._stop_event.wait())
        sleep_task = asyncio.ensure_future(asyncio.sleep(seconds))
        done, pending = await asyncio.wait(
            [stop_task, sleep_task], return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
        return self._stop_event.is_set()

    # ── Ephemeral reveals ─────────────────────────────────────────────────────

    async def reveal_roles(
        self,
        roles: Dict[discord.Member, discord.Embed],
        title: str = "🔐 Roles Assigned!",
        description: str = "Click the button below to see your role — **only you** will see it.",
        button_label: str = "🔍 View My Secret Role",
    ) -> discord.Message:
        """Post a channel message with a button. Each player clicks to see their embed ephemerally."""
        view = self.track_view(SecretRoleView(roles, button_label))
        embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
        return await self.channel.send(embed=embed, view=view)

    async def request_secret_input(
        self,
        target: discord.Member,
        prompt: str,
        modal_title: str,
        field_label: str,
        placeholder: str = "",
        button_label: str = "✏️ Set Your Word",
        timeout: float = 60.0,
    ) -> Optional[str]:
        """Post a channel message with a modal button for `target`. Returns their typed value or None."""
        view = self.track_view(
            SecretInputView(
                target=target,
                modal_title=modal_title,
                field_label=field_label,
                placeholder=placeholder,
                button_label=button_label,
                timeout=timeout,
            )
        )
        embed = discord.Embed(
            title="✏️ Input Required",
            description=prompt,
            color=discord.Color.green(),
        )
        await self.channel.send(embed=embed, view=view)
        return await view.wait_for_input()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def make_embed(
        self, title: str, description: str = "", color: discord.Color = None
    ) -> discord.Embed:
        if color is None:
            color = discord.Color.blurple()
        e = discord.Embed(title=title, description=description, color=color)
        return e

    async def listen_for_answer(
        self,
        check,
        timeout: float = 20.0,
    ) -> Optional[discord.Message]:
        try:
            return await self.cog.bot.wait_for("message", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def players_mention_list(self) -> str:
        return " ".join(p.mention for p in self.players)

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    @abstractmethod
    async def run(self):
        pass
