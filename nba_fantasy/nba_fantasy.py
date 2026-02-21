import discord
from redbot.core import commands, Config, app_commands
from redbot.core.utils.chat_formatting import pagify
from espn_api.basketball import League
import datetime
import asyncio

class MatchupSelect(discord.ui.Select):
    def __init__(self, matchups, callback_func):
        options = []
        for i, m in enumerate(matchups[:25]):
            home = getattr(m, 'home_team', None)
            away = getattr(m, 'away_team', None)
            home_name = home.team_name if home else "BYE"
            away_name = away.team_name if away else "BYE"
            options.append(discord.SelectOption(label=f"{away_name} @ {home_name}", value=str(i)))
            
        super().__init__(placeholder="Select a matchup...", min_values=1, max_values=1, options=options)
        self.callback_func = callback_func

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction, int(self.values[0]))


class TeamSelect(discord.ui.Select):
    def __init__(self, teams, callback_func):
        options = [
            discord.SelectOption(label=team.team_name, value=str(team.team_id), description=f"Manager: {getattr(team, 'owner', 'Unknown')}")
            for team in teams[:25]
        ]
        super().__init__(placeholder="Select a team...", min_values=1, max_values=1, options=options)
        self.callback_func = callback_func

    async def callback(self, interaction: discord.Interaction):
        await self.callback_func(interaction, self.values[0])


class LeagueHubView(discord.ui.View):
    def __init__(self, cog, interaction_context, league):
        super().__init__(timeout=600)
        self.cog = cog
        self.interaction_context = interaction_context
        self.league = league

    @discord.ui.button(label="Standings", style=discord.ButtonStyle.primary, emoji="📊")
    async def btn_standings(self, interaction: discord.Interaction, button: discord.ui.Button):
        standings = await asyncio.to_thread(self.league.standings)
        embed = discord.Embed(title=f"Standings - {self.league.settings.name}", color=discord.Color.orange())
        desc = ""
        for i, team in enumerate(standings, 1):
            record = f"{team.wins}-{team.losses}-{team.ties}"
            desc += f"**{i}.** {team.team_name} ({record})\\n"
        embed.description = desc
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Rosters", style=discord.ButtonStyle.secondary, emoji="📋")
    async def btn_rosters(self, interaction: discord.Interaction, button: discord.ui.Button):
        async def team_callback(inter: discord.Interaction, team_id_str: str):
            team = next((t for t in self.league.teams if str(t.team_id) == team_id_str), None)
            if not team:
                await inter.response.send_message("Team not found.", ephemeral=True)
                return
                
            embed = discord.Embed(title=f"Roster - {team.team_name}", color=discord.Color.green())
            roster_text = ""
            for player in team.roster:
                status = getattr(player, 'injuryStatus', 'ACTIVE')
                position = getattr(player, 'position', 'N/A')
                pro_team = getattr(player, 'proTeam', 'N/A')
                roster_text += f"**{player.name}** ({pro_team} - {position}) - {status}\\n"
            
            if len(roster_text) > 4000:
                roster_text = roster_text[:4000] + "...(truncated)"
            embed.description = roster_text
            
            new_view = LeagueHubView(self.cog, self.interaction_context, self.league)
            await inter.response.edit_message(embed=embed, view=new_view)

        view = discord.ui.View(timeout=60)
        view.add_item(TeamSelect(self.league.teams, team_callback))
        await interaction.response.edit_message(content="Select a team to view their roster:", embed=None, view=view)

    @discord.ui.button(label="Scoreboard", style=discord.ButtonStyle.danger, emoji="🏀")
    async def btn_scoreboard(self, interaction: discord.Interaction, button: discord.ui.Button):
        matchups = await asyncio.to_thread(self.league.scoreboard)
        if not matchups:
            await interaction.response.send_message("No current matchups.", ephemeral=True)
            return

        async def matchup_callback(inter: discord.Interaction, matchup_idx: int):
            m = matchups[matchup_idx]
            home = getattr(m, 'home_team', None)
            away = getattr(m, 'away_team', None)
            home_name = home.team_name if home else "BYE"
            away_name = away.team_name if away else "BYE"
            home_score = getattr(m, 'home_score', getattr(m, 'home_team_cats', 0))
            away_score = getattr(m, 'away_score', getattr(m, 'away_team_cats', 0))
            
            embed = discord.Embed(title=f"Matchup: {away_name} @ {home_name}", color=discord.Color.red())
            embed.add_field(name=away_name, value=f"Score: {away_score}", inline=True)
            embed.add_field(name=home_name, value=f"Score: {home_score}", inline=True)
            
            new_view = LeagueHubView(self.cog, self.interaction_context, self.league)
            await inter.response.edit_message(embed=embed, view=new_view)

        view = discord.ui.View(timeout=60)
        view.add_item(MatchupSelect(matchups, matchup_callback))
        await interaction.response.edit_message(content="Select a matchup to view details:", embed=None, view=view)

    @discord.ui.button(label="Free Agents", style=discord.ButtonStyle.success, emoji="💸")
    async def btn_fa(self, interaction: discord.Interaction, button: discord.ui.Button):
        def get_fa():
            return self.league.free_agents(size=15)
        fa = await asyncio.to_thread(get_fa)
        embed = discord.Embed(title="Top 15 Free Agents", color=discord.Color.purple())
        fa_text = ""
        for p in fa:
            position = getattr(p, 'position', 'N/A')
            pro_team = getattr(p, 'proTeam', 'N/A')
            fa_text += f"**{p.name}** ({pro_team} - {position})\\n"
        embed.description = fa_text
        await interaction.response.edit_message(embed=embed, view=self)


class NBAFantasy(commands.Cog):
    """ESPN NBA Fantasy Cog - Full Slash Command Support"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=837492837492, force_registration=True)
        default_guild = {
            "league_id": None,
            "year": datetime.datetime.now().year,
            "espn_s2": None,
            "swid": None,
            "draft_active": False,
            "draft_channel": None,
            "draft_picks": []
        }
        self.config.register_guild(**default_guild)

    async def get_league(self, guild):
        settings = await self.config.guild(guild).all()
        if not settings["league_id"]:
            return None
        
        try:
            def fetch_league():
                return League(
                    league_id=settings["league_id"],
                    year=settings["year"],
                    espn_s2=settings["espn_s2"],
                    swid=settings["swid"]
                )
            league = await asyncio.to_thread(fetch_league)
            return league
        except Exception:
            return None

    # --- SLASH COMMANDS ---

    nba = app_commands.Group(name="nba", description="ESPN NBA Fantasy Commands")
    
    @nba.command(name="setleague", description="Configure your ESPN NBA Fantasy league")
    @app_commands.describe(
        league_id="The ID of your ESPN league",
        year="The year of the season (e.g., 2024)",
        espn_s2="The espn_s2 cookie (required for private leagues)",
        swid="The SWID cookie (required for private leagues)"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setleague(self, interaction: discord.Interaction, league_id: int, year: int = None, espn_s2: str = None, swid: str = None):
        if year is None:
            year = datetime.datetime.now().year
            
        await self.config.guild(interaction.guild).league_id.set(league_id)
        await self.config.guild(interaction.guild).year.set(year)
        if espn_s2:
            await self.config.guild(interaction.guild).espn_s2.set(espn_s2)
        if swid:
            await self.config.guild(interaction.guild).swid.set(swid)
            
        await interaction.response.send_message(f"✅ League configured! ID: `{league_id}`, Year: `{year}`.", ephemeral=True)

    @nba.command(name="hub", description="Open the interactive ESPN Fantasy League Hub")
    async def hub(self, interaction: discord.Interaction):
        await interaction.response.defer()
        league = await self.get_league(interaction.guild)
        if not league:
            await interaction.followup.send("League is not configured or ESPN API failed to connect. Admins must use `/nba setleague`.", ephemeral=True)
            return
            
        embed = discord.Embed(title=f"🏀 Welcome to {league.settings.name} Hub", description="Use the buttons below to navigate your fantasy league, just like the app.", color=discord.Color.blue())
        view = LeagueHubView(self, interaction, league)
        await interaction.followup.send(embed=embed, view=view)

    @nba.command(name="player", description="Search for a player to see their fantasy status")
    @app_commands.describe(player_name="The name of the NBA player")
    async def player_search(self, interaction: discord.Interaction, player_name: str):
        await interaction.response.defer()
        league = await self.get_league(interaction.guild)
        if not league:
            await interaction.followup.send("League is not configured.", ephemeral=True)
            return
            
        def search():
            found = []
            for team in league.teams:
                for p in team.roster:
                    if player_name.lower() in p.name.lower():
                        found.append((p, team.team_name))
            if len(found) < 5:
                try:
                    fa = league.free_agents(size=100)
                    for p in fa:
                        if player_name.lower() in p.name.lower():
                            found.append((p, "Free Agent"))
                except Exception:
                    pass
            return found
            
        found_players = await asyncio.to_thread(search)
                
        if not found_players:
            await interaction.followup.send(f"Could not find player `{player_name}` in the league.")
            return
            
        embed = discord.Embed(title=f"Player Search: {player_name}", color=discord.Color.light_grey())
        
        for p, location in found_players[:10]:
            status = getattr(p, 'injuryStatus', 'ACTIVE')
            position = getattr(p, 'position', 'N/A')
            pro_team = getattr(p, 'proTeam', 'N/A')
            embed.add_field(name=p.name, value=f"Location: **{location}**\\nNBA Team: {pro_team}\\nPosition: {position}\\nStatus: {status}", inline=False)
            
        await interaction.followup.send(embed=embed)

    @nba.command(name="transactions", description="View recent league transactions (Adds, Drops, Trades)")
    async def transactions(self, interaction: discord.Interaction):
        await interaction.response.defer()
        league = await self.get_league(interaction.guild)
        if not league:
            await interaction.followup.send("League is not configured.", ephemeral=True)
            return

        def get_activity():
            return league.recent_activity(size=10)
            
        try:
            activity = await asyncio.to_thread(get_activity)
        except Exception as e:
            await interaction.followup.send(f"Could not fetch transactions: {e}")
            return
            
        if not activity:
            await interaction.followup.send("No recent transactions found.")
            return
            
        embed = discord.Embed(title=f"Recent Transactions - {league.settings.name}", color=discord.Color.dark_theme())
        
        for act in activity:
            # Action string parsing based on typical espn-api activity format
            action_type = getattr(act, 'actions', [])
            date = datetime.datetime.fromtimestamp(act.date / 1000.0).strftime('%Y-%m-%d %H:%M') if hasattr(act, 'date') else "Unknown"
            
            desc = ""
            for a in action_type:
                team = a[0].team_name if hasattr(a[0], 'team_name') else "Unknown Team"
                action_str = a[1]
                player = a[2].name if hasattr(a[2], 'name') else "Unknown Player"
                desc += f"**{team}** {action_str} **{player}**\\n"
                
            if desc:
                embed.add_field(name=date, value=desc, inline=False)
                
        await interaction.followup.send(embed=embed)

    # --- DRAFT SYSTEM ---
    draft = app_commands.Group(name="draft", description="In-Discord Live Draft System", parent=nba)

    @draft.command(name="start", description="Start a live text-based draft in this channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def draft_start(self, interaction: discord.Interaction):
        await self.config.guild(interaction.guild).draft_active.set(True)
        await self.config.guild(interaction.guild).draft_channel.set(interaction.channel_id)
        await self.config.guild(interaction.guild).draft_picks.set([])
        
        embed = discord.Embed(
            title="🟢 Live Draft Started!", 
            description="The draft has officially begun in this channel!\\n\\nUse `/nba draft pick player_name:<name>` to make your selection.\\nView the board with `/nba draft board`.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @draft.command(name="stop", description="Stop the live draft")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def draft_stop(self, interaction: discord.Interaction):
        await self.config.guild(interaction.guild).draft_active.set(False)
        await interaction.response.send_message("🔴 Live Draft has been stopped.", ephemeral=False)

    @draft.command(name="pick", description="Select a player for your team in the draft")
    @app_commands.describe(player_name="The name of the NBA player you are drafting")
    async def draft_pick(self, interaction: discord.Interaction, player_name: str):
        settings = await self.config.guild(interaction.guild).all()
        if not settings["draft_active"] or settings["draft_channel"] != interaction.channel_id:
            await interaction.response.send_message("The draft is not currently active in this channel.", ephemeral=True)
            return

        # Record the pick
        picks = settings["draft_picks"]
        pick_number = len(picks) + 1
        
        picks.append({
            "pick_number": pick_number,
            "player": player_name,
            "user_id": interaction.user.id,
            "user_name": interaction.user.display_name
        })
        await self.config.guild(interaction.guild).draft_picks.set(picks)
            
        embed = discord.Embed(title=f"Draft Pick #{pick_number} is in!", description=f"{interaction.user.mention} selects **{player_name.title()}**!", color=discord.Color.gold())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @draft.command(name="board", description="View the current draft board")
    async def draft_board(self, interaction: discord.Interaction):
        settings = await self.config.guild(interaction.guild).all()
        picks = settings["draft_picks"]
        
        if not picks:
            await interaction.response.send_message("No picks have been made yet.", ephemeral=True)
            return
            
        embed = discord.Embed(title="Draft Board", color=discord.Color.blurple())
        
        board_text = ""
        for p in picks[-20:]: # Show last 20 picks
            board_text += f"**{p['pick_number']}.** {p['user_name']} - **{p['player'].title()}**\\n"
            
        embed.description = board_text
        if len(picks) > 20:
            embed.set_footer(text=f"Showing the latest 20 picks out of {len(picks)} total.")
            
        await interaction.response.send_message(embed=embed)