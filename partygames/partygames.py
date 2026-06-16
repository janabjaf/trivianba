import asyncio
import discord
from discord.ext import commands
from redbot.core import commands as red_commands, Config
from redbot.core.bot import Red
from typing import List, Optional

from .games import GAME_REGISTRY, GAME_NAMES
from .game_base import BaseGame
from .lobby import start_game


class PartyGames(red_commands.Cog):
    """🎮 35+ party games for your Discord server!

    Use `/play` to start a game — a lobby opens for 30 seconds, players join,
    and the game starts automatically. Admin commands under `/games`.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.active_games: dict = {}  # channel_id → BaseGame
        self.config = Config.get_conf(
            self,
            identifier=0xBA5EBA1100F,
            force_registration=True,
        )
        self.config.register_guild(
            allowed_roles=[],   # role IDs; empty = everyone can start
        )

    # ── Autocomplete helper ───────────────────────────────────────────────────

    async def game_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice[str]]:
        matches = [
            name for name in GAME_NAMES
            if current.lower() in name.lower()
        ][:25]
        return [
            discord.app_commands.Choice(name=name, value=name)
            for name in matches
        ]

    # ── /play ─────────────────────────────────────────────────────────────────

    @red_commands.hybrid_command(name="play", description="Start a party game!")
    @discord.app_commands.autocomplete(game=game_autocomplete)
    @discord.app_commands.describe(game="Which game do you want to play?")
    async def play(self, ctx: red_commands.Context, *, game: str):
        """Start a party game in this channel.

        Usage: `/play` then pick a game from the autocomplete list.
        A 30-second lobby opens — click **Join Game** to participate!

        Examples:
            `/play Werewolf`
            `/play Trivia Clash`
            `/play Word Bomb`
        """
        # Role check
        allowed = await self.config.guild(ctx.guild).allowed_roles()
        if allowed:
            member_role_ids = {r.id for r in ctx.author.roles}
            if not (member_role_ids & set(allowed)):
                await ctx.send(
                    embed=discord.Embed(
                        title="❌ No Permission",
                        description="You don't have the required role to start party games.\n"
                                    "Ask an admin to run `/games setrole @YourRole`.",
                        color=discord.Color.red(),
                    ),
                    ephemeral=True,
                )
                return

        # One game per channel
        if ctx.channel.id in self.active_games:
            active = self.active_games[ctx.channel.id]
            await ctx.send(
                embed=discord.Embed(
                    title="⚠️ Game Already Running",
                    description=f"**{active.GAME_INFO['name']}** is already active in this channel.\n"
                                "Wait for it to finish or have an admin use `/games end` to stop it.",
                    color=discord.Color.orange(),
                ),
                ephemeral=True,
            )
            return

        # Find game
        game_key = next(
            (k for k in GAME_REGISTRY if k.lower().strip() == game.lower().strip()
             or k.lower().endswith(game.lower().strip())),
            None,
        )
        # Fuzzy fallback
        if not game_key:
            game_key = next(
                (k for k in GAME_REGISTRY if game.lower() in k.lower()),
                None,
            )

        if not game_key:
            names_block = "\n".join(f"• {n}" for n in GAME_NAMES)
            await ctx.send(
                embed=discord.Embed(
                    title="❌ Game Not Found",
                    description=f"No game matching `{game}` was found.\n\n"
                                f"**Available games:**\n{names_block}",
                    color=discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        GameClass = GAME_REGISTRY[game_key]
        game_instance: BaseGame = GameClass()

        # Host joins automatically
        game_instance.players.append(ctx.author)
        self.active_games[ctx.channel.id] = game_instance

        await ctx.send(
            embed=discord.Embed(
                title=f"{game_instance.GAME_INFO['emoji']} Game Lobby Opening…",
                description=f"**{ctx.author.display_name}** is starting **{game_instance.GAME_INFO['name']}**!\n\n"
                            f"*{game_instance.GAME_INFO['description']}*\n\n"
                            "⏳ Loading lobby…",
                color=discord.Color.blurple(),
            )
        )

        task = asyncio.create_task(
            start_game(game_instance, ctx.channel, self)
        )
        task.add_done_callback(
            lambda t: t.exception() if not t.cancelled() and t.done() else None
        )

    # ── /games group ──────────────────────────────────────────────────────────

    @red_commands.hybrid_group(name="games", description="Party games admin commands")
    async def games_group(self, ctx: red_commands.Context):
        """Admin commands for party games.

        Run `/games` to see all subcommands.
        """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    # ── /games end ────────────────────────────────────────────────────────────

    @games_group.command(name="end", description="Force-end the current game in this channel")
    @red_commands.admin_or_permissions(manage_guild=True)
    async def games_end(self, ctx: red_commands.Context):
        """Force-end the running game in this channel."""
        if ctx.channel.id not in self.active_games:
            await ctx.send(
                embed=discord.Embed(
                    title="ℹ️ No Active Game",
                    description="There is no game currently running in this channel.",
                    color=discord.Color.blurple(),
                ),
                ephemeral=True,
            )
            return

        game = self.active_games.pop(ctx.channel.id)
        await game.force_end()
        await ctx.send(
            embed=discord.Embed(
                title="🛑 Game Ended",
                description=f"**{game.GAME_INFO['name']}** has been forcefully ended by {ctx.author.display_name}.",
                color=discord.Color.red(),
            )
        )

    # ── /games setrole ────────────────────────────────────────────────────────

    @games_group.command(name="setrole", description="Add a role that's allowed to start party games")
    @red_commands.admin_or_permissions(manage_guild=True)
    @discord.app_commands.describe(role="The role to allow")
    async def games_setrole(self, ctx: red_commands.Context, role: discord.Role):
        """Add a role that can start party games. Use multiple times to add multiple roles."""
        async with self.config.guild(ctx.guild).allowed_roles() as roles:
            if role.id in roles:
                await ctx.send(
                    embed=discord.Embed(
                        title="ℹ️ Already Added",
                        description=f"**{role.name}** already has permission to start games.",
                        color=discord.Color.blurple(),
                    ),
                    ephemeral=True,
                )
                return
            roles.append(role.id)

        await ctx.send(
            embed=discord.Embed(
                title="✅ Role Added",
                description=f"**{role.name}** can now start party games.",
                color=discord.Color.green(),
            )
        )

    # ── /games removerole ─────────────────────────────────────────────────────

    @games_group.command(name="removerole", description="Remove a role from the allowed list")
    @red_commands.admin_or_permissions(manage_guild=True)
    @discord.app_commands.describe(role="The role to remove")
    async def games_removerole(self, ctx: red_commands.Context, role: discord.Role):
        """Remove a role's permission to start party games."""
        async with self.config.guild(ctx.guild).allowed_roles() as roles:
            if role.id not in roles:
                await ctx.send(
                    embed=discord.Embed(
                        title="ℹ️ Role Not in List",
                        description=f"**{role.name}** was not in the allowed list.",
                        color=discord.Color.blurple(),
                    ),
                    ephemeral=True,
                )
                return
            roles.remove(role.id)

        await ctx.send(
            embed=discord.Embed(
                title="✅ Role Removed",
                description=f"**{role.name}** can no longer start party games.",
                color=discord.Color.orange(),
            )
        )

    # ── /games listroles ──────────────────────────────────────────────────────

    @games_group.command(name="listroles", description="Show roles that can start games")
    @red_commands.admin_or_permissions(manage_guild=True)
    async def games_listroles(self, ctx: red_commands.Context):
        """List all roles allowed to start party games."""
        role_ids = await self.config.guild(ctx.guild).allowed_roles()
        if not role_ids:
            desc = "**Anyone** can start party games (no role restriction).\nUse `/games setrole @Role` to restrict it."
        else:
            resolved = []
            for rid in role_ids:
                role = ctx.guild.get_role(rid)
                resolved.append(f"• {role.name}" if role else f"• (deleted role: {rid})")
            desc = "\n".join(resolved)

        await ctx.send(
            embed=discord.Embed(
                title="🎮 Allowed Roles",
                description=desc,
                color=discord.Color.blurple(),
            )
        )

    # ── /games status ─────────────────────────────────────────────────────────

    @games_group.command(name="status", description="Show all active games in this server")
    async def games_status(self, ctx: red_commands.Context):
        """Show all currently active party games on this server."""
        server_games = {
            ch_id: game for ch_id, game in self.active_games.items()
            if ctx.guild.get_channel(ch_id) is not None
        }

        if not server_games:
            await ctx.send(
                embed=discord.Embed(
                    title="🎮 No Active Games",
                    description="No party games are currently running on this server.",
                    color=discord.Color.blurple(),
                ),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🎮 Active Party Games",
            color=discord.Color.blurple(),
        )
        for ch_id, game in server_games.items():
            channel = ctx.guild.get_channel(ch_id)
            channel_str = channel.mention if channel else f"(#{ch_id})"
            players = ", ".join(p.display_name for p in game.players) or "None"
            embed.add_field(
                name=f"{game.GAME_INFO['emoji']} {game.GAME_INFO['name']}",
                value=f"Channel: {channel_str}\nPlayers: {players}",
                inline=False,
            )

        await ctx.send(embed=embed)

    # ── /games list ───────────────────────────────────────────────────────────

    @games_group.command(name="list", description="Show all available party games")
    async def games_list(self, ctx: red_commands.Context):
        """Show all 35 party games available to play."""
        # Group by category
        categories: dict = {}
        for name, cls in GAME_REGISTRY.items():
            cat = cls.GAME_INFO.get("category", "Other")
            categories.setdefault(cat, []).append(
                f"{cls.GAME_INFO['emoji']} **{cls.GAME_INFO['name']}** "
                f"({cls.GAME_INFO['min_players']}–{cls.GAME_INFO['max_players']} players) — "
                f"*{cls.GAME_INFO['description'][:80]}…*"
            )

        embed = discord.Embed(
            title="🎮 All Party Games",
            description=f"**{len(GAME_REGISTRY)} games** available! Use `/play <name>` to start.",
            color=discord.Color.blurple(),
        )
        for cat, games_list in categories.items():
            embed.add_field(
                name=f"━━ {cat} ━━",
                value="\n".join(games_list),
                inline=False,
            )
        embed.set_footer(text="Tip: Use /play with autocomplete to find games quickly!")
        await ctx.send(embed=embed)

    # ── /games info ───────────────────────────────────────────────────────────

    @games_group.command(name="info", description="Get details about a specific game")
    @discord.app_commands.autocomplete(game=game_autocomplete)
    @discord.app_commands.describe(game="Which game to describe")
    async def games_info(self, ctx: red_commands.Context, *, game: str):
        """Get detailed info about a specific game."""
        game_key = next(
            (k for k in GAME_REGISTRY if game.lower() in k.lower()), None
        )
        if not game_key:
            await ctx.send(f"❌ No game matching `{game}`. Try `/games list`.", ephemeral=True)
            return

        cls = GAME_REGISTRY[game_key]
        info = cls.GAME_INFO
        embed = discord.Embed(
            title=f"{info['emoji']} {info['name']}",
            description=info["description"],
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Category", value=info.get("category", "General"), inline=True)
        embed.add_field(name="Players", value=f"{info['min_players']}–{info['max_players']}", inline=True)
        embed.add_field(name="Duration", value=info.get("duration", "varies"), inline=True)
        embed.set_footer(text=f"Start with: /play {info['name']}")
        await ctx.send(embed=embed)

    # ── Cog events ────────────────────────────────────────────────────────────

    async def cog_unload(self):
        """Clean up all active games when the cog is unloaded."""
        for game in list(self.active_games.values()):
            try:
                game._stop_event.set()
                game.running = False
            except Exception:
                pass
        self.active_games.clear()
