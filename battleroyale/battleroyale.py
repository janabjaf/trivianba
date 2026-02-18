import discord
from redbot.core import commands, Config, checks
import asyncio
import random

class BattleRoyale(commands.Cog):
    """Advanced Server Battle Royale with Buttons and Dark Humor!"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "lobby": [],
            "is_running": False
        }
        self.config.register_guild(**default_guild)
        
        self.death_messages = [
            "{victim} was used as a human shield by {killer}.",
            "{victim} accidentally drank bleach thinking it was a health potion.",
            "{victim} was pushed into a meat grinder by {killer}.",
            "{victim}'s parachute was replaced with a backpack full of bricks by {killer}.",
            "{victim} tried to high-five a moving train.",
            "{victim} was force-fed a live grenade by {killer}.",
            "{victim} choked on their own hubris.",
            "{victim} was sacrificed to the dark gods by {killer}.",
            "{victim} forgot that gravity is a thing.",
            "{victim} was beaten to death with their own severed leg by {killer}."
        ]

    class JoinView(discord.ui.View):
        def __init__(self, cog, guild):
            super().__init__(timeout=60)
            self.cog = cog
            self.guild = guild

        @discord.ui.button(label="Join Match", style=discord.ButtonStyle.danger, emoji="💀")
        async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
            async with self.cog.config.guild(self.guild).lobby() as lobby:
                if interaction.user.id in lobby:
                    await interaction.response.send_message("You're already in the death pit!", ephemeral=True)
                    return
                lobby.append(interaction.user.id)
                await interaction.response.send_message(f"✅ {interaction.user.display_name} has joined the slaughter!", ephemeral=False)

    @commands.group(name="br")
    async def br(self, ctx):
        """Advanced Battle Royale commands."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @br.command(name="start")
    @checks.is_owner()
    async def br_start(self, ctx):
        """Open the lobby for 60 seconds (Owner Only)."""
        is_running = await self.config.guild(ctx.guild).is_running()
        if is_running:
            await ctx.send("A match is already in progress!")
            return

        await self.config.guild(ctx.guild).lobby.set([])
        view = self.JoinView(self, ctx.guild)
        
        embed = discord.Embed(title="☠️ BATTLE ROYALE LOBBY OPEN ☠️", color=discord.Color.dark_red())
        embed.description = "Click the button below to join the slaughter. You have 60 seconds."
        embed.set_footer(text="May the odds be never in your favor.")
        
        lobby_msg = await ctx.send(embed=embed, view=view)
        await asyncio.sleep(60)
        
        # End lobby
        lobby = await self.config.guild(ctx.guild).lobby()
        if len(lobby) < 2:
            await ctx.send("Not enough victims joined. Match cancelled.")
            await lobby_msg.edit(view=None)
            return

        await self.config.guild(ctx.guild).is_running.set(True)
        await lobby_msg.edit(view=None)
        await ctx.send("🩸 **The gates are locked. Let the carnage begin!**")
        
        players = lobby.copy()
        while len(players) > 1:
            await asyncio.sleep(4)
            victim_id = random.choice(players)
            players.remove(victim_id)
            
            killer_id = random.choice(players)
            
            victim = ctx.guild.get_member(victim_id)
            killer = ctx.guild.get_member(killer_id)
            
            victim_name = f"**{victim.display_name}**" if victim else "A nameless soul"
            killer_name = f"**{killer.display_name}**" if killer else "someone"
            
            msg = random.choice(self.death_messages).format(victim=victim_name, killer=killer_name)
            await ctx.send(f"💀 {msg} — {len(players)} survivors remain.")

        winner_id = players[0]
        winner = ctx.guild.get_member(winner_id)
        winner_name = winner.mention if winner else f"User {winner_id}"
        
        win_embed = discord.Embed(title="🏆 SOLE SURVIVOR 🏆", color=discord.Color.gold())
        win_embed.description = f"{winner_name} crawled out of the pile of corpses victorious!"
        win_embed.set_thumbnail(url=winner.avatar.url if winner and winner.avatar else None)
        await ctx.send(embed=win_embed)
        
        await self.config.guild(ctx.guild).is_running.set(False)

    @br.command(name="stop")
    @checks.is_owner()
    async def br_stop(self, ctx):
        """Force stop a match (Owner Only)."""
        await self.config.guild(ctx.guild).is_running.set(False)
        await ctx.send("🛑 The simulation has been terminated.")
