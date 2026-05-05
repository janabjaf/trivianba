"""
NBAdex — The Ultimate NBA Draft Game for Red-DiscordBot v3.5+
Author: jaffar21

Commands: [p]nbadraft <subcommand>
Draft Modes: Snake, Auction, Best Ball, Random
Features: 400+ all-time players, Discord UI (dropdowns/buttons),
          position requirements, simulation, rankings, player search.
"""
import asyncio
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red

from .players import (
    ALL_PLAYERS,
    get_all_sorted,
    get_player_by_name,
    get_players_by_position,
    get_top_available,
    player_embed_fields,
    search_players,
)
from .simulation import (
    CATEGORIES,
    CATEGORY_LABELS,
    compare_players,
    grade_team,
    simulate_season,
)
from .views import (
    AuctionBidView,
    ConfirmView,
    JoinDraftView,
    PickPlayerView,
    RankingsView,
    TeamRosterView,
)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

DRAFT_MODES = {
    "snake": {
        "name": "Snake Draft",
        "emoji": "🐍",
        "desc": (
            "Classic snake order. Pick 1→N in odd rounds, N→1 in even rounds. "
            "Most common fantasy format — strategy matters most in early rounds."
        ),
    },
    "auction": {
        "name": "Auction Draft",
        "emoji": "💰",
        "desc": (
            "Every manager starts with a $200 budget. Players are nominated one "
            "at a time and managers bid. Every player is fair game — you can have "
            "any player if you're willing to pay."
        ),
    },
    "bestball": {
        "name": "Best Ball Draft",
        "emoji": "🎱",
        "desc": (
            "No management after the draft — the best starting lineup is "
            "automatically selected each week. Focus on roster depth and upside."
        ),
    },
    "random": {
        "name": "Random Draft",
        "emoji": "🎲",
        "desc": (
            "Players are randomly assigned to teams. Pure luck — who gets Jordan? "
            "Great for casual/fun leagues."
        ),
    },
}

# Roster position requirements (slots that MUST be filled)
POSITION_REQUIREMENTS = {
    "PG": 1, "SG": 1, "SF": 1, "PF": 1, "C": 1,
    "G": 1,   # PG or SG
    "F": 1,   # SF or PF
    "UTIL": 1, # Any
}

DEFAULT_ROUNDS = 13
DEFAULT_TEAMS = 8
PICK_TIMEOUT = 120  # seconds per pick
AUCTION_TIMEOUT = 30  # seconds between bids
MAX_BUDGET = 200

COLOR_DRAFT = discord.Color.from_rgb(255, 165, 0)   # NBA orange
COLOR_SUCCESS = discord.Color.green()
COLOR_ERROR = discord.Color.red()
COLOR_INFO = discord.Color.blue()

TIER_EMOJI = {1: "👑", 2: "⭐", 3: "🔥", 4: "💎", 5: "🏃"}

# ──────────────────────────────────────────────────────────────────────────────
# Helper: build snake draft order
# ──────────────────────────────────────────────────────────────────────────────

def build_snake_order(participants: List[str], rounds: int) -> List[str]:
    """Build a full snake draft order for all rounds."""
    order = []
    for r in range(rounds):
        if r % 2 == 0:
            order.extend(participants)
        else:
            order.extend(reversed(participants))
    return order


# ──────────────────────────────────────────────────────────────────────────────
# Main Class
# ──────────────────────────────────────────────────────────────────────────────

class NBAdex(commands.Cog):
    """
    NBAdex — The ultimate NBA all-time player draft game.

    Draft 400+ historical and current NBA players across multiple modes.
    Features snake draft, auction, best ball, and random modes with
    full Discord UI (dropdowns + buttons), rankings, simulation, and more.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=847162938457, force_registration=True)

        default_guild = {
            "active_draft": None,
            "draft_history": [],
        }
        self.config.register_guild(**default_guild)

        # In-memory pick timers: guild_id → asyncio.Task
        self._pick_timers: Dict[int, asyncio.Task] = {}
        # In-memory auction timers: guild_id → asyncio.Task
        self._auction_timers: Dict[int, asyncio.Task] = {}
        # In-memory join messages: guild_id → discord.Message
        self._join_messages: Dict[int, discord.Message] = {}
        # In-memory pick messages: guild_id → discord.Message
        self._pick_messages: Dict[int, discord.Message] = {}

    # ──────────────────────────────────────────────────────────────────────────
    # COMMAND GROUP
    # ──────────────────────────────────────────────────────────────────────────

    @commands.group(name="nbadraft", aliases=["nba", "nbadex"])
    @commands.guild_only()
    async def nbadraft(self, ctx: commands.Context):
        """🏀 NBAdex — NBA All-Time Player Draft System.

        Use `[p]nbadraft create` to start a new draft.
        Use `[p]nbadraft modes` to see all available draft modes.
        Use `[p]nbadraft help` for full command reference.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: create
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="create", aliases=["new", "start"])
    @commands.has_permissions(manage_messages=True)
    async def draft_create(
        self,
        ctx: commands.Context,
        mode: str = "snake",
        rounds: int = DEFAULT_ROUNDS,
        teams: int = DEFAULT_TEAMS,
    ):
        """Create a new NBA draft session.

        **Arguments:**
        - `mode` — Draft mode: `snake`, `auction`, `bestball`, `random` (default: snake)
        - `rounds` — Number of rounds per team (default: 13)
        - `teams` — Max number of teams (default: 8)

        **Examples:**
        - `[p]nbadraft create` — Start a default 13-round snake draft
        - `[p]nbadraft create auction 10 6` — 10-round auction draft for 6 teams
        - `[p]nbadraft create random 8` — 8-round random draft
        """
        mode = mode.lower()
        if mode not in DRAFT_MODES:
            valid = ", ".join(f"`{m}`" for m in DRAFT_MODES)
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Invalid Draft Mode",
                    description=f"Choose from: {valid}",
                    color=COLOR_ERROR,
                )
            )
            return

        if rounds < 1 or rounds > 25:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Invalid Rounds",
                    description="Rounds must be between **1** and **25**.",
                    color=COLOR_ERROR,
                )
            )
            return

        if teams < 2 or teams > 16:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Invalid Team Count",
                    description="Teams must be between **2** and **16**.",
                    color=COLOR_ERROR,
                )
            )
            return

        existing = await self.config.guild(ctx.guild).active_draft()
        if existing and existing.get("status") in ("waiting", "active"):
            await ctx.send(
                embed=discord.Embed(
                    title="⚠️ Draft Already Active",
                    description=(
                        "A draft is already running in this server. "
                        f"Use `{ctx.clean_prefix}nbadraft cancel` to cancel it first."
                    ),
                    color=COLOR_ERROR,
                )
            )
            return

        draft = {
            "mode": mode,
            "rounds": rounds,
            "num_teams": teams,
            "host_id": str(ctx.author.id),
            "channel_id": str(ctx.channel.id),
            "participants": [str(ctx.author.id)],
            "teams": {str(ctx.author.id): []},
            "budgets": {str(ctx.author.id): MAX_BUDGET} if mode == "auction" else {},
            "draft_order": [],
            "current_pick_index": 0,
            "current_round": 1,
            "status": "waiting",
            "autopick_users": [],
            "picks_log": [],
            "nomination_queue": [],
            "current_nomination": None,
            "current_bid": 0,
            "current_bidder": None,
            "bid_passers": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        await self.config.guild(ctx.guild).active_draft.set(draft)

        mode_info = DRAFT_MODES[mode]
        embed = discord.Embed(
            title=f"{mode_info['emoji']} New NBA Draft — {mode_info['name']}",
            color=COLOR_DRAFT,
        )
        embed.add_field(
            name="📋 Settings",
            value=(
                f"**Mode:** {mode_info['emoji']} {mode_info['name']}\n"
                f"**Rounds:** {rounds}\n"
                f"**Max Teams:** {teams}\n"
                f"{'**Budget:** $' + str(MAX_BUDGET) + ' per team' if mode == 'auction' else ''}"
            ),
            inline=True,
        )
        embed.add_field(
            name="📖 How It Works",
            value=mode_info["desc"],
            inline=False,
        )
        embed.add_field(
            name="✅ Participants (1/{})".format(teams),
            value=f"• {ctx.author.mention} *(Host)*",
            inline=False,
        )
        embed.set_footer(
            text=f"Host: {ctx.author.display_name} • Use '{ctx.clean_prefix}nbadraft join' or click below"
        )

        view = JoinDraftView(self, ctx.guild.id)
        msg = await ctx.send(embed=embed, view=view)
        self._join_messages[ctx.guild.id] = msg

        await ctx.send(
            embed=discord.Embed(
                description=(
                    f"✅ Draft created! Others can join with `{ctx.clean_prefix}nbadraft join` "
                    f"or by clicking **Join Draft** above.\n"
                    f"Start when ready: `{ctx.clean_prefix}nbadraft begin`"
                ),
                color=COLOR_SUCCESS,
            )
        )

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: join
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="join")
    async def draft_join(self, ctx: commands.Context):
        """Join the current waiting draft."""
        draft = await self.config.guild(ctx.guild).active_draft()
        if not draft:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ No Active Draft",
                    description=f"Create one with `{ctx.clean_prefix}nbadraft create`.",
                    color=COLOR_ERROR,
                )
            )
            return

        if draft["status"] != "waiting":
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Draft Already Started",
                    description="You can't join after the draft has begun.",
                    color=COLOR_ERROR,
                )
            )
            return

        user_id = str(ctx.author.id)
        if user_id in draft["participants"]:
            await ctx.send(
                embed=discord.Embed(
                    title="⚠️ Already Joined",
                    description="You're already in this draft!",
                    color=COLOR_ERROR,
                )
            )
            return

        if len(draft["participants"]) >= draft["num_teams"]:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Draft Full",
                    description=f"This draft already has the maximum of **{draft['num_teams']}** teams.",
                    color=COLOR_ERROR,
                )
            )
            return

        draft["participants"].append(user_id)
        draft["teams"][user_id] = []
        if draft["mode"] == "auction":
            draft["budgets"][user_id] = MAX_BUDGET

        await self.config.guild(ctx.guild).active_draft.set(draft)

        joined = len(draft["participants"])
        max_t = draft["num_teams"]

        embed = discord.Embed(
            title="✅ Joined the Draft!",
            description=f"{ctx.author.mention} joined! **{joined}/{max_t}** teams filled.",
            color=COLOR_SUCCESS,
        )
        await ctx.send(embed=embed)

        await self._refresh_join_embed(ctx.guild, draft)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: begin
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="begin", aliases=["go", "startdraft"])
    async def draft_begin(self, ctx: commands.Context):
        """Begin the draft (host only). Locks the draft and starts picks."""
        draft = await self.config.guild(ctx.guild).active_draft()
        if not draft:
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        if draft["status"] != "waiting":
            await ctx.send(embed=discord.Embed(title="❌ Draft Already Started", color=COLOR_ERROR))
            return

        if str(ctx.author.id) != draft["host_id"]:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Not the Host",
                    description="Only the draft host can start the draft.",
                    color=COLOR_ERROR,
                )
            )
            return

        if len(draft["participants"]) < 2:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Not Enough Participants",
                    description="You need at least **2** participants to start a draft.",
                    color=COLOR_ERROR,
                )
            )
            return

        if draft["mode"] == "random":
            await self._run_random_draft(ctx, draft)
            return

        # Shuffle participants for randomized draft order
        random.shuffle(draft["participants"])
        draft["status"] = "active"

        if draft["mode"] == "snake":
            draft["draft_order"] = build_snake_order(draft["participants"], draft["rounds"])
        elif draft["mode"] in ("bestball", "auction"):
            draft["draft_order"] = build_snake_order(draft["participants"], draft["rounds"])

        draft["current_pick_index"] = 0
        draft["current_round"] = 1
        await self.config.guild(ctx.guild).active_draft.set(draft)

        # Announce draft order
        await self._announce_draft_start(ctx, draft)

        if draft["mode"] == "auction":
            await self._start_auction_nomination(ctx, draft)
        else:
            await self._prompt_next_pick(ctx, draft)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: pick
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="pick", aliases=["select", "draft"])
    async def draft_pick(self, ctx: commands.Context, *, player_name: str):
        """Pick a player by name during your turn.

        **Example:**
        - `[p]nbadraft pick Michael Jordan`
        - `[p]nbadraft pick LeBron`  *(partial name search)*
        """
        draft = await self.config.guild(ctx.guild).active_draft()
        if not self._is_active(draft):
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        if draft["mode"] == "auction":
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Use Auction Commands",
                    description=f"Use `{ctx.clean_prefix}nbadraft nominate <player>` instead.",
                    color=COLOR_ERROR,
                )
            )
            return

        user_id = str(ctx.author.id)
        current_picker = draft["draft_order"][draft["current_pick_index"]]
        if user_id != current_picker:
            on_deck = self.bot.get_user(int(current_picker))
            name = on_deck.display_name if on_deck else "another player"
            await ctx.send(
                embed=discord.Embed(
                    title="⏳ Not Your Turn",
                    description=f"It's **{name}'s** pick right now.",
                    color=COLOR_ERROR,
                )
            )
            return

        await self._process_pick(ctx, player_name, from_view=False)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: board
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="board", aliases=["picks", "log"])
    async def draft_board(self, ctx: commands.Context):
        """Show the current draft board — all picks made so far."""
        draft = await self.config.guild(ctx.guild).active_draft()
        if not draft:
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        log = draft.get("picks_log", [])
        if not log:
            await ctx.send(
                embed=discord.Embed(
                    title="📋 Draft Board",
                    description="No picks have been made yet.",
                    color=COLOR_INFO,
                )
            )
            return

        mode_info = DRAFT_MODES.get(draft["mode"], {})
        embed = discord.Embed(
            title=f"📋 Draft Board — {mode_info.get('name', 'Draft')}",
            color=COLOR_DRAFT,
        )

        # Group picks by round
        rounds_data: Dict[int, List[str]] = {}
        for entry in log:
            r = entry.get("round", 1)
            rounds_data.setdefault(r, [])
            user = self.bot.get_user(int(entry["user_id"]))
            u_name = user.display_name if user else f"User {entry['user_id']}"
            p = get_player_by_name(entry["player"])
            tier_e = TIER_EMOJI.get(p.get("tier", 5), "🏀") if p else "🏀"
            rounds_data[r].append(f"`{entry['pick_num']:>3}.` {tier_e} **{entry['player']}** → {u_name}")

        for r in sorted(rounds_data.keys()):
            picks_text = "\n".join(rounds_data[r])
            if len(picks_text) > 1024:
                picks_text = picks_text[:1020] + "..."
            embed.add_field(name=f"Round {r}", value=picks_text, inline=False)

        total_picks = len(log)
        total_expected = draft["rounds"] * len(draft["participants"])
        embed.set_footer(text=f"Picks: {total_picks}/{total_expected} • Round {draft['current_round']}/{draft['rounds']}")
        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: team
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="team", aliases=["roster", "myteam"])
    async def draft_team(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """View a team's current roster. Defaults to your own team.

        **Examples:**
        - `[p]nbadraft team` — Your roster
        - `[p]nbadraft team @user` — Another user's roster
        """
        draft = await self.config.guild(ctx.guild).active_draft()
        if not draft:
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        target = user or ctx.author
        user_id = str(target.id)

        if user_id not in draft.get("teams", {}):
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Not in Draft",
                    description=f"{target.display_name} is not in this draft.",
                    color=COLOR_ERROR,
                )
            )
            return

        roster = draft["teams"][user_id]
        embed = self._build_team_embed(target.display_name, roster, draft)
        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: teams
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="teams", aliases=["allteams", "standings"])
    async def draft_teams(self, ctx: commands.Context):
        """View all teams' rosters with navigation buttons."""
        draft = await self.config.guild(ctx.guild).active_draft()
        if not draft:
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        teams = draft.get("teams", {})
        if not teams:
            await ctx.send(embed=discord.Embed(title="No teams yet.", color=COLOR_INFO))
            return

        named_rosters = {}
        for uid, roster in teams.items():
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f"User {uid}"
            named_rosters[name] = roster

        def builder(name, roster):
            return self._build_team_embed(name, roster, draft)

        first_name = list(named_rosters.keys())[0]
        embed = builder(first_name, named_rosters[first_name])
        view = TeamRosterView(builder, named_rosters)
        await ctx.send(embed=embed, view=view)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: remaining
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="remaining", aliases=["available", "pool"])
    async def draft_remaining(self, ctx: commands.Context, position: str = "ALL"):
        """Show remaining available players.

        **Arguments:**
        - `position` — Filter by position: `PG`, `SG`, `SF`, `PF`, `C`, or `ALL` (default)

        **Examples:**
        - `[p]nbadraft remaining` — All available players
        - `[p]nbadraft remaining PG` — Available point guards
        """
        draft = await self.config.guild(ctx.guild).active_draft()
        if not draft:
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        all_drafted = []
        for roster in draft.get("teams", {}).values():
            all_drafted.extend(roster)

        pos = position.upper()
        if pos == "ALL":
            available = get_top_available(all_drafted, limit=300)
        else:
            if pos not in ("PG", "SG", "SF", "PF", "C"):
                await ctx.send(
                    embed=discord.Embed(
                        title="❌ Invalid Position",
                        description="Position must be: `PG`, `SG`, `SF`, `PF`, `C`, or `ALL`",
                        color=COLOR_ERROR,
                    )
                )
                return
            all_pos = get_players_by_position(pos)
            excluded = {n.lower() for n in all_drafted}
            available = [p for p in all_pos if p["name"].lower() not in excluded]

        if not available:
            await ctx.send(embed=discord.Embed(title="No available players!", color=COLOR_INFO))
            return

        pos_label = pos if pos != "ALL" else "All Positions"
        embed = discord.Embed(
            title=f"🏀 Available Players — {pos_label}",
            color=COLOR_INFO,
        )

        lines = []
        for i, p in enumerate(available[:30]):
            tier_e = TIER_EMOJI.get(p.get("tier", 5), "🏀")
            pos_str = "/".join(p["positions"])
            lines.append(f"`#{i+1:>3}` {tier_e} **{p['name']}** `{p['ovr']} OVR` — {pos_str} | {p['era']}")

        embed.description = "\n".join(lines)
        if len(available) > 30:
            embed.set_footer(text=f"Showing top 30 of {len(available)} available players")
        else:
            embed.set_footer(text=f"{len(available)} players available")

        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: player
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="player", aliases=["stats", "lookup"])
    async def draft_player(self, ctx: commands.Context, *, name: str):
        """Look up detailed info and stats for any NBA player.

        **Example:**
        - `[p]nbadraft player Michael Jordan`
        - `[p]nbadraft player Wilt`
        """
        results = search_players(name, limit=5)
        if not results:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Player Not Found",
                    description=f"No player found matching **{name}**. Try a different spelling.",
                    color=COLOR_ERROR,
                )
            )
            return

        p = results[0]
        fields = player_embed_fields(p)
        tier_e = TIER_EMOJI.get(p.get("tier", 5), "🏀")

        embed = discord.Embed(
            title=f"{tier_e} {p['name']}",
            color=COLOR_DRAFT,
        )
        embed.add_field(name="Position", value=fields["pos"], inline=True)
        embed.add_field(name="Era", value=p.get("era", "Unknown"), inline=True)
        embed.add_field(name="Team", value=p.get("team", "N/A"), inline=True)
        embed.add_field(name="Status", value=fields["tier"], inline=True)
        embed.add_field(name="Overall", value=f"**{p['ovr']}** / 99", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(
            name="📊 Ratings",
            value=fields["stats"],
            inline=False,
        )

        # Show rating bars
        def bar(val: int) -> str:
            filled = round(val / 10)
            return "█" * filled + "░" * (10 - filled) + f" {val}"

        embed.add_field(
            name="📈 Visual Ratings",
            value=(
                f"`PTS` {bar(p['pts'])}\n"
                f"`REB` {bar(p['reb'])}\n"
                f"`AST` {bar(p['ast'])}\n"
                f"`DEF` {bar(p['defense'])}\n"
                f"`3PT` {bar(p['three'])}"
            ),
            inline=False,
        )

        if len(results) > 1:
            others = ", ".join(r["name"] for r in results[1:])
            embed.set_footer(text=f"Showing closest match. Others: {others}")
        else:
            embed.set_footer(text="Use [p]nbadraft rankings to browse all players")

        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: search
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="search", aliases=["find", "s"])
    async def draft_search(self, ctx: commands.Context, *, query: str):
        """Search for players by name.

        **Example:**
        - `[p]nbadraft search james` — Find all players named James
        - `[p]nbadraft search jordan` — Find Jordan players
        """
        results = search_players(query, limit=15)
        if not results:
            await ctx.send(
                embed=discord.Embed(
                    title="🔍 No Results",
                    description=f"No players found matching **{query}**.",
                    color=COLOR_ERROR,
                )
            )
            return

        embed = discord.Embed(
            title=f"🔍 Search Results for \"{query}\"",
            color=COLOR_INFO,
        )
        lines = []
        for p in results:
            tier_e = TIER_EMOJI.get(p.get("tier", 5), "🏀")
            pos_str = "/".join(p["positions"])
            lines.append(f"{tier_e} **{p['name']}** `{p['ovr']} OVR` — {pos_str} | {p['era']}")
        embed.description = "\n".join(lines)
        embed.set_footer(text=f"{len(results)} results • Use [p]nbadraft player <name> for full stats")
        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: rankings
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="rankings", aliases=["rank", "top"])
    async def draft_rankings(self, ctx: commands.Context, position: str = "ALL"):
        """Browse all-time player rankings with interactive position filter.

        **Arguments:**
        - `position` — `PG`, `SG`, `SF`, `PF`, `C`, or `ALL` (default)

        **Example:**
        - `[p]nbadraft rankings` — All-time rankings
        - `[p]nbadraft rankings C` — All-time center rankings
        """
        pos = position.upper()
        players = get_all_sorted()
        view = RankingsView(self, players, position=pos)
        embed = view.build_embed()
        await ctx.send(embed=embed, view=view)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: status
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="status", aliases=["current"])
    async def draft_status(self, ctx: commands.Context):
        """Show the current draft status and settings."""
        draft = await self.config.guild(ctx.guild).active_draft()
        if not draft:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ No Active Draft",
                    description=f"Start one with `{ctx.clean_prefix}nbadraft create`.",
                    color=COLOR_ERROR,
                )
            )
            return

        mode_info = DRAFT_MODES.get(draft["mode"], {})
        status = draft.get("status", "waiting")
        status_str = {"waiting": "⏳ Waiting", "active": "🟢 Active", "completed": "✅ Completed"}.get(status, status)

        embed = discord.Embed(
            title=f"📊 Draft Status — {mode_info.get('name', 'Draft')}",
            color=COLOR_DRAFT,
        )
        embed.add_field(name="Status", value=status_str, inline=True)
        embed.add_field(name="Mode", value=f"{mode_info.get('emoji', '')} {mode_info.get('name', '')}", inline=True)
        embed.add_field(name="Rounds", value=f"{draft['current_round']}/{draft['rounds']}", inline=True)

        participants = draft.get("participants", [])
        embed.add_field(
            name=f"Teams ({len(participants)}/{draft['num_teams']})",
            value="\n".join(
                f"• {ctx.guild.get_member(int(uid)).display_name if ctx.guild.get_member(int(uid)) else uid}"
                for uid in participants
            ) or "None",
            inline=False,
        )

        if status == "active":
            idx = draft["current_pick_index"]
            if idx < len(draft["draft_order"]):
                cur_uid = draft["draft_order"][idx]
                cur_user = ctx.guild.get_member(int(cur_uid))
                cur_name = cur_user.display_name if cur_user else cur_uid
                total_picks = len(draft["picks_log"])
                embed.add_field(
                    name="🎯 Current Pick",
                    value=f"**{cur_name}** — Pick #{total_picks + 1}",
                    inline=False,
                )
            if draft["mode"] == "auction":
                budgets = draft.get("budgets", {})
                budget_lines = []
                for uid, budget in budgets.items():
                    m = ctx.guild.get_member(int(uid))
                    n = m.display_name if m else uid
                    budget_lines.append(f"• {n}: **${budget}**")
                embed.add_field(name="💰 Budgets", value="\n".join(budget_lines) or "N/A", inline=False)

        total_picks = len(draft.get("picks_log", []))
        embed.set_footer(text=f"Total picks made: {total_picks}")
        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: simulate
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="simulate", aliases=["sim", "results", "winner"])
    async def draft_simulate(self, ctx: commands.Context):
        """Simulate a full season and determine the draft champion.

        Simulates head-to-head matchups across 8 statistical categories:
        Points, Rebounds, Assists, Blocks, Steals, 3PM, FG%, FT%
        """
        draft = await self.config.guild(ctx.guild).active_draft()
        if not draft:
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        teams = draft.get("teams", {})
        # At least 2 teams with players
        filled = {uid: r for uid, r in teams.items() if r}
        if len(filled) < 2:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Not Enough Teams",
                    description="At least **2** teams need players to simulate.",
                    color=COLOR_ERROR,
                )
            )
            return

        # Build named teams
        named_teams = {}
        for uid, roster in filled.items():
            member = ctx.guild.get_member(int(uid))
            name = member.display_name if member else f"User {uid}"
            named_teams[name] = roster

        thinking = await ctx.send(
            embed=discord.Embed(
                title="⚙️ Simulating the Season...",
                description=(
                    "Running matchups. Crunching stats. Writing history.\n"
                    "This might take a moment — championship dynasties aren't built overnight."
                ),
                color=COLOR_INFO,
            )
        )

        await asyncio.sleep(2.0)
        results = simulate_season(named_teams)
        narrative = results.get("narrative", {})
        await thinking.delete()

        # ── Embed 1: Pre-Season Power Rankings ──
        pre_season = narrative.get("pre_season", [])
        pre_embed = discord.Embed(
            title="📊 Pre-Season Power Rankings",
            color=discord.Color.from_rgb(30, 130, 200),
        )
        if pre_season:
            lines = []
            for rank, team, analysis in pre_season:
                lines.append(f"**{rank} {team}**\n{analysis}")
            pre_embed.description = "\n\n".join(lines)
        else:
            pre_embed.description = "Season preview not available."
        pre_embed.set_footer(text="Predictions based on roster strength, depth, and star power.")
        await ctx.send(embed=pre_embed)

        # ── Embed 2: Season Highlights ──
        moments = narrative.get("season_moments", [])
        if moments:
            highlights_embed = discord.Embed(
                title="🔥 Regular Season Highlights",
                description="\n\n".join(moments),
                color=discord.Color.from_rgb(220, 80, 20),
            )
            highlights_embed.set_footer(text="5 moments from a full round-robin season.")
            await ctx.send(embed=highlights_embed)

        # ── Embed 3: Final Standings ──
        standings_embed = discord.Embed(
            title="📋 Regular Season Final Standings",
            color=COLOR_DRAFT,
        )
        standings_lines = []
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
        for i, (name, wins, losses, cw, cl) in enumerate(results["standings"]):
            medal = medals[i] if i < len(medals) else f"`#{i+1}`"
            grade = grade_team(named_teams[name])
            playoff_tag = " 🏀 *PLAYOFF*" if i < 4 else ""
            standings_lines.append(
                f"{medal} **{name}** — {wins}W-{losses}L | Cat: {cw}-{cl} | **{grade}**{playoff_tag}"
            )
        standings_embed.description = "\n".join(standings_lines)
        standings_embed.set_footer(text="Top 4 advance to playoffs. Category wins break ties.")
        await ctx.send(embed=standings_embed)

        # ── Embed 4: Playoff Results with Commentary ──
        playoffs_embed = discord.Embed(
            title="⚔️ Playoff Results",
            color=discord.Color.from_rgb(180, 30, 180),
        )
        for match in results["playoffs"]:
            rnd = match.get("round", "Playoff")
            ta, tb = match["team_a"], match["team_b"]
            cwa = match.get("cat_wins_a", match.get("wins_a", 0))
            cwb = match.get("cat_wins_b", match.get("wins_b", 0))
            winner = match["winner"]
            loser = tb if winner == ta else ta
            commentary = match.get("commentary", "")
            is_final = rnd == "Championship"
            field_text = f"**{winner}** def. {loser} ({cwa}-{cwb} categories)\n{commentary}"
            if len(field_text) > 1024:
                field_text = field_text[:1020] + "..."
            playoffs_embed.add_field(
                name=f"{'🏆' if is_final else '⚔️'} {rnd}: {winner} vs {loser}",
                value=field_text,
                inline=False,
            )
        await ctx.send(embed=playoffs_embed)

        # ── Embed 5: Championship + MVP + Last Place Roast ──
        champion = results["champion"]
        runner_up = results.get("runner_up", "")
        mvp = results["mvp"]
        champ_speech = narrative.get("champ_speech", f"🏆 **{champion}** wins it all!")
        last_roast = narrative.get("last_place_roast", "")

        champ_embed = discord.Embed(
            title=f"🏆 CHAMPIONSHIP — {champion}",
            description=champ_speech,
            color=discord.Color.gold(),
        )

        # Champion's roster top 3
        champ_roster = named_teams.get(champion, [])
        top_3 = sorted(
            [get_player_by_name(p) for p in champ_roster if get_player_by_name(p)],
            key=lambda x: x["ovr"], reverse=True,
        )[:3]
        if top_3:
            champ_embed.add_field(
                name="💎 Championship Roster (Top 3)",
                value="\n".join(
                    f"{TIER_EMOJI.get(p['tier'], '🏀')} **{p['name']}** — OVR {p['ovr']}"
                    for p in top_3
                ),
                inline=True,
            )

        # Category breakdown vs runner-up
        if runner_up and runner_up != champion:
            champ_scores = results["team_scores"].get(champion, {})
            runner_scores = results["team_scores"].get(runner_up, {})
            if champ_scores and runner_scores:
                cat_lines = []
                for cat in CATEGORIES:
                    c_val = round(champ_scores.get(cat, 0), 1)
                    r_val = round(runner_scores.get(cat, 0), 1)
                    mark = "✅" if c_val >= r_val else "❌"
                    cat_lines.append(f"{mark} **{CATEGORY_LABELS[cat]}:** {c_val} vs {r_val}")
                champ_embed.add_field(
                    name=f"📊 Final Breakdown vs {runner_up}",
                    value="\n".join(cat_lines),
                    inline=False,
                )

        if last_roast:
            champ_embed.add_field(name="\u200b", value=last_roast, inline=False)

        await ctx.send(embed=champ_embed)

        # Save to history
        history = await self.config.guild(ctx.guild).draft_history()
        history.append({
            "champion": champion,
            "mvp": mvp,
            "date": datetime.now(timezone.utc).isoformat(),
            "mode": draft["mode"],
            "participants": len(named_teams),
        })
        await self.config.guild(ctx.guild).draft_history.set(history[-10:])  # Keep last 10

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: compare
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="compare", aliases=["vs", "h2h"])
    async def draft_compare(self, ctx: commands.Context, *, players: str):
        """Compare two players head-to-head across all stat categories.

        Separate the two player names with **vs**:
        - `[p]nbadraft compare Michael Jordan vs LeBron James`
        - `[p]nbadraft compare Kobe vs Shaq`
        - `[p]nbadraft compare Steph Curry vs Klay Thompson`
        """
        sep = " vs "
        lower = players.lower()
        if sep not in lower:
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Wrong Format",
                    description="Separate the two names with **vs**:\n`[p]nbadraft compare Jordan vs LeBron`",
                    color=COLOR_ERROR,
                )
            )
            return

        idx = lower.index(sep)
        raw_a = players[:idx].strip()
        raw_b = players[idx + len(sep):].strip()

        # Try exact match first, then fuzzy search
        result = compare_players(raw_a, raw_b)
        if not result:
            res_a = search_players(raw_a, limit=1)
            res_b = search_players(raw_b, limit=1)
            if not res_a:
                await ctx.send(
                    embed=discord.Embed(title=f"❌ Player not found: **{raw_a}**", color=COLOR_ERROR)
                )
                return
            if not res_b:
                await ctx.send(
                    embed=discord.Embed(title=f"❌ Player not found: **{raw_b}**", color=COLOR_ERROR)
                )
                return
            result = compare_players(res_a[0]["name"], res_b[0]["name"])

        if not result:
            await ctx.send(
                embed=discord.Embed(title="❌ Could not compare those players.", color=COLOR_ERROR)
            )
            return

        pa = result["player_a"]
        pb = result["player_b"]

        embed = discord.Embed(
            title=f"⚔️  {pa['name']}  vs  {pb['name']}",
            color=discord.Color.orange(),
        )

        # Header: OVR at a glance
        embed.add_field(
            name=pa["name"],
            value=(
                f"**OVR {pa['ovr']}** | {'/'.join(pa['positions'])}\n"
                f"{pa.get('team', '')} | {pa.get('era', '')}"
            ),
            inline=True,
        )
        embed.add_field(
            name="\u200b",
            value=f"**{result['wins_a']}—{result['wins_b']}**\ncategory score",
            inline=True,
        )
        embed.add_field(
            name=pb["name"],
            value=(
                f"**OVR {pb['ovr']}** | {'/'.join(pb['positions'])}\n"
                f"{pb.get('team', '')} | {pb.get('era', '')}"
            ),
            inline=True,
        )

        # Full category breakdown
        cat_lines = []
        for cat, (label, va, vb, winner) in result["categories"].items():
            if winner == pa["name"]:
                bar = f"**{va}** ← {vb}"
                mark = "✅"
            elif winner == pb["name"]:
                bar = f"{va} → **{vb}**"
                mark = "❌"
            else:
                bar = f"{va} = {vb}"
                mark = "🟡"
            cat_lines.append(f"{mark} {label}: {bar}")

        embed.add_field(
            name="📊 Category Breakdown",
            value="\n".join(cat_lines),
            inline=False,
        )

        # Honest verdict
        verdict = result["verdict"]
        if len(verdict) > 1020:
            verdict = verdict[:1017] + "..."
        embed.add_field(name="🎙️ Honest Breakdown", value=verdict, inline=False)

        overall = result["overall_winner"]
        if overall == "TIE":
            embed.set_footer(text="Dead even by OVR — context determines who you pick.")
        else:
            gap = abs(pa["ovr"] - pb["ovr"])
            embed.set_footer(text=f"Edge: {overall} (+{gap} OVR)")

        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: autopick
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="autopick", aliases=["auto"])
    async def draft_autopick(self, ctx: commands.Context):
        """Toggle autopick for yourself. When active, the best available player is picked automatically on your turn."""
        draft = await self.config.guild(ctx.guild).active_draft()
        if not self._is_active(draft):
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        user_id = str(ctx.author.id)
        if user_id not in draft.get("participants", []):
            await ctx.send(embed=discord.Embed(title="❌ Not in Draft", color=COLOR_ERROR))
            return

        autopick_list = draft.get("autopick_users", [])
        if user_id in autopick_list:
            autopick_list.remove(user_id)
            status = "❌ disabled"
        else:
            autopick_list.append(user_id)
            status = "✅ enabled"

        draft["autopick_users"] = autopick_list
        await self.config.guild(ctx.guild).active_draft.set(draft)
        await ctx.send(
            embed=discord.Embed(
                title=f"🤖 Autopick {status}",
                description=f"Autopick is now **{status.split()[-1]}** for {ctx.author.mention}.",
                color=COLOR_SUCCESS,
            )
        )

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: nominate (auction)
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="nominate", aliases=["nom"])
    async def draft_nominate(self, ctx: commands.Context, *, player_name: str):
        """Nominate a player for auction. Only works in Auction draft mode.

        **Example:**
        - `[p]nbadraft nominate LeBron James`
        """
        draft = await self.config.guild(ctx.guild).active_draft()
        if not self._is_active(draft):
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        if draft["mode"] != "auction":
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Not Auction Mode",
                    description="Nominations are only for Auction draft mode.",
                    color=COLOR_ERROR,
                )
            )
            return

        user_id = str(ctx.author.id)
        current_nominator = draft["draft_order"][draft["current_pick_index"]]
        if user_id != current_nominator:
            m = ctx.guild.get_member(int(current_nominator))
            name = m.display_name if m else current_nominator
            await ctx.send(
                embed=discord.Embed(
                    title="⏳ Not Your Nomination Turn",
                    description=f"It's **{name}'s** turn to nominate.",
                    color=COLOR_ERROR,
                )
            )
            return

        # Find player
        results = search_players(player_name, limit=1)
        if not results:
            await ctx.send(
                embed=discord.Embed(title=f"❌ Player not found: **{player_name}**", color=COLOR_ERROR)
            )
            return

        p = results[0]
        all_drafted = []
        for r in draft["teams"].values():
            all_drafted.extend(r)
        if p["name"].lower() in [d.lower() for d in all_drafted]:
            await ctx.send(
                embed=discord.Embed(title=f"❌ {p['name']} is already drafted!", color=COLOR_ERROR)
            )
            return

        draft["current_nomination"] = p["name"]
        draft["current_bid"] = 1
        draft["current_bidder"] = user_id
        draft["bid_passers"] = []
        await self.config.guild(ctx.guild).active_draft.set(draft)
        await self._show_auction_embed(ctx, draft, p["name"])

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: bid
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="bid", aliases=["b"])
    async def draft_bid(self, ctx: commands.Context, amount: int):
        """Place a bid in an Auction draft.

        **Example:**
        - `[p]nbadraft bid 45` — Bid $45 on the current player
        """
        draft = await self.config.guild(ctx.guild).active_draft()
        if not self._is_active(draft):
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        if draft["mode"] != "auction":
            await ctx.send(embed=discord.Embed(title="❌ Not Auction Mode", color=COLOR_ERROR))
            return

        player_name = draft.get("current_nomination")
        if not player_name:
            await ctx.send(embed=discord.Embed(title="❌ No active nomination.", color=COLOR_ERROR))
            return

        await self._process_bid(ctx, player_name, amount)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: pass (auction)
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="pass")
    async def draft_pass(self, ctx: commands.Context):
        """Pass on the current auction nomination."""
        draft = await self.config.guild(ctx.guild).active_draft()
        if not self._is_active(draft):
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        player_name = draft.get("current_nomination")
        if not player_name:
            await ctx.send(embed=discord.Embed(title="❌ No active nomination.", color=COLOR_ERROR))
            return

        await self._process_bid_pass(ctx, player_name)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: modes
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="modes", aliases=["draftmodes"])
    async def draft_modes(self, ctx: commands.Context):
        """Show all available draft modes with descriptions."""
        embed = discord.Embed(
            title="🏀 NBAdex Draft Modes",
            description="Choose a mode when creating your draft with `[p]nbadraft create <mode>`",
            color=COLOR_DRAFT,
        )
        for mode_key, info in DRAFT_MODES.items():
            embed.add_field(
                name=f"{info['emoji']} {info['name']} (`{mode_key}`)",
                value=info["desc"],
                inline=False,
            )
        embed.set_footer(text="Example: [p]nbadraft create auction 10 6")
        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: history
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="history", aliases=["past"])
    async def draft_history(self, ctx: commands.Context):
        """Show recent draft history for this server."""
        history = await self.config.guild(ctx.guild).draft_history()
        if not history:
            await ctx.send(
                embed=discord.Embed(
                    title="📜 Draft History",
                    description="No drafts have been completed yet.",
                    color=COLOR_INFO,
                )
            )
            return

        embed = discord.Embed(title="📜 Draft History", color=COLOR_INFO)
        for i, entry in enumerate(reversed(history[-10:])):
            champ = entry.get("champion", "Unknown")
            mvp = entry.get("mvp", "N/A")
            mode = DRAFT_MODES.get(entry.get("mode", "snake"), {}).get("name", entry.get("mode", ""))
            date = entry.get("date", "")[:10]
            teams = entry.get("participants", "?")
            embed.add_field(
                name=f"#{len(history) - i} — {date}",
                value=f"🏆 **{champ}** | 🌟 MVP: {mvp} | {mode} | {teams} teams",
                inline=False,
            )
        await ctx.send(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: cancel
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="cancel", aliases=["abort"])
    async def draft_cancel(self, ctx: commands.Context):
        """Cancel the current draft. Host or admin only."""
        draft = await self.config.guild(ctx.guild).active_draft()
        if not draft:
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        is_host = str(ctx.author.id) == draft.get("host_id")
        is_admin = ctx.author.guild_permissions.manage_guild

        if not (is_host or is_admin):
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Permission Denied",
                    description="Only the draft host or a server admin can cancel the draft.",
                    color=COLOR_ERROR,
                )
            )
            return

        view = ConfirmView()
        msg = await ctx.send(
            embed=discord.Embed(
                title="⚠️ Confirm Cancellation",
                description="Are you sure you want to **cancel** the current draft? This cannot be undone.",
                color=discord.Color.orange(),
            ),
            view=view,
        )
        await view.wait()

        if view.confirmed:
            self._cancel_timers(ctx.guild.id)
            await self.config.guild(ctx.guild).active_draft.set(None)
            await msg.edit(
                embed=discord.Embed(
                    title="🗑️ Draft Cancelled",
                    description="The draft has been cancelled.",
                    color=COLOR_ERROR,
                ),
                view=None,
            )
        else:
            await msg.edit(
                embed=discord.Embed(title="✅ Cancellation Aborted", description="The draft continues!", color=COLOR_SUCCESS),
                view=None,
            )

    # ──────────────────────────────────────────────────────────────────────────
    # SUBCOMMAND: pickui  (show pick dropdown manually)
    # ──────────────────────────────────────────────────────────────────────────

    @nbadraft.command(name="pickui", aliases=["dropdown", "ui"])
    async def draft_pickui(self, ctx: commands.Context, position: str = "ALL"):
        """Show the interactive player picker dropdown for your current pick.

        Optionally filter by position: `PG`, `SG`, `SF`, `PF`, `C`, or `ALL`
        """
        draft = await self.config.guild(ctx.guild).active_draft()
        if not self._is_active(draft):
            await ctx.send(embed=discord.Embed(title="❌ No Active Draft", color=COLOR_ERROR))
            return

        if draft["mode"] == "auction":
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Use nomination in Auction Mode",
                    description=f"Use `{ctx.clean_prefix}nbadraft nominate <player>` instead.",
                    color=COLOR_ERROR,
                )
            )
            return

        user_id = str(ctx.author.id)
        current = draft["draft_order"][draft["current_pick_index"]]
        if user_id != current:
            m = ctx.guild.get_member(int(current))
            name = m.display_name if m else current
            await ctx.send(
                embed=discord.Embed(title=f"⏳ It's {name}'s turn, not yours.", color=COLOR_ERROR)
            )
            return

        all_drafted = []
        for r in draft["teams"].values():
            all_drafted.extend(r)

        pos = position.upper()
        available = get_top_available(all_drafted, limit=300)
        if pos != "ALL":
            available = [p for p in available if pos in p["positions"]]

        view = PickPlayerView(self, available, page=0, channel_id=ctx.channel.id)
        embed = discord.Embed(
            title=f"🎯 Your Pick — Select a Player",
            description=(
                f"**Round {draft['current_round']}/{draft['rounds']}** | "
                f"**Pick #{len(draft['picks_log']) + 1}**\n"
                f"Use the dropdown below or type `{ctx.clean_prefix}nbadraft pick <name>`"
            ),
            color=COLOR_DRAFT,
        )
        await ctx.send(embed=embed, view=view)

    # ──────────────────────────────────────────────────────────────────────────
    # INTERNAL HELPERS
    # ──────────────────────────────────────────────────────────────────────────

    def _is_active(self, draft: Optional[dict]) -> bool:
        return draft is not None and draft.get("status") == "active"

    def _cancel_timers(self, guild_id: int):
        t1 = self._pick_timers.pop(guild_id, None)
        if t1:
            t1.cancel()
        t2 = self._auction_timers.pop(guild_id, None)
        if t2:
            t2.cancel()

    async def _refresh_join_embed(self, guild: discord.Guild, draft: dict):
        msg = self._join_messages.get(guild.id)
        if not msg:
            return
        try:
            mode_info = DRAFT_MODES.get(draft["mode"], {})
            participants = draft["participants"]
            host = guild.get_member(int(draft["host_id"]))
            lines = []
            for uid in participants:
                m = guild.get_member(int(uid))
                name = m.display_name if m else uid
                suffix = " *(Host)*" if uid == draft["host_id"] else ""
                lines.append(f"• {name}{suffix}")

            embed = discord.Embed(
                title=f"{mode_info.get('emoji', '🏀')} NBA Draft — {mode_info.get('name', 'Draft')}",
                color=COLOR_DRAFT,
            )
            embed.add_field(
                name="📋 Settings",
                value=(
                    f"**Mode:** {mode_info.get('emoji', '')} {mode_info.get('name', '')}\n"
                    f"**Rounds:** {draft['rounds']}\n"
                    f"**Max Teams:** {draft['num_teams']}"
                ),
                inline=True,
            )
            embed.add_field(
                name=f"✅ Participants ({len(participants)}/{draft['num_teams']})",
                value="\n".join(lines),
                inline=False,
            )
            await msg.edit(embed=embed)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def _announce_draft_start(self, ctx: commands.Context, draft: dict):
        participants = draft["participants"]
        lines = []
        for i, uid in enumerate(participants):
            m = ctx.guild.get_member(int(uid))
            name = m.display_name if m else uid
            lines.append(f"`#{i+1}` {m.mention if m else name}")

        mode_info = DRAFT_MODES.get(draft["mode"], {})
        embed = discord.Embed(
            title=f"🚀 Draft Started — {mode_info['name']}!",
            description="\n".join(lines),
            color=COLOR_SUCCESS,
        )
        embed.add_field(
            name="📋 Format",
            value=(
                f"**Mode:** {mode_info['emoji']} {mode_info['name']}\n"
                f"**Rounds:** {draft['rounds']}\n"
                f"**Teams:** {len(participants)}\n"
                f"**Pick Timeout:** {PICK_TIMEOUT}s"
            ),
            inline=False,
        )
        await ctx.send(embed=embed)

    async def _prompt_next_pick(self, ctx_or_channel, draft: dict):
        """Post the pick prompt for the current drafter."""
        idx = draft["current_pick_index"]
        if idx >= len(draft["draft_order"]):
            await self._end_draft(ctx_or_channel, draft)
            return

        current_uid = draft["draft_order"][idx]
        guild = ctx_or_channel.guild if hasattr(ctx_or_channel, "guild") else ctx_or_channel

        member = guild.get_member(int(current_uid))
        display = member.display_name if member else current_uid
        pick_num = len(draft["picks_log"]) + 1
        current_round = draft["current_round"]

        # Check autopick
        if current_uid in draft.get("autopick_users", []):
            all_drafted = [p for r in draft["teams"].values() for p in r]
            available = get_top_available(all_drafted, limit=1)
            if available:
                channel = ctx_or_channel.channel if hasattr(ctx_or_channel, "channel") else ctx_or_channel
                fake_interaction = type("FakeCtx", (), {
                    "guild": guild, "user": member, "guild_id": guild.id,
                })()
                await self._make_pick(channel, guild, draft, current_uid, available[0]["name"], auto=True)
                return

        embed = discord.Embed(
            title=f"🎯 Pick #{pick_num} — Round {current_round}/{draft['rounds']}",
            description=(
                f"**{member.mention if member else display}** is on the clock!\n"
                f"⏱️ You have **{PICK_TIMEOUT} seconds** to pick.\n\n"
                f"• Use `pick <player name>` to draft\n"
                f"• Use `pickui` for the dropdown menu\n"
                f"• Use `autopick` to auto-pick"
            ),
            color=COLOR_DRAFT,
        )

        channel = ctx_or_channel.channel if hasattr(ctx_or_channel, "channel") else ctx_or_channel
        msg = await channel.send(embed=embed)
        self._pick_messages[guild.id] = msg

        # Start timer
        self._cancel_timers(guild.id)
        self._pick_timers[guild.id] = asyncio.get_event_loop().create_task(
            self._pick_timeout_task(channel, guild, draft, current_uid)
        )

    async def _pick_timeout_task(self, channel, guild, draft, user_id: str):
        """Auto-pick best available player after timeout."""
        await asyncio.sleep(PICK_TIMEOUT)
        # Re-read draft in case it changed
        draft = await self.config.guild(guild).active_draft()
        if not draft or draft.get("status") != "active":
            return
        idx = draft["current_pick_index"]
        if idx >= len(draft["draft_order"]):
            return
        cur = draft["draft_order"][idx]
        if cur != user_id:
            return  # Pick was already made

        all_drafted = [p for r in draft["teams"].values() for p in r]
        available = get_top_available(all_drafted, limit=1)
        if not available:
            return

        await self._make_pick(channel, guild, draft, user_id, available[0]["name"], auto=True, timed_out=True)

    async def _process_pick(self, ctx_or_interaction, player_name: str, from_view: bool = False, auto: bool = False):
        """Handle a pick command from text command or view interaction."""
        if isinstance(ctx_or_interaction, discord.Interaction):
            guild = ctx_or_interaction.guild
            user = ctx_or_interaction.user
            channel = ctx_or_interaction.channel
        else:
            guild = ctx_or_interaction.guild
            user = ctx_or_interaction.author
            channel = ctx_or_interaction.channel

        draft = await self.config.guild(guild).active_draft()
        if not draft or draft.get("status") != "active":
            if isinstance(ctx_or_interaction, discord.Interaction):
                try:
                    await ctx_or_interaction.followup.send("No active draft.", ephemeral=True)
                except Exception:
                    pass
            return

        user_id = str(user.id)
        idx = draft["current_pick_index"]
        if idx >= len(draft["draft_order"]):
            return

        current_uid = draft["draft_order"][idx]
        if user_id != current_uid:
            if not from_view:
                m = guild.get_member(int(current_uid))
                name = m.display_name if m else current_uid
                await channel.send(
                    embed=discord.Embed(title=f"⏳ Not your turn! It's **{name}'s** pick.", color=COLOR_ERROR)
                )
            return

        # Find player
        results = search_players(player_name, limit=3)
        if not results:
            msg = f"❌ Player not found: **{player_name}**. Try `{draft.get('prefix', '[p]')}nbadraft search <name>`."
            await channel.send(embed=discord.Embed(description=msg, color=COLOR_ERROR))
            return

        p = results[0]

        # Check already drafted
        all_drafted = [pp for r in draft["teams"].values() for pp in r]
        if p["name"].lower() in [d.lower() for d in all_drafted]:
            await channel.send(
                embed=discord.Embed(
                    title=f"❌ {p['name']} is already drafted!",
                    description="Use `pickui` to see available players.",
                    color=COLOR_ERROR,
                )
            )
            return

        self._cancel_timers(guild.id)
        await self._make_pick(channel, guild, draft, user_id, p["name"])

    async def _make_pick(self, channel, guild, draft: dict, user_id: str, player_name: str, auto: bool = False, timed_out: bool = False):
        """Commit the pick and advance draft state."""
        draft["teams"][user_id].append(player_name)
        pick_num = len(draft["picks_log"]) + 1
        draft["picks_log"].append({
            "pick_num": pick_num,
            "round": draft["current_round"],
            "user_id": user_id,
            "player": player_name,
        })
        draft["current_pick_index"] += 1

        # Update round counter
        picks_per_round = len(draft["participants"])
        if pick_num % picks_per_round == 0:
            draft["current_round"] += 1

        member = guild.get_member(int(user_id))
        display = member.display_name if member else user_id
        p = get_player_by_name(player_name)
        tier_e = TIER_EMOJI.get(p.get("tier", 5), "🏀") if p else "🏀"

        label = "⏰ AUTO-PICKED" if timed_out else ("🤖 Auto-pick" if auto else f"✅ Pick #{pick_num}")
        embed = discord.Embed(
            title=f"{label} — {tier_e} {player_name}",
            description=f"**{display}** selects **{player_name}**",
            color=COLOR_SUCCESS,
        )
        if p:
            embed.add_field(
                name="📊 Stats",
                value=(
                    f"**OVR:** {p['ovr']} | **Pos:** {'/'.join(p['positions'])} | "
                    f"**Era:** {p.get('era', 'N/A')}"
                ),
                inline=False,
            )
        embed.set_footer(text=f"Round {draft['current_round'] - 1}/{draft['rounds']} • Pick {pick_num}")
        await channel.send(embed=embed)

        # Check if draft is complete
        total_picks = draft["rounds"] * len(draft["participants"])
        if len(draft["picks_log"]) >= total_picks:
            draft["status"] = "completed"
            await self.config.guild(guild).active_draft.set(draft)
            await self._end_draft(channel, draft, guild)
            return

        await self.config.guild(guild).active_draft.set(draft)

        # Build fake channel context for next prompt
        class FakeCtx:
            def __init__(self, g, ch):
                self.guild = g
                self.channel = ch

        await self._prompt_next_pick(FakeCtx(guild, channel), draft)

    async def _end_draft(self, channel_or_ctx, draft: dict, guild=None):
        """Announce draft completion."""
        if guild is None:
            guild = channel_or_ctx.guild if hasattr(channel_or_ctx, "guild") else None

        embed = discord.Embed(
            title="🏁 Draft Complete!",
            description=(
                "All picks have been made! The draft is over.\n\n"
                f"📊 Use `nbadraft team @user` to see any team's roster.\n"
                f"🏆 Use `nbadraft simulate` to simulate the season and find out who won!"
            ),
            color=discord.Color.gold(),
        )

        if draft.get("teams") and guild:
            team_summary = []
            for uid, roster in draft["teams"].items():
                m = guild.get_member(int(uid))
                name = m.display_name if m else uid
                top = sorted(
                    [get_player_by_name(p) for p in roster if get_player_by_name(p)],
                    key=lambda x: x["ovr"],
                    reverse=True
                )[:2]
                top_names = ", ".join(p["name"] for p in top)
                grade = grade_team(roster)
                team_summary.append(f"**{name}** (Grade: {grade}) — ⭐ {top_names}")
            embed.add_field(
                name="📋 Team Summary",
                value="\n".join(team_summary) or "N/A",
                inline=False,
            )

        ch = channel_or_ctx.channel if hasattr(channel_or_ctx, "channel") else channel_or_ctx
        await ch.send(embed=embed)

    async def _run_random_draft(self, ctx: commands.Context, draft: dict):
        """Randomly distribute all players among teams."""
        participants = draft["participants"]
        rounds = draft["rounds"]
        total_picks = rounds * len(participants)

        # Get top players for random draft
        available = get_top_available([], limit=total_picks + 50)
        random.shuffle(available)

        teams = {uid: [] for uid in participants}
        for i, p in enumerate(available[:total_picks]):
            uid = participants[i % len(participants)]
            teams[uid].append(p["name"])

        draft["teams"] = teams
        draft["status"] = "completed"
        draft["current_round"] = rounds
        await self.config.guild(ctx.guild).active_draft.set(draft)

        embed = discord.Embed(
            title="🎲 Random Draft Complete!",
            description="Players have been randomly assigned to all teams!",
            color=COLOR_SUCCESS,
        )
        for uid, roster in teams.items():
            m = ctx.guild.get_member(int(uid))
            name = m.display_name if m else uid
            top3 = sorted(
                [get_player_by_name(p) for p in roster if get_player_by_name(p)],
                key=lambda x: x["ovr"], reverse=True
            )[:3]
            top_str = " | ".join(f"{p['name']} ({p['ovr']})" for p in top3)
            grade = grade_team(roster)
            embed.add_field(
                name=f"{name} — Grade {grade}",
                value=f"⭐ {top_str}\n*{len(roster)} players total*",
                inline=False,
            )

        embed.set_footer(text="Use [p]nbadraft simulate to find the winner!")
        await ctx.send(embed=embed)

    # ── Auction helpers ──

    async def _start_auction_nomination(self, ctx: commands.Context, draft: dict):
        """Prompt the current nominator to nominate a player."""
        idx = draft["current_pick_index"]
        if idx >= len(draft["draft_order"]):
            await self._end_draft(ctx, draft)
            return

        uid = draft["draft_order"][idx]
        m = ctx.guild.get_member(int(uid))
        display = m.display_name if m else uid

        embed = discord.Embed(
            title=f"💰 Auction — {display}'s Nomination",
            description=(
                f"{m.mention if m else display} nominate a player!\n"
                f"Use `{ctx.clean_prefix}nbadraft nominate <player name>`"
            ),
            color=COLOR_DRAFT,
        )
        budgets = draft.get("budgets", {})
        budget_lines = []
        for u, b in budgets.items():
            member = ctx.guild.get_member(int(u))
            n = member.display_name if member else u
            budget_lines.append(f"• {n}: **${b}**")
        embed.add_field(name="💰 Budgets", value="\n".join(budget_lines) or "N/A", inline=False)
        await ctx.send(embed=embed)

    async def _show_auction_embed(self, ctx_or_channel, draft: dict, player_name: str):
        """Show the auction bidding UI for the nominated player."""
        if hasattr(ctx_or_channel, "send"):
            channel = ctx_or_channel
        else:
            channel = ctx_or_channel

        p = get_player_by_name(player_name)
        tier_e = TIER_EMOJI.get(p.get("tier", 5), "🏀") if p else "🏀"
        bid = draft.get("current_bid", 1)
        bidder_uid = draft.get("current_bidder")
        guild = channel.guild if hasattr(channel, "guild") else None

        bidder_name = "Nobody"
        if bidder_uid and guild:
            m = guild.get_member(int(bidder_uid))
            bidder_name = m.display_name if m else bidder_uid

        embed = discord.Embed(
            title=f"💰 Auction: {tier_e} {player_name}",
            color=COLOR_DRAFT,
        )
        if p:
            embed.add_field(name="Position", value="/".join(p["positions"]), inline=True)
            embed.add_field(name="OVR", value=str(p["ovr"]), inline=True)
            embed.add_field(name="Era", value=p.get("era", "N/A"), inline=True)

        embed.add_field(name="💵 Current Bid", value=f"**${bid}** by **{bidder_name}**", inline=False)
        embed.add_field(
            name="💰 Bid",
            value=(
                f"• Use `nbadraft bid <amount>` to raise the bid\n"
                f"• Use `nbadraft pass` to pass\n"
                f"• Or click the buttons below\n"
                f"• **{AUCTION_TIMEOUT}s** timer resets with each bid"
            ),
            inline=False,
        )

        view = AuctionBidView(self, player_name, bid, bidder_name)

        if hasattr(channel, "channel"):
            ch = channel.channel
        else:
            ch = channel

        msg = await ch.send(embed=embed, view=view)

        # Start/restart auction timer
        self._cancel_timers(ch.guild.id)
        self._auction_timers[ch.guild.id] = asyncio.get_event_loop().create_task(
            self._auction_timeout_task(ch, ch.guild, player_name)
        )

    async def _process_bid(self, ctx_or_interaction, player_name: str, amount: int):
        if isinstance(ctx_or_interaction, discord.Interaction):
            guild = ctx_or_interaction.guild
            user = ctx_or_interaction.user
            channel = ctx_or_interaction.channel
        else:
            guild = ctx_or_interaction.guild
            user = ctx_or_interaction.author
            channel = ctx_or_interaction.channel

        draft = await self.config.guild(guild).active_draft()
        if not draft or draft.get("status") != "active":
            return

        user_id = str(user.id)
        budget = draft.get("budgets", {}).get(user_id, 0)

        if amount <= draft.get("current_bid", 0):
            msg = f"Bid must be higher than the current bid of **${draft['current_bid']}**."
            if isinstance(ctx_or_interaction, discord.Interaction):
                try:
                    await ctx_or_interaction.followup.send(msg, ephemeral=True)
                except Exception:
                    pass
            else:
                await channel.send(embed=discord.Embed(description=msg, color=COLOR_ERROR))
            return

        if amount > budget:
            msg = f"You can't bid ${amount}! Your budget is only **${budget}**."
            if isinstance(ctx_or_interaction, discord.Interaction):
                try:
                    await ctx_or_interaction.followup.send(msg, ephemeral=True)
                except Exception:
                    pass
            else:
                await channel.send(embed=discord.Embed(description=msg, color=COLOR_ERROR))
            return

        draft["current_bid"] = amount
        draft["current_bidder"] = user_id
        draft["bid_passers"] = []  # Reset passers when bid is raised
        await self.config.guild(guild).active_draft.set(draft)

        await channel.send(
            embed=discord.Embed(
                title=f"💰 New Bid: ${amount} by {user.display_name}",
                description=f"Bidding on **{player_name}**. Time resets to {AUCTION_TIMEOUT}s.",
                color=COLOR_SUCCESS,
            )
        )

        # Restart auction timer
        self._cancel_timers(guild.id)
        self._auction_timers[guild.id] = asyncio.get_event_loop().create_task(
            self._auction_timeout_task(channel, guild, player_name)
        )

    async def _process_bid_pass(self, ctx_or_interaction, player_name: str):
        if isinstance(ctx_or_interaction, discord.Interaction):
            guild = ctx_or_interaction.guild
            user = ctx_or_interaction.user
            channel = ctx_or_interaction.channel
        else:
            guild = ctx_or_interaction.guild
            user = ctx_or_interaction.author
            channel = ctx_or_interaction.channel

        draft = await self.config.guild(guild).active_draft()
        if not draft or draft.get("status") != "active":
            return

        user_id = str(user.id)
        passers = draft.get("bid_passers", [])
        if user_id not in passers:
            passers.append(user_id)
        draft["bid_passers"] = passers
        await self.config.guild(guild).active_draft.set(draft)

        # If all participants except current bidder have passed → award
        all_participants = draft["participants"]
        current_bidder = draft.get("current_bidder")
        non_bidders = [p for p in all_participants if p != current_bidder]
        if all(p in passers for p in non_bidders):
            self._cancel_timers(guild.id)
            await self._award_auction_player(channel, guild, draft, player_name)
        else:
            remaining = len([p for p in non_bidders if p not in passers])
            await channel.send(
                embed=discord.Embed(
                    description=f"**{user.display_name}** passed. **{remaining}** still need to pass.",
                    color=COLOR_INFO,
                )
            )

    async def _auction_timeout_task(self, channel, guild, player_name: str):
        """Award player to highest bidder after timeout."""
        await asyncio.sleep(AUCTION_TIMEOUT)
        draft = await self.config.guild(guild).active_draft()
        if not draft or draft.get("status") != "active":
            return
        if draft.get("current_nomination") != player_name:
            return
        await self._award_auction_player(channel, guild, draft, player_name)

    async def _award_auction_player(self, channel, guild, draft: dict, player_name: str):
        """Award the player to the highest bidder and advance."""
        bidder_uid = draft.get("current_bidder")
        bid_amount = draft.get("current_bid", 1)

        if not bidder_uid:
            # No bids — skip player
            await channel.send(
                embed=discord.Embed(
                    title=f"⏭️ {player_name} — No Bids",
                    description="No one bid on this player. Moving to next nomination.",
                    color=COLOR_INFO,
                )
            )
        else:
            m = guild.get_member(int(bidder_uid))
            display = m.display_name if m else bidder_uid
            draft["teams"][bidder_uid].append(player_name)
            draft["budgets"][bidder_uid] = max(0, draft["budgets"].get(bidder_uid, 0) - bid_amount)
            draft["picks_log"].append({
                "pick_num": len(draft["picks_log"]) + 1,
                "round": draft["current_round"],
                "user_id": bidder_uid,
                "player": player_name,
                "bid": bid_amount,
            })

            p = get_player_by_name(player_name)
            tier_e = TIER_EMOJI.get(p.get("tier", 5), "🏀") if p else "🏀"
            await channel.send(
                embed=discord.Embed(
                    title=f"🔨 SOLD! {tier_e} {player_name} → {display} for ${bid_amount}",
                    description=f"**{display}** has **${draft['budgets'][bidder_uid]}** remaining.",
                    color=discord.Color.gold(),
                )
            )

        draft["current_nomination"] = None
        draft["current_bid"] = 0
        draft["current_bidder"] = None
        draft["bid_passers"] = []

        # Advance to next pick slot
        draft["current_pick_index"] += 1
        picks_per_round = len(draft["participants"])
        total_picks_made = len(draft["picks_log"])
        if total_picks_made % picks_per_round == 0:
            draft["current_round"] += 1

        # Check completion: everyone out of budget or all rounds done
        total_needed = draft["rounds"] * len(draft["participants"])
        if total_picks_made >= total_needed or draft["current_pick_index"] >= len(draft["draft_order"]):
            draft["status"] = "completed"
            await self.config.guild(guild).active_draft.set(draft)
            await self._end_draft(channel, draft, guild)
            return

        await self.config.guild(guild).active_draft.set(draft)

        # Fake ctx for next nomination
        class FakeCtx:
            def __init__(self, g, ch):
                self.guild = g
                self.channel = ch

            async def send(self, *args, **kwargs):
                return await ch.send(*args, **kwargs)

        ch = channel.channel if hasattr(channel, "channel") else channel
        fake = FakeCtx(guild, ch)
        await self._start_auction_nomination(fake, draft)

    def _build_team_embed(self, display_name: str, roster: List[str], draft: dict) -> discord.Embed:
        """Build a rich team roster embed."""
        embed = discord.Embed(
            title=f"🏀 {display_name}'s Roster",
            color=COLOR_DRAFT,
        )

        if not roster:
            embed.description = "*No players drafted yet.*"
            return embed

        # Group by position
        by_pos: Dict[str, List] = {"PG": [], "SG": [], "SF": [], "PF": [], "C": [], "?": []}
        for pname in roster:
            p = get_player_by_name(pname)
            if p:
                primary = p["positions"][0]
                if primary in by_pos:
                    by_pos[primary].append(p)
                else:
                    by_pos["?"].append(p)
            else:
                by_pos["?"].append({"name": pname, "ovr": 0, "positions": ["?"], "tier": 5})

        pos_labels = {"PG": "🔵 PG", "SG": "🟢 SG", "SF": "🟡 SF", "PF": "🟠 PF", "C": "🔴 C", "?": "⚪ Other"}
        for pos, players in by_pos.items():
            if not players:
                continue
            lines = []
            for p in sorted(players, key=lambda x: x.get("ovr", 0), reverse=True):
                tier_e = TIER_EMOJI.get(p.get("tier", 5), "🏀")
                lines.append(f"{tier_e} **{p['name']}** `OVR {p.get('ovr', '?')}`")
            embed.add_field(name=pos_labels[pos], value="\n".join(lines), inline=True)

        grade = grade_team(roster)
        top_player = max(
            [get_player_by_name(p) for p in roster if get_player_by_name(p)],
            key=lambda x: x["ovr"],
            default=None,
        )
        embed.set_footer(
            text=f"Team Grade: {grade} | {len(roster)} players | "
                 f"{'Top: ' + top_player['name'] if top_player else ''}"
        )
        return embed
