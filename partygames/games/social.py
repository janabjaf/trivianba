import asyncio
import random
import discord
from typing import Optional, Dict, List
from ..game_base import BaseGame, VotingView
from ..game_data import (
    IDENTITY_THEFT_CHARACTERS, IDENTITY_THEFT_PROMPTS,
    SPYFALL_LOCATIONS, WEREWOLF_ROLE_DESCRIPTIONS, WEREWOLF_ROLE_COMPOSITION,
    MURDER_MYSTERY_VICTIMS, MURDER_MYSTERY_WEAPONS, MURDER_MYSTERY_SETTINGS, MURDER_MYSTERY_CLUES,
    AUCTION_ARTIFACTS,
)


# ── Identity Theft ─────────────────────────────────────────────────────────────

class IdentityTheft(BaseGame):
    GAME_INFO = {
        "name": "Identity Theft",
        "description": "Everyone gets a secret character. One player secretly impersonates someone else's character. Answer questions in-character, then vote to find the impersonator!",
        "min_players": 3,
        "max_players": 20,
        "emoji": "🎭",
        "duration": "5–20 min",
        "category": "Social Deduction",
    }

    async def run(self):
        n = len(self.players)
        characters = random.sample(IDENTITY_THEFT_CHARACTERS, min(n, len(IDENTITY_THEFT_CHARACTERS)))
        while len(characters) < n:
            characters.append(random.choice(IDENTITY_THEFT_CHARACTERS))

        impersonator = random.choice(self.players)
        victim = random.choice([p for p in self.players if p != impersonator])
        victim_char = characters[self.players.index(victim)]

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        for i, player in enumerate(self.players):
            char = characters[i]
            if player == impersonator:
                e = discord.Embed(title="🎭 Your Role: IMPERSONATOR", color=discord.Color.red())
                e.add_field(
                    name="You are secretly impersonating:",
                    value=f"**{victim_char['name']}**\n*{victim_char['occupation']}*\nQuirk: {victim_char['quirk']}",
                    inline=False,
                )
                e.set_footer(text="Act exactly as this character! Don't get caught. If nobody guesses you, you WIN!")
            else:
                e = discord.Embed(title="🎭 Your Secret Identity", color=discord.Color.blurple())
                e.add_field(
                    name="You are:",
                    value=f"**{char['name']}**\n*{char['occupation']}*\nQuirk: {char['quirk']}",
                    inline=False,
                )
                e.set_footer(text="Stay in character throughout the game and find the impersonator!")
            role_embeds[player] = e

        await self.reveal_roles(
            role_embeds,
            title="🎭 Secret Characters Assigned!",
            description="Click the button to privately view your character — only you will see it.",
            button_label="🎭 View My Character",
        )

        intro = discord.Embed(
            title="🎭 Identity Theft — Game Begins!",
            description="Everyone has their **secret character** — click the button above to view it!\n\n"
                        "One player is impersonating someone else's character.\n"
                        "**3 rounds of questions** will follow. Answer as your character!\n"
                        "At the end, vote to find the impersonator.",
            color=discord.Color.gold(),
        )
        intro.add_field(name="Players", value=" • ".join(p.display_name for p in self.players))
        await self.channel.send(embed=intro)

        if await self.wait_or_stop(5):
            return

        prompts = random.sample(IDENTITY_THEFT_PROMPTS, 3)
        for round_num, prompt in enumerate(prompts, 1):
            if self.is_stopped():
                return
            e = discord.Embed(
                title=f"🎭 Round {round_num} / 3",
                description=f"**Question:** {prompt}\n\n"
                            "Answer as your character in this channel! You have **60 seconds**.",
                color=discord.Color.orange(),
            )
            await self.channel.send(embed=e)
            if await self.wait_or_stop(60):
                return

        if self.is_stopped():
            return

        vote_embed = discord.Embed(
            title="🗳️ Vote — Who Is The Impersonator?",
            description="Based on the answers above, who do you think was impersonating someone else?\n"
                        "**30 seconds to vote!**",
            color=discord.Color.purple(),
        )
        options = [p.display_name for p in self.players]
        view = self.track_view(VotingView(self.players, options, timeout=30.0))
        await self.channel.send(embed=vote_embed, view=view)
        await asyncio.wait_for(view.wait(), timeout=32.0)

        if self.is_stopped():
            return

        tally = view.tally()
        most_votes_idx = view.winner_idx()
        most_voted = self.players[most_votes_idx] if most_votes_idx is not None else None

        result = discord.Embed(title="🎭 Identity Theft — Results!", color=discord.Color.green())
        result.add_field(name="The Impersonator was:", value=f"**{impersonator.display_name}**", inline=False)
        result.add_field(
            name="They were impersonating:",
            value=f"**{victim.display_name}** ({victim_char['name']}, *{victim_char['occupation']}*)",
            inline=False,
        )
        if most_voted == impersonator:
            result.add_field(name="✅ Village Wins!", value="You correctly identified the impersonator!", inline=False)
        else:
            result.add_field(
                name="😈 Impersonator Wins!",
                value=f"{impersonator.mention} fooled everyone!",
                inline=False,
            )
        if tally:
            breakdown = "\n".join(
                f"• {self.players[idx].display_name}: {cnt} vote(s)" for idx, cnt in sorted(tally.items(), key=lambda x: -x[1])
            )
            result.add_field(name="Vote Breakdown", value=breakdown, inline=False)
        await self.channel.send(embed=result)


# ── Alibi ─────────────────────────────────────────────────────────────────────

class Alibi(BaseGame):
    GAME_INFO = {
        "name": "Alibi",
        "description": "One player secretly committed the crime. Everyone presents their alibi — the criminal must lie convincingly. Vote to find the culprit!",
        "min_players": 4,
        "max_players": 12,
        "emoji": "🕵️",
        "duration": "10–20 min",
        "category": "Social Deduction",
    }

    async def run(self):
        criminal = random.choice(self.players)
        crime = random.choice([
            "the theft of the Golden Chalice from the museum last night",
            "the poisoning of the town's water supply",
            "the disappearance of Mayor Henderson's briefcase",
            "the midnight arson at the old warehouse",
            "the sabotage of the city's power grid",
        ])
        crime_time = random.choice(["9:00 PM", "10:30 PM", "11:45 PM", "midnight", "1:00 AM"])
        crime_location = random.choice(["downtown", "the east docks", "City Hall", "the old factory", "Westside Park"])

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        for p in self.players:
            if p == criminal:
                e = discord.Embed(title="🔴 You Are The CRIMINAL!", color=discord.Color.red())
                e.description = (
                    f"You committed **{crime}**.\n"
                    f"It happened at **{crime_time}** near **{crime_location}**.\n\n"
                    "You must lie about your whereabouts! Be consistent. If they can't figure you out, **you win**."
                )
            else:
                e = discord.Embed(title="✅ You Are Innocent", color=discord.Color.green())
                e.description = (
                    f"A crime occurred: **{crime}**.\n"
                    f"It happened at **{crime_time}** near **{crime_location}**.\n\n"
                    "Tell the truth about where you were. Work with others to find the criminal!"
                )
            role_embeds[p] = e

        await self.reveal_roles(
            role_embeds,
            title="🕵️ Alibi — Roles Assigned!",
            description="Click the button to secretly see your role — are you the criminal or innocent?",
            button_label="🕵️ View My Role",
        )

        intro = discord.Embed(
            title="🕵️ Alibi — Game Begins!",
            description=f"**A crime has occurred:** {crime}\n"
                        f"**Time:** {crime_time}  •  **Location:** {crime_location}\n\n"
                        "Check your role above, then present your alibi. The criminal is among you.\n"
                        "After hearing everyone, **vote for who you think did it**.",
            color=discord.Color.dark_red(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for i, player in enumerate(self.players):
            if self.is_stopped():
                return
            e = discord.Embed(
                title=f"🎤 Alibi Round — {player.display_name}",
                description=f"**{player.display_name}**, present your alibi for {crime_time}!\n\n"
                            "Type your statement in this channel. You have **45 seconds**.",
                color=discord.Color.blue(),
            )
            await self.channel.send(embed=e, content=player.mention)
            if await self.wait_or_stop(45):
                return

        if self.is_stopped():
            return

        vote_embed = discord.Embed(
            title="🗳️ Vote — Who Did It?",
            description="You've heard everyone's alibi. Vote for who you think is the criminal!\n**30 seconds.**",
            color=discord.Color.purple(),
        )
        options = [p.display_name for p in self.players]
        view = self.track_view(VotingView(self.players, options, timeout=30.0))
        await self.channel.send(embed=vote_embed, view=view)
        await asyncio.wait_for(view.wait(), timeout=32.0)

        if self.is_stopped():
            return

        winner_idx = view.winner_idx()
        most_voted = self.players[winner_idx] if winner_idx is not None else None
        result = discord.Embed(title="🕵️ Alibi — Verdict!", color=discord.Color.gold())
        result.add_field(name="The Criminal Was:", value=f"**{criminal.display_name}**", inline=False)
        if most_voted == criminal:
            result.add_field(name="⚖️ Justice Served!", value="The players correctly identified the criminal!", inline=False)
        else:
            result.add_field(name="😈 Criminal Escaped!", value=f"**{criminal.display_name}** got away with it!", inline=False)
        await self.channel.send(embed=result)


# ── Werewolf ──────────────────────────────────────────────────────────────────

class Werewolf(BaseGame):
    GAME_INFO = {
        "name": "Werewolf",
        "description": "Classic social deduction. Werewolves hunt at night; villagers vote by day. Special roles: Seer, Doctor, Hunter, Witch.",
        "min_players": 4,
        "max_players": 10,
        "emoji": "🐺",
        "duration": "15–40 min",
        "category": "Social Deduction",
    }

    def __init__(self):
        super().__init__()
        self.roles: Dict = {}
        self.alive: List[discord.Member] = []
        self.night_kills: List[discord.Member] = []
        self.protected: Optional[discord.Member] = None
        self.last_protected: Optional[discord.Member] = None
        self.poison_used = False
        self.heal_used = False

    async def run(self):
        n = len(self.players)
        role_list = WEREWOLF_ROLE_COMPOSITION.get(n)
        if not role_list:
            # fallback for odd sizes
            wolves = max(1, n // 3)
            role_list = ["Werewolf"] * wolves + ["Seer", "Doctor"] + ["Villager"] * (n - wolves - 2)
        random.shuffle(role_list)
        self.roles = {p: role_list[i] for i, p in enumerate(self.players)}
        self.alive = list(self.players)

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        wolves_list = [x for x, r in self.roles.items() if r == "Werewolf"]
        for p in self.players:
            role = self.roles[p]
            e = discord.Embed(
                title=f"🐺 Your Role: {role}",
                description=WEREWOLF_ROLE_DESCRIPTIONS[role],
                color=discord.Color.red() if role == "Werewolf" else discord.Color.blurple(),
            )
            if role == "Werewolf" and len(wolves_list) > 1:
                e.add_field(name="Fellow Werewolves:", value=", ".join(x.display_name for x in wolves_list if x != p))
            role_embeds[p] = e

        await self.reveal_roles(
            role_embeds,
            title="🐺 Werewolf Roles Assigned!",
            description="Click the button to secretly see your role — only you will see it.",
            button_label="🐺 View My Role",
        )

        roles_summary = "\n".join(f"• {r}" for r in sorted(set(self.roles.values())))
        intro = discord.Embed(
            title="🐺 Werewolf — Game Starts!",
            description="Everyone has their role — click the button above to view it!\n\n"
                        f"**Roles in play:**\n{roles_summary}\n\n"
                        "The game alternates between **Night** (ephemeral actions in-channel) and **Day** (discussion + vote).\n"
                        "Villagers must eliminate all Werewolves. Werewolves must outnumber Villagers.",
            color=discord.Color.dark_blue(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(8):
            return

        day_num = 1
        while True:
            if self.is_stopped():
                return
            winner = self._check_win()
            if winner:
                break

            # Night Phase
            await self._night_phase(day_num)
            if self.is_stopped():
                return

            winner = self._check_win()
            if winner:
                break

            # Day Phase
            await self._day_phase(day_num)
            if self.is_stopped():
                return

            day_num += 1
            if day_num > 15:  # safety
                break

        winner = self._check_win()
        result = discord.Embed(
            title=f"🐺 Werewolf — Game Over! {'🐺' if winner == 'werewolves' else '🏘️'} {winner.title()} Win!",
            color=discord.Color.red() if winner == "werewolves" else discord.Color.green(),
        )
        role_reveal = "\n".join(f"• {p.display_name}: **{self.roles[p]}**" for p in self.players)
        result.add_field(name="Role Reveal", value=role_reveal, inline=False)
        await self.channel.send(embed=result)

    def _check_win(self) -> Optional[str]:
        wolves = [p for p in self.alive if self.roles[p] == "Werewolf"]
        non_wolves = [p for p in self.alive if self.roles[p] != "Werewolf"]
        if not wolves:
            return "villagers"
        if len(wolves) >= len(non_wolves):
            return "werewolves"
        return None

    async def _night_phase(self, day_num: int):
        wolves = [p for p in self.alive if self.roles[p] == "Werewolf"]
        non_wolves = [p for p in self.alive if self.roles[p] != "Werewolf"]
        seer_list = [p for p in self.alive if self.roles[p] == "Seer"]
        doctor_list = [p for p in self.alive if self.roles[p] == "Doctor"]

        wolf_votes: Dict[discord.Member, discord.Member] = {}
        self.protected = None
        # Build a single view with all night-action buttons
        game_ref = self

        class _NightView(discord.ui.View):
            def __init__(self_v):
                super().__init__(timeout=45.0)

        nv = _NightView()

        # ── Wolf vote button ──────────────────────────────────────────────────
        if wolves and non_wolves:
            wolf_btn = discord.ui.Button(
                label="🐺 Werewolves: Vote for Victim",
                style=discord.ButtonStyle.danger,
                row=0,
            )
            async def wolf_click(interaction: discord.Interaction):
                if interaction.user not in wolves:
                    await interaction.response.send_message("You're not a Werewolf!", ephemeral=True)
                    return
                if interaction.user in wolf_votes:
                    await interaction.response.send_message("You already voted tonight!", ephemeral=True)
                    return
                sv = discord.ui.View(timeout=25.0)
                sel = discord.ui.Select(
                    placeholder="Choose your victim…",
                    options=[discord.SelectOption(label=t.display_name, value=str(i))
                             for i, t in enumerate(non_wolves)],
                )
                async def do_wolf_vote(inter2: discord.Interaction):
                    wolf_votes[inter2.user] = non_wolves[int(sel.values[0])]
                    await inter2.response.send_message(
                        f"🐺 Voted to eliminate **{wolf_votes[inter2.user].display_name}**!", ephemeral=True
                    )
                sel.callback = do_wolf_vote
                sv.add_item(sel)
                await interaction.response.send_message("🐺 Choose your victim:", view=sv, ephemeral=True)
            wolf_btn.callback = wolf_click
            nv.add_item(wolf_btn)

        # ── Seer investigate button ───────────────────────────────────────────
        if seer_list:
            seer = seer_list[0]
            investigate_targets = [p for p in self.alive if p != seer]
            if investigate_targets:
                seer_btn = discord.ui.Button(
                    label="🔮 Seer: Investigate",
                    style=discord.ButtonStyle.primary,
                    row=0,
                )
                seer_used = [False]
                async def seer_click(interaction: discord.Interaction):
                    if interaction.user != seer:
                        await interaction.response.send_message("You're not the Seer!", ephemeral=True)
                        return
                    if seer_used[0]:
                        await interaction.response.send_message("Already investigated tonight!", ephemeral=True)
                        return
                    sv = discord.ui.View(timeout=25.0)
                    sel = discord.ui.Select(
                        placeholder="Who do you investigate?",
                        options=[discord.SelectOption(label=t.display_name, value=str(i))
                                 for i, t in enumerate(investigate_targets)],
                    )
                    async def do_seer(inter2: discord.Interaction):
                        seer_used[0] = True
                        target = investigate_targets[int(sel.values[0])]
                        is_wolf = game_ref.roles[target] == "Werewolf"
                        result_txt = (
                            f"**{target.display_name}** is a 🐺 **WEREWOLF**!"
                            if is_wolf else
                            f"**{target.display_name}** is a 👤 **Villager** (not a Werewolf)."
                        )
                        await inter2.response.send_message(f"🔮 Investigation result: {result_txt}", ephemeral=True)
                    sel.callback = do_seer
                    sv.add_item(sel)
                    await interaction.response.send_message("🔮 Choose who to investigate:", view=sv, ephemeral=True)
                seer_btn.callback = seer_click
                nv.add_item(seer_btn)

        # ── Doctor protect button ─────────────────────────────────────────────
        if doctor_list:
            doctor = doctor_list[0]
            protect_targets = list(self.alive)
            doc_used = [False]
            doc_btn = discord.ui.Button(
                label="⚕️ Doctor: Protect",
                style=discord.ButtonStyle.success,
                row=0,
            )
            async def doctor_click(interaction: discord.Interaction):
                if interaction.user != doctor:
                    await interaction.response.send_message("You're not the Doctor!", ephemeral=True)
                    return
                if doc_used[0]:
                    await interaction.response.send_message("Already protected someone tonight!", ephemeral=True)
                    return
                sv = discord.ui.View(timeout=25.0)
                sel = discord.ui.Select(
                    placeholder="Who do you protect?",
                    options=[discord.SelectOption(label=t.display_name, value=str(i))
                             for i, t in enumerate(protect_targets)],
                )
                async def do_doctor(inter2: discord.Interaction):
                    doc_used[0] = True
                    choice = protect_targets[int(sel.values[0])]
                    if choice != game_ref.last_protected:
                        game_ref.protected = choice
                        game_ref.last_protected = choice
                        await inter2.response.send_message(
                            f"⚕️ Protecting **{choice.display_name}** tonight!", ephemeral=True
                        )
                    else:
                        await inter2.response.send_message(
                            "⚠️ Can't protect the same player twice in a row — no protection tonight.", ephemeral=True
                        )
                sel.callback = do_doctor
                sv.add_item(sel)
                await interaction.response.send_message("⚕️ Choose who to protect:", view=sv, ephemeral=True)
            doc_btn.callback = doctor_click
            nv.add_item(doc_btn)

        night_e = discord.Embed(
            title=f"🌙 Night {day_num} Falls…",
            description="The village sleeps. Active night roles — click your button below!\n"
                        "*(Your action is private — nobody else can see it.)*\n\n"
                        "⏱ **45 seconds** for all night actions.",
            color=discord.Color.dark_blue(),
        )
        self.track_view(nv)
        await self.channel.send(embed=night_e, view=nv)
        await asyncio.sleep(45)
        nv.stop()

        # Tally wolf votes
        wolf_kill: Optional[discord.Member] = None
        if wolf_votes:
            vote_counts: Dict[discord.Member, int] = {}
            for v in wolf_votes.values():
                vote_counts[v] = vote_counts.get(v, 0) + 1
            wolf_kill = max(vote_counts, key=vote_counts.get)

        # Resolve night
        killed = None
        if wolf_kill and wolf_kill != self.protected:
            killed = wolf_kill
            self.alive.remove(killed)

        dawn_e = discord.Embed(title="☀️ Morning Arrives…", color=discord.Color.orange())
        if killed:
            role_of_killed = self.roles[killed]
            dawn_e.description = (
                f"The village wakes to tragic news…\n\n"
                f"💀 **{killed.display_name}** was eliminated in the night.\n"
                f"They were a **{role_of_killed}**."
            )
            # Hunter's last shot via ephemeral button
            if role_of_killed == "Hunter":
                others = list(self.alive)
                if others:
                    await self.channel.send(embed=dawn_e)
                    await self._hunter_shot(killed, others)
                    return
        else:
            dawn_e.description = "The village wakes in relief — **nobody was killed last night!**" + (
                "\n*(The Doctor's protection saved someone…)*"
                if wolf_kill and wolf_kill == self.protected else ""
            )

        await self.channel.send(embed=dawn_e)

    async def _hunter_shot(self, hunter: discord.Member, targets: List[discord.Member]):
        """Post an ephemeral button for the Hunter to fire their last shot."""
        shot_result: List[Optional[discord.Member]] = [None]
        done_event = asyncio.Event()

        class _HunterView(discord.ui.View):
            def __init__(self_v):
                super().__init__(timeout=30.0)
                btn = discord.ui.Button(label="🏹 Fire Final Shot", style=discord.ButtonStyle.danger)
                btn.callback = self_v._on_click
                self_v.add_item(btn)

            async def _on_click(self_v, interaction: discord.Interaction):
                if interaction.user != hunter:
                    await interaction.response.send_message("Only the Hunter can fire!", ephemeral=True)
                    return
                sv = discord.ui.View(timeout=20.0)
                sel = discord.ui.Select(
                    placeholder="Who do you shoot?",
                    options=[discord.SelectOption(label=t.display_name, value=str(i))
                             for i, t in enumerate(targets)],
                )
                async def fire(inter2: discord.Interaction):
                    shot_result[0] = targets[int(sel.values[0])]
                    await inter2.response.send_message(
                        f"🏹 Shot **{shot_result[0].display_name}**!", ephemeral=True
                    )
                    done_event.set()
                    self_v.stop()
                sel.callback = fire
                sv.add_item(sel)
                await interaction.response.send_message("🏹 Choose your target:", view=sv, ephemeral=True)

        hv = self.track_view(_HunterView())
        hunt_embed = discord.Embed(
            title="🏹 Hunter's Last Stand!",
            description=f"**{hunter.display_name}** (Hunter) was eliminated — they get one final shot!\n"
                        "Click below before the 30-second window closes.",
            color=discord.Color.dark_orange(),
        )
        await self.channel.send(embed=hunt_embed, view=hv)
        try:
            await asyncio.wait_for(done_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            pass

        if shot_result[0]:
            self.alive.remove(shot_result[0])
            await self.channel.send(
                f"🏹 **{hunter.display_name}** (Hunter) fired their last shot — **{shot_result[0].display_name}** "
                f"(**{self.roles[shot_result[0]]}**) is eliminated!"
            )

    async def _day_phase(self, day_num: int):
        if self._check_win():
            return

        alive_names = ", ".join(p.display_name for p in self.alive)
        day_e = discord.Embed(
            title=f"☀️ Day {day_num} — Discussion",
            description=f"**Alive ({len(self.alive)}):** {alive_names}\n\n"
                        "Discuss who you think the werewolves are.\n"
                        "**90 seconds of discussion**, then vote!",
            color=discord.Color.yellow(),
        )
        await self.channel.send(embed=day_e)
        if await self.wait_or_stop(90):
            return

        if self.is_stopped():
            return

        vote_e = discord.Embed(
            title="🗳️ Village Vote — Who Do You Suspect?",
            description="Vote to eliminate a player. Majority rules. **30 seconds.**",
            color=discord.Color.orange(),
        )
        options = [p.display_name for p in self.alive]
        view = self.track_view(VotingView(self.alive, options, timeout=30.0))
        await self.channel.send(embed=vote_e, view=view)
        await asyncio.wait_for(view.wait(), timeout=32.0)

        if self.is_stopped():
            return

        winner_idx = view.winner_idx()
        eliminated = self.alive[winner_idx] if winner_idx is not None else None

        if eliminated:
            self.alive.remove(eliminated)
            role_el = self.roles[eliminated]
            elim_e = discord.Embed(
                title="⚖️ The Village Has Spoken",
                description=f"**{eliminated.display_name}** has been eliminated by popular vote.\n"
                            f"They were a **{role_el}**.",
                color=discord.Color.dark_red(),
            )
            await self.channel.send(embed=elim_e)

            if role_el == "Hunter":
                others = [p for p in self.alive]
                if others:
                    await self._hunter_shot(eliminated, others)
        else:
            await self.channel.send("No consensus reached — nobody was eliminated today.")


# ── Spyfall ────────────────────────────────────────────────────────────────────

class Spyfall(BaseGame):
    GAME_INFO = {
        "name": "Spyfall",
        "description": "Everyone knows the secret location — except the spy! Ask each other questions to expose the spy, but don't give away too much. The spy tries to figure out the location.",
        "min_players": 3,
        "max_players": 10,
        "emoji": "🌍",
        "duration": "10–20 min",
        "category": "Social Deduction",
    }

    async def run(self):
        location_data = random.choice(SPYFALL_LOCATIONS)
        location = location_data["name"]
        roles = location_data["roles"] * 5  # repeat to have enough
        spy = random.choice(self.players)

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        for i, p in enumerate(self.players):
            if p == spy:
                e = discord.Embed(title="🕵️ YOU ARE THE SPY!", color=discord.Color.red())
                e.description = (
                    "You don't know the location. Ask questions and listen carefully to figure it out!\n\n"
                    "**Your goal:** Blend in without revealing you don't know the location.\n"
                    "If players vote for you — try to guess the location to win!"
                )
            else:
                role = roles[i % len(location_data["roles"])]
                e = discord.Embed(title=f"🌍 Location: **{location}**", color=discord.Color.blurple())
                e.description = (
                    f"Your role at this location: **{role}**\n\n"
                    "**Your goal:** Ask and answer questions to expose the spy without giving away the location directly."
                )
            role_embeds[p] = e

        await self.reveal_roles(
            role_embeds,
            title="🌍 Spyfall — Roles Assigned!",
            description="Click the button to secretly see your role — are you a local, or the Spy?",
            button_label="🌍 View My Role",
        )

        intro = discord.Embed(
            title="🌍 Spyfall — Game Begins!",
            description="All players have their role — click the button above to view it!\n\n"
                        "Players take turns asking **one question** to any other player.\n"
                        "After 4 minutes, vote for who you think is the spy!\n\n"
                        "**The spy can call the vote early** by typing `/spy` in chat.",
            color=discord.Color.teal(),
        )
        await self.channel.send(embed=intro)

        # 4 minute discussion timer with early-end check
        if await self.wait_or_stop(240):
            return

        if self.is_stopped():
            return

        vote_e = discord.Embed(
            title="🗳️ Spyfall — Vote for the Spy!",
            description="Who do you think is the spy? Vote now! **30 seconds.**",
            color=discord.Color.purple(),
        )
        options = [p.display_name for p in self.players]
        view = self.track_view(VotingView(self.players, options, timeout=30.0))
        await self.channel.send(embed=vote_e, view=view)
        await asyncio.wait_for(view.wait(), timeout=32.0)

        if self.is_stopped():
            return

        winner_idx = view.winner_idx()
        most_voted = self.players[winner_idx] if winner_idx is not None else None

        result = discord.Embed(title="🌍 Spyfall — Results!", color=discord.Color.gold())
        result.add_field(name="The Spy was:", value=f"**{spy.display_name}**", inline=False)
        result.add_field(name="The Location was:", value=f"**{location}**", inline=False)

        if most_voted == spy:
            result.add_field(name="✅ Players Win!", value="You correctly identified the spy!", inline=False)
        else:
            voted_name = most_voted.display_name if most_voted else "Nobody"
            result.add_field(name="😈 Spy Wins!", value=f"You voted for **{voted_name}** — wrong! The spy escapes!", inline=False)
        await self.channel.send(embed=result)


# ── Fake Artist ───────────────────────────────────────────────────────────────

class FakeArtist(BaseGame):
    GAME_INFO = {
        "name": "Fake Artist",
        "description": "Everyone knows the secret word except the Fake Artist. Players take turns giving one-word clues. Vote to find the Fake Artist — who must then guess the word to steal the win!",
        "min_players": 4,
        "max_players": 15,
        "emoji": "🎨",
        "duration": "5–15 min",
        "category": "Social Deduction",
    }

    WORD_CATEGORIES = {
        "Animals": ["elephant", "penguin", "chameleon", "narwhal", "platypus", "axolotl", "tardigrade"],
        "Foods": ["spaghetti", "croissant", "sushi", "dumpling", "avocado", "pretzel", "churro"],
        "Places": ["lighthouse", "volcano", "glacier", "waterfall", "canyon", "cathedral", "monastery"],
        "Objects": ["telescope", "compass", "lantern", "pocket watch", "kaleidoscope", "hourglass"],
        "Concepts": ["nostalgia", "gravity", "democracy", "entropy", "solitude", "resilience"],
    }

    async def run(self):
        category = random.choice(list(self.WORD_CATEGORIES.keys()))
        word = random.choice(self.WORD_CATEGORIES[category])
        fake_artist = random.choice(self.players)

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        for p in self.players:
            if p == fake_artist:
                e = discord.Embed(title="🎨 You Are the FAKE ARTIST!", color=discord.Color.red())
                e.description = (
                    f"The category is: **{category}**\n"
                    "You do **NOT** know the word!\n\n"
                    "Give a clue that sounds convincing without revealing you don't know.\n"
                    "If discovered, guess the word to steal the win!"
                )
            else:
                e = discord.Embed(title="🎨 Secret Word", color=discord.Color.blurple())
                e.description = (
                    f"**Category:** {category}\n"
                    f"**Word:** `{word}`\n\n"
                    "Give one-word clues in the channel to help others while exposing the Fake Artist."
                )
            role_embeds[p] = e

        await self.reveal_roles(
            role_embeds,
            title="🎨 Fake Artist — Roles Assigned!",
            description="Click the button to secretly see your role — do you know the word, or are you the Fake Artist?",
            button_label="🎨 View My Role",
        )

        intro = discord.Embed(
            title="🎨 Fake Artist — Game Begins!",
            description=f"**Category:** {category}\n\n"
                        "Each player gives **one-word clue** in the channel (in order below).\n"
                        "One player is the Fake Artist and doesn't know the word!\n\n"
                        "**Order:**\n" + "\n".join(f"{i+1}. {p.display_name}" for i, p in enumerate(self.players)),
            color=discord.Color.green(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for round_num in range(1, 3):
            for player in self.players:
                if self.is_stopped():
                    return
                e = discord.Embed(
                    title=f"🎨 Round {round_num} — {player.display_name}'s Turn",
                    description=f"**{player.mention}**, type your **one-word clue** now! (30 seconds)",
                    color=discord.Color.orange(),
                )
                await self.channel.send(embed=e)

                def check(m):
                    return m.channel == self.channel and m.author == player and len(m.content.split()) <= 3

                await self.listen_for_answer(check=check, timeout=30.0)

        if self.is_stopped():
            return

        vote_e = discord.Embed(
            title="🗳️ Who Is The Fake Artist?",
            description="Based on the clues, vote for who you think is the Fake Artist! **30 seconds.**",
            color=discord.Color.purple(),
        )
        options = [p.display_name for p in self.players]
        view = self.track_view(VotingView(self.players, options, timeout=30.0))
        await self.channel.send(embed=vote_e, view=view)
        await asyncio.wait_for(view.wait(), timeout=32.0)

        if self.is_stopped():
            return

        winner_idx = view.winner_idx()
        most_voted = self.players[winner_idx] if winner_idx is not None else None

        result = discord.Embed(title="🎨 Fake Artist — Results!", color=discord.Color.gold())
        result.add_field(name="The Secret Word was:", value=f"**{word}** ({category})", inline=False)
        result.add_field(name="The Fake Artist was:", value=f"**{fake_artist.display_name}**", inline=False)

        if most_voted == fake_artist:
            result.add_field(
                name="🎨 Caught! But can they guess the word?",
                value=f"Everyone voted for **{fake_artist.display_name}**! Can they guess the word to steal the win?\n"
                      f"**{fake_artist.mention}** — type your guess now! 15 seconds.",
                inline=False,
            )
            await self.channel.send(embed=result)

            def guess_check(m):
                return m.channel == self.channel and m.author == fake_artist

            guess_msg = await self.listen_for_answer(check=guess_check, timeout=15.0)
            if guess_msg and word.lower() in guess_msg.content.lower():
                await self.channel.send(
                    embed=discord.Embed(
                        title="😱 Fake Artist Steals the Win!",
                        description=f"**{fake_artist.display_name}** correctly guessed `{word}`! The Fake Artist wins!",
                        color=discord.Color.red(),
                    )
                )
            else:
                await self.channel.send(
                    embed=discord.Embed(
                        title="✅ Real Artists Win!",
                        description=f"**{fake_artist.display_name}** failed to guess the word. Real Artists win!",
                        color=discord.Color.green(),
                    )
                )
        else:
            voted_name = most_voted.display_name if most_voted else "Nobody"
            await self.channel.send(
                embed=discord.Embed(
                    title="😈 Fake Artist Wins!",
                    description=f"Village voted for **{voted_name}** — wrong! The Fake Artist **{fake_artist.display_name}** escapes!",
                    color=discord.Color.red(),
                )
            )


# ── Murder Mystery ─────────────────────────────────────────────────────────────

class MurderMystery(BaseGame):
    GAME_INFO = {
        "name": "Murder Mystery",
        "description": "A crime has been committed! Players are suspects. The detective eliminates suspects each round based on revealed clues. Can you catch the murderer?",
        "min_players": 4,
        "max_players": 12,
        "emoji": "🔍",
        "duration": "10–25 min",
        "category": "Social Deduction",
    }

    async def run(self):
        victim = random.choice(MURDER_MYSTERY_VICTIMS)
        weapon = random.choice(MURDER_MYSTERY_WEAPONS)
        setting = random.choice(MURDER_MYSTERY_SETTINGS)
        murderer = random.choice(self.players)
        detective = random.choice([p for p in self.players if p != murderer])
        suspects = [p for p in self.players if p != detective]
        clues = random.sample(MURDER_MYSTERY_CLUES, min(len(suspects), len(MURDER_MYSTERY_CLUES)))

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        for p in self.players:
            if p == murderer:
                e = discord.Embed(title="🔴 You Are The MURDERER!", color=discord.Color.red())
                e.description = (
                    f"You murdered **{victim}** using a **{weapon}** in {setting}.\n\n"
                    "Deny everything. Stay calm. If the detective suspects you, they need evidence."
                )
            elif p == detective:
                e = discord.Embed(title="🕵️ You Are The DETECTIVE!", color=discord.Color.blue())
                e.description = (
                    "Each round, a new clue is revealed. After each clue, you must **eliminate a suspect**.\n"
                    "Catch the murderer before you run out of suspects!"
                )
            else:
                e = discord.Embed(title="👤 You Are A Suspect", color=discord.Color.greyple())
                e.description = (
                    f"You are innocent, but you're under suspicion for the murder of {victim}.\n"
                    "Act naturally. Help the detective if you want!"
                )
            role_embeds[p] = e

        await self.reveal_roles(
            role_embeds,
            title="🔍 Murder Mystery — Roles Assigned!",
            description="Click the button to secretly see your role.",
            button_label="🔍 View My Role",
        )

        intro = discord.Embed(
            title="🔍 Murder Mystery",
            description=f"💀 **{victim}** has been found dead in {setting}!\n"
                        f"The murder weapon: a **{weapon}**.\n\n"
                        f"🕵️ **Detective:** {detective.display_name}\n"
                        f"**Suspects:** {', '.join(s.display_name for s in suspects)}\n\n"
                        "Clues will be revealed each round. The detective must eliminate one suspect per round.",
            color=discord.Color.dark_red(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        remaining_suspects = list(suspects)
        for round_num, clue in enumerate(clues, 1):
            if self.is_stopped():
                return
            if len(remaining_suspects) <= 1:
                break

            clue_e = discord.Embed(
                title=f"🔎 Clue #{round_num}",
                description=f"*{clue}*\n\n"
                            f"**{detective.mention}** — Discuss with the group, then eliminate a suspect!\n"
                            "**90 seconds of discussion**, then the detective votes.",
                color=discord.Color.orange(),
            )
            await self.channel.send(embed=clue_e)
            if await self.wait_or_stop(90):
                return

            if self.is_stopped():
                return

            options = [s.display_name for s in remaining_suspects]
            view = self.track_view(VotingView([detective], options, timeout=30.0))
            await self.channel.send(
                embed=discord.Embed(
                    title="🕵️ Detective — Eliminate a Suspect",
                    description="Choose who to eliminate. **30 seconds.**",
                    color=discord.Color.purple(),
                ),
                view=view,
            )
            await asyncio.wait_for(view.wait(), timeout=32.0)

            if self.is_stopped():
                return

            winner_idx = view.winner_idx()
            if winner_idx is not None:
                eliminated = remaining_suspects[winner_idx]
                remaining_suspects.remove(eliminated)
                is_murderer = eliminated == murderer
                await self.channel.send(
                    embed=discord.Embed(
                        title="💼 Suspect Eliminated",
                        description=f"**{eliminated.display_name}** was cleared from suspicion.\n"
                                    f"They were **{'❌ THE MURDERER — too early!' if is_murderer else '✅ Innocent'}**.",
                        color=discord.Color.red() if is_murderer else discord.Color.green(),
                    )
                )
                if is_murderer:
                    await self.channel.send(
                        embed=discord.Embed(
                            title="😭 Murderer Was Eliminated Early",
                            description=f"**{murderer.display_name}** committed the murder of {victim} with a {weapon}.",
                            color=discord.Color.red(),
                        )
                    )
                    return

        if self.is_stopped():
            return

        if remaining_suspects:
            final_suspect = remaining_suspects[0]
            correct = final_suspect == murderer
            result = discord.Embed(
                title="🔍 Murder Mystery — Final Verdict",
                color=discord.Color.green() if correct else discord.Color.red(),
            )
            result.add_field(name="Final Suspect:", value=f"**{final_suspect.display_name}**", inline=False)
            result.add_field(
                name="The Murderer was:",
                value=f"**{murderer.display_name}** — used a **{weapon}** in {setting}.",
                inline=False,
            )
            result.add_field(
                name="Result:",
                value="✅ **Detective wins!** Justice served!" if correct else "😈 **Murderer escapes!**",
                inline=False,
            )
            await self.channel.send(embed=result)


# ── Auction Heist ─────────────────────────────────────────────────────────────

class AuctionHeist(BaseGame):
    GAME_INFO = {
        "name": "Auction Heist",
        "description": "Thieves bid on stolen artifacts (some are fakes!). Some players are secretly undercover cops. Win by acquiring real artifacts — if you're not arrested!",
        "min_players": 4,
        "max_players": 15,
        "emoji": "🏺",
        "duration": "10–25 min",
        "category": "Social Deduction",
    }

    async def run(self):
        n_cops = max(1, len(self.players) // 4)
        cops = random.sample(self.players, n_cops)
        artifacts = random.sample(AUCTION_ARTIFACTS, min(5, len(AUCTION_ARTIFACTS)))

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        for p in self.players:
            if p in cops:
                e = discord.Embed(title="🚔 You Are an UNDERCOVER COP!", color=discord.Color.blue())
                e.description = (
                    "Pretend to be a thief and bid on items.\n"
                    "At the end, reveal yourself and arrest the top bidder on each REAL artifact.\n"
                    "Don't reveal yourself too early!"
                )
            else:
                e = discord.Embed(title="🥷 You Are a THIEF!", color=discord.Color.dark_red())
                e.description = (
                    "Bid on stolen artifacts — but some are FAKES! Be careful.\n"
                    "Watch out for undercover cops — they could arrest you at the end!\n"
                    "Win by acquiring the most valuable REAL artifacts without getting caught."
                )
            role_embeds[p] = e

        await self.reveal_roles(
            role_embeds,
            title="🏺 Auction Heist — Roles Assigned!",
            description="Click the button to secretly see your role — cop or thief?",
            button_label="🏺 View My Role",
        )

        intro = discord.Embed(
            title="🏺 Auction Heist — Doors Open!",
            description=f"Welcome to the underground auction!\n\n"
                        f"**{len(artifacts)} artifacts** are up for bid.\n"
                        f"**{n_cops} undercover cop(s)** are hiding among the bidders.\n\n"
                        "For each artifact, type a bid (whole number). Highest bid wins the item.\n"
                        "But beware — some artifacts are **FAKES** and some bidders are **COPS**!",
            color=discord.Color.gold(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}
        budgets: Dict[discord.Member, int] = {p: 10_000_000 for p in self.players}
        winners_per_artifact: Dict = {}

        for i, artifact in enumerate(artifacts, 1):
            if self.is_stopped():
                return
            art_e = discord.Embed(
                title=f"🏺 Lot #{i}: {artifact['name']}",
                description=f"*{artifact['description']}*\n\n"
                            "Type your bid (numbers only) in the channel! **30 seconds.**",
                color=discord.Color.gold(),
            )
            await self.channel.send(embed=art_e)

            bids: Dict[discord.Member, int] = {}
            end_time = asyncio.get_event_loop().time() + 30

            while asyncio.get_event_loop().time() < end_time:
                remaining = end_time - asyncio.get_event_loop().time()
                msg = await self.listen_for_answer(
                    check=lambda m: m.channel == self.channel and m.author in self.players
                                   and m.content.strip().replace(",", "").isdigit(),
                    timeout=min(remaining, 5),
                )
                if msg:
                    amount = int(msg.content.strip().replace(",", ""))
                    if amount > 0 and amount <= budgets[msg.author]:
                        bids[msg.author] = amount

            if bids:
                winner = max(bids, key=bids.get)
                winners_per_artifact[artifact["name"]] = (winner, bids[winner], artifact["fake"], artifact.get("value", 0))
                budgets[winner] -= bids[winner]
                result_text = f"**{winner.display_name}** wins with **${bids[winner]:,}**!"
            else:
                result_text = "No bids — item withdrawn."

            await self.channel.send(f"🔨 Lot #{i} **{artifact['name']}**: {result_text}")

        if self.is_stopped():
            return

        # Reveal cops
        reveal = discord.Embed(
            title="🚔 FREEZE! Undercover Cops Reveal!",
            description=f"The following bidders were **undercover cops**: {', '.join(c.display_name for c in cops)}\n\n"
                        "Any thief who won a **real artifact** and was the **top bidder** gets arrested!",
            color=discord.Color.blue(),
        )
        await self.channel.send(embed=reveal)
        await asyncio.sleep(2)

        # Score
        results_lines = []
        for art_name, (winner, bid, is_fake, value) in winners_per_artifact.items():
            if is_fake:
                results_lines.append(f"❌ **{art_name}** — FAKE! {winner.display_name} wasted ${bid:,}")
            elif winner in cops:
                results_lines.append(f"🚔 **{art_name}** — Real artifact, but won by a cop. Returned to authorities.")
            else:
                scores[winner] += value
                results_lines.append(f"✅ **{art_name}** — Real! Worth ${value:,}. {winner.display_name} scores!")

        final = discord.Embed(title="🏺 Auction Heist — Final Scores!", color=discord.Color.gold())
        final.add_field(name="Auction Results", value="\n".join(results_lines) or "No results", inline=False)
        ranking = sorted(scores.items(), key=lambda x: -x[1])
        leaderboard = "\n".join(f"{'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else '▪️'} {p.display_name}: ${score:,}" for i, (p, score) in enumerate(ranking))
        final.add_field(name="Leaderboard", value=leaderboard or "No scores", inline=False)
        await self.channel.send(embed=final)


# ── Kingmaker ─────────────────────────────────────────────────────────────────

class Kingmaker(BaseGame):
    GAME_INFO = {
        "name": "Kingmaker",
        "description": "One player starts as King. Each round, nobles form alliances and vote to change who wears the crown. Political intrigue and betrayal decide the winner!",
        "min_players": 5,
        "max_players": 25,
        "emoji": "👑",
        "duration": "10–30 min",
        "category": "Social Deduction",
    }

    async def run(self):
        king = random.choice(self.players)
        nobles = [p for p in self.players if p != king]
        king_rounds: Dict[discord.Member, int] = {p: 0 for p in self.players}
        king_rounds[king] = 1

        intro = discord.Embed(
            title="👑 Kingmaker — All Hail the King!",
            description=f"**{king.display_name}** starts as King!\n\n"
                        "**Rules:**\n"
                        "• Each round, nobles **discuss** and **vote** to either keep the current king or elect a new one.\n"
                        "• Announce alliances in chat freely!\n"
                        "• The player who was King the **most total rounds** wins!\n\n"
                        "**5 rounds** of political intrigue begin!",
            color=discord.Color.gold(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for round_num in range(1, 6):
            if self.is_stopped():
                return

            round_e = discord.Embed(
                title=f"👑 Round {round_num} / 5 — Current King: {king.display_name}",
                description="**Discuss alliances and politics!** Then vote to keep the King or nominate a new one.\n"
                            "**60 seconds of discussion.**",
                color=discord.Color.gold(),
            )
            await self.channel.send(embed=round_e)
            if await self.wait_or_stop(60):
                return

            if self.is_stopped():
                return

            candidates = [p.display_name for p in self.players]
            vote_e = discord.Embed(
                title="🗳️ Vote for the Next King!",
                description="Vote for who you want to be King next round. **30 seconds.**",
                color=discord.Color.purple(),
            )
            view = self.track_view(VotingView(nobles, candidates, timeout=30.0))
            await self.channel.send(embed=vote_e, view=view)
            await asyncio.wait_for(view.wait(), timeout=32.0)

            if self.is_stopped():
                return

            winner_idx = view.winner_idx()
            if winner_idx is not None:
                king = self.players[winner_idx]
                king_rounds[king] = king_rounds.get(king, 0) + 1

            await self.channel.send(
                f"👑 **{king.display_name}** is crowned King for round {round_num + 1}!" if round_num < 5 else
                f"👑 **{king.display_name}** holds the crown as the game ends!"
            )

        if self.is_stopped():
            return

        ranking = sorted(king_rounds.items(), key=lambda x: -x[1])
        final = discord.Embed(title="👑 Kingmaker — Final Results!", color=discord.Color.gold())
        leaderboard = "\n".join(
            f"{'👑' if i == 0 else '▪️'} **{p.display_name}**: {r} round(s) as King"
            for i, (p, r) in enumerate(ranking) if r > 0
        )
        final.add_field(name="Total Rounds as King", value=leaderboard or "No rounds recorded", inline=False)
        final.add_field(name="🏆 Winner", value=f"**{ranking[0][0].display_name}** reigns supreme!", inline=False)
        await self.channel.send(embed=final)


# ── Assassin ──────────────────────────────────────────────────────────────────

class Assassin(BaseGame):
    GAME_INFO = {
        "name": "Assassin",
        "description": "Each player is secretly assigned a target to eliminate. Tag your target by typing their name + a secret code word in chat. Once tagged, you inherit their target. Last one standing wins!",
        "min_players": 4,
        "max_players": 20,
        "emoji": "🗡️",
        "duration": "15–60 min",
        "category": "Social Deduction",
    }

    async def run(self):
        code_word = random.choice(["banana", "pineapple", "cactus", "umbrella", "penguin", "volcano", "nebula"])
        random.shuffle(self.players)
        targets: Dict[discord.Member, discord.Member] = {
            self.players[i]: self.players[(i + 1) % len(self.players)]
            for i in range(len(self.players))
        }
        alive = list(self.players)

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        for p in self.players:
            e = discord.Embed(title="🗡️ Your Assassination Assignment", color=discord.Color.dark_red())
            e.description = (
                f"**Your target:** {targets[p].display_name}\n\n"
                f"**Code word:** `{code_word}`\n\n"
                "To eliminate your target, type their **exact display name** followed by the code word in chat.\n"
                "Example: `John banana`\n\n"
                "Once you eliminate them, you inherit **their** target.\n"
                "Last player alive wins!"
            )
            role_embeds[p] = e

        await self.reveal_roles(
            role_embeds,
            title="🗡️ Assassin — Assignments Sealed!",
            description="Click the button to secretly see your target and the code word — only you will see it.",
            button_label="🗡️ View My Assignment",
        )

        intro = discord.Embed(
            title="🗡️ Assassin — The Hunt Begins!",
            description=f"**{len(self.players)} players** have been assigned secret targets.\n\n"
                        "To eliminate your target, type their display name + the secret code word in this channel.\n"
                        "**Hint:** The code word is a fruit... or maybe a plant... or an animal.\n\n"
                        "The game runs for **10 minutes** or until only one player remains!",
            color=discord.Color.dark_red(),
        )
        await self.channel.send(embed=intro)

        eliminated: List[discord.Member] = []
        end_time = asyncio.get_event_loop().time() + 600  # 10 minutes

        while len(alive) > 1 and asyncio.get_event_loop().time() < end_time:
            if self.is_stopped():
                return

            remaining_time = end_time - asyncio.get_event_loop().time()
            msg = await self.listen_for_answer(
                check=lambda m: m.channel == self.channel and m.author in alive and code_word in m.content.lower(),
                timeout=min(remaining_time, 30),
            )
            if not msg:
                continue

            attacker = msg.author
            if attacker not in targets:
                continue

            target = targets[attacker]
            target_name_lower = target.display_name.lower()
            if target_name_lower not in msg.content.lower():
                continue

            # Valid kill!
            alive.remove(target)
            eliminated.append(target)

            # Inherit target
            old_target_of_target = targets.get(target)
            if old_target_of_target and old_target_of_target != attacker:
                targets[attacker] = old_target_of_target
                new_target_info = f"Your new target: **{old_target_of_target.display_name}**"
            else:
                targets.pop(attacker, None)
                new_target_info = "You have no more targets — you win!"

            await self.channel.send(
                embed=discord.Embed(
                    title="🗡️ Elimination!",
                    description=f"**{attacker.display_name}** eliminated **{target.display_name}**!\n"
                                f"**Remaining:** {len(alive)} players",
                    color=discord.Color.red(),
                )
            )
            new_target_embed = discord.Embed(
                title="🗡️ Target Eliminated!",
                description=f"✅ You eliminated **{target.display_name}**!\n\n{new_target_info}",
                color=discord.Color.dark_green(),
            )
            await self.reveal_roles(
                {attacker: new_target_embed},
                title="🗡️ New Assignment",
                description=f"**{attacker.mention}** — click to privately see your next target!",
                button_label="🗡️ View My Next Target",
            )

        if self.is_stopped():
            return

        result = discord.Embed(title="🗡️ Assassin — Game Over!", color=discord.Color.gold())
        if len(alive) == 1:
            result.add_field(name="🏆 Last Standing!", value=f"**{alive[0].display_name}** wins!", inline=False)
        else:
            result.add_field(name="Time's Up!", value=f"Survivors: {', '.join(p.display_name for p in alive)}", inline=False)
        result.add_field(
            name="Elimination Order",
            value="\n".join(f"{i+1}. {p.display_name}" for i, p in enumerate(eliminated)) or "None",
            inline=False,
        )
        await self.channel.send(embed=result)
