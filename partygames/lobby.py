import asyncio
import discord
from typing import Optional
from .game_base import BaseGame, LobbyView


async def run_lobby(
    game: BaseGame,
    channel: discord.TextChannel,
    cog,
) -> bool:
    """
    Show the join lobby for 30 seconds, then check if enough players joined.
    Returns True if the game should start, False if it should be cancelled.
    """
    view = LobbyView(game)
    lobby_msg = await channel.send(embed=game.make_lobby_embed(), view=view)
    view.message = lobby_msg

    await asyncio.sleep(30)
    view.stop()
    for item in view.children:
        item.disabled = True
    try:
        await lobby_msg.edit(view=view)
    except discord.HTTPException:
        pass

    min_players = game.GAME_INFO["min_players"]
    if len(game.players) < min_players:
        cancel_embed = discord.Embed(
            title="❌ Not Enough Players",
            description=f"**{len(game.players)}/{min_players}** players joined. "
                        f"Need at least **{min_players}** to start **{game.GAME_INFO['name']}**.\n\n"
                        "Game cancelled.",
            color=discord.Color.red(),
        )
        await channel.send(embed=cancel_embed)
        return False

    return True


async def start_game(
    game: BaseGame,
    channel: discord.TextChannel,
    cog,
) -> None:
    """
    Runs the full game lifecycle: lobby → game → cleanup.
    Handles cancellation and errors gracefully.
    """
    game.channel = channel
    game.cog = cog

    info = game.GAME_INFO
    started = await run_lobby(game, channel, cog)

    if not started:
        # Clean up from active games
        cog.active_games.pop(channel.id, None)
        return

    # Announce game start
    start_embed = discord.Embed(
        title=f"{info['emoji']}  {info['name']} — Starting!",
        description=f"**{len(game.players)} players** locked in:\n"
                    + " • ".join(p.display_name for p in game.players)
                    + "\n\nGet ready…",
        color=discord.Color.green(),
    )
    await channel.send(embed=start_embed)
    await asyncio.sleep(3)

    game.running = True
    try:
        await game.run()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        try:
            await channel.send(
                embed=discord.Embed(
                    title="⚠️ Game Error",
                    description=f"An unexpected error occurred: `{type(e).__name__}`\nThe game has ended.",
                    color=discord.Color.red(),
                )
            )
        except Exception:
            pass
    finally:
        game.running = False
        cog.active_games.pop(channel.id, None)
