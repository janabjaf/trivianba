import asyncio
import random
import discord
from typing import Dict, List, Optional
from ..game_base import BaseGame, VotingView
from ..game_data import (
    MOVIE_GENRES, MOVIE_ACTORS, RIDICULOUS_OBJECTS,
    CHAIN_REACTION_STARTERS, TIME_TRAVELER_ERAS, TIME_TRAVELER_SCENARIOS,
    HOT_TAKE_PROMPTS, QUIPLASH_PROMPTS, DEBATE_TOPICS,
    PERSONALITY_SWAP_QUESTIONS,
)


# ── Modals ─────────────────────────────────────────────────────────────────────

class TextModal(discord.ui.Modal):
    answer = discord.ui.TextInput(
        label="Your Answer",
        style=discord.TextStyle.paragraph,
        max_length=400,
    )

    def __init__(self, title: str, label: str, placeholder: str, storage: dict, key, max_length: int = 400):
        super().__init__(title=title)
        self.answer.label = label
        self.answer.placeholder = placeholder
        self.answer.max_length = max_length
        self._storage = storage
        self._key = key

    async def on_submit(self, interaction: discord.Interaction):
        self._storage[self._key] = self.answer.value
        await interaction.response.send_message("✅ Submitted!", ephemeral=True)


class SubmitModalView(discord.ui.View):
    def __init__(self, eligible: list, storage: dict, modal_kwargs: dict, timeout: float = 60.0,
                 button_label: str = "✍️ Submit Answer"):
        super().__init__(timeout=timeout)
        self._eligible = eligible
        self._storage = storage
        self._modal_kwargs = modal_kwargs
        self._btn_label = button_label

        btn = discord.ui.Button(label=button_label, style=discord.ButtonStyle.primary)
        btn.callback = self._on_click
        self.add_item(btn)

    async def _on_click(self, interaction: discord.Interaction):
        if interaction.user not in self._eligible:
            await interaction.response.send_message("You're not in this game!", ephemeral=True)
            return
        modal = TextModal(
            **self._modal_kwargs,
            storage=self._storage,
            key=interaction.user,
        )
        await interaction.response.send_modal(modal)
        if len(self._storage) >= len(self._eligible):
            self.stop()


# ── Movie Pitch ────────────────────────────────────────────────────────────────

class MoviePitch(BaseGame):
    GAME_INFO = {
        "name": "Movie Pitch",
        "description": "Each player gets a random genre, 2 actors, and a ridiculous object. Write the funniest movie pitch, then vote for the best one!",
        "min_players": 3,
        "max_players": 20,
        "emoji": "🎬",
        "duration": "5–15 min",
        "category": "Creative",
    }

    async def run(self):
        assignments = {}
        assign_embeds: Dict[discord.Member, discord.Embed] = {}
        for p in self.players:
            genre = random.choice(MOVIE_GENRES)
            actors = random.sample(MOVIE_ACTORS, 2)
            obj = random.choice(RIDICULOUS_OBJECTS)
            assignments[p] = {"genre": genre, "actors": actors, "object": obj}
            e = discord.Embed(title="🎬 Your Movie Pitch Assignment!", color=discord.Color.blurple())
            e.add_field(name="Genre", value=genre, inline=True)
            e.add_field(name="Starring", value=" & ".join(actors), inline=True)
            e.add_field(name="Must Include", value=obj, inline=True)
            e.set_footer(text="Submit your pitch using the button in the game channel!")
            assign_embeds[p] = e

        await self.reveal_roles(
            assign_embeds,
            title="🎬 Movie Pitch — Assignments Sealed!",
            description="Click the button to secretly view your assignment — only you will see it.",
            button_label="🎬 View My Assignment",
        )

        assignments_text = "\n".join(
            f"• **{p.display_name}**: {d['genre']} starring {' & '.join(d['actors'])} + {d['object']}"
            for p, d in assignments.items()
        )
        intro = discord.Embed(
            title="🎬 Movie Pitch — Write Your Pitch!",
            description=f"Everyone has their assignment!\n\n{assignments_text}\n\n"
                        "Click **Submit Pitch** below to write your movie pitch. **3 minutes.**",
            color=discord.Color.blurple(),
        )
        pitches: Dict = {}
        view = self.track_view(
            SubmitModalView(
                eligible=self.players,
                storage=pitches,
                modal_kwargs={
                    "title": "Your Movie Pitch",
                    "label": "Write your pitch (max 400 chars)",
                    "placeholder": "In a world where...",
                },
                timeout=180.0,
                button_label="🎬 Submit Pitch",
            )
        )
        await self.channel.send(embed=intro, view=view)
        await asyncio.wait_for(view.wait(), timeout=182.0)

        if self.is_stopped():
            return
        if len(pitches) < 2:
            await self.channel.send("Not enough pitches submitted. Game cancelled.")
            return

        # Reveal pitches anonymously, then vote
        submitted = list(pitches.items())
        random.shuffle(submitted)
        pitch_reveal = discord.Embed(title="🎬 The Pitches!", color=discord.Color.gold())
        for i, (player, pitch) in enumerate(submitted, 1):
            pitch_reveal.add_field(name=f"Pitch #{i}", value=pitch[:300], inline=False)
        await self.channel.send(embed=pitch_reveal)

        vote_e = discord.Embed(
            title="🗳️ Vote for the Best Pitch! (30 sec)",
            description="Which pitch is the best / funniest?",
            color=discord.Color.purple(),
        )
        options = [f"Pitch #{i+1}" for i in range(len(submitted))]
        view2 = self.track_view(VotingView(self.players, options, timeout=30.0))
        await self.channel.send(embed=vote_e, view=view2)
        await asyncio.wait_for(view2.wait(), timeout=32.0)

        if self.is_stopped():
            return

        winner_idx = view2.winner_idx()
        winner_player, winning_pitch = submitted[winner_idx] if winner_idx is not None else (None, "")
        result = discord.Embed(title="🎬 Movie Pitch — Winner!", color=discord.Color.gold())
        if winner_player:
            d = assignments[winner_player]
            result.add_field(name=f"🏆 {winner_player.display_name} wins!", value=winning_pitch[:400], inline=False)
            result.add_field(name="Assignment was:", value=f"{d['genre']} • {' & '.join(d['actors'])} • {d['object']}", inline=False)
        await self.channel.send(embed=result)


# ── Chain Reaction ─────────────────────────────────────────────────────────────

class ChainReaction(BaseGame):
    GAME_INFO = {
        "name": "Chain Reaction",
        "description": "Players take turns adding consequences to a starter event. Each addition must logically (or hilariously) follow from the last. The bot scores the chaos!",
        "min_players": 3,
        "max_players": 30,
        "emoji": "🔗",
        "duration": "5–20 min",
        "category": "Creative",
    }

    async def run(self):
        starter = random.choice(CHAIN_REACTION_STARTERS)
        chain = [("🌍 Starter Event", starter)]

        intro = discord.Embed(
            title="🔗 Chain Reaction — It Begins!",
            description=f"**Starter event:** {starter}\n\n"
                        "Each player takes a turn adding **one consequence** to the chain!\n"
                        "Make it logical, funny, or chaotic — the bot will score the reaction.",
            color=discord.Color.orange(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for player in self.players:
            if self.is_stopped():
                return
            last_event = chain[-1][1]
            e = discord.Embed(
                title=f"🔗 {player.display_name}'s Turn",
                description=f"**Last event:** *{last_event}*\n\n"
                            f"**{player.mention}** — type your consequence! What happens next? **45 seconds.**",
                color=discord.Color.blurple(),
            )
            await self.channel.send(embed=e)
            msg = await self.listen_for_answer(
                check=lambda m: m.channel == self.channel and m.author == player and len(m.content) > 3,
                timeout=45.0,
            )
            if msg:
                chain.append((player.display_name, msg.content))
            else:
                chain.append((f"{player.display_name} (skipped)", "*(No response — the universe shrugs.)*"))

        if self.is_stopped():
            return

        # Show the full chain with chaos scoring
        chaos_score = random.randint(60, 100)
        chain_text = "\n\n".join(f"**{name}:** {event}" for name, event in chain)
        result = discord.Embed(
            title="🔗 Chain Reaction — The Full Story!",
            description=chain_text[:4000],
            color=discord.Color.orange(),
        )
        result.set_footer(text=f"🌡️ Chaos Score: {chaos_score}/100 — {'Maximum Chaos! 🔥' if chaos_score >= 90 else 'Delightful Mayhem! ⚡' if chaos_score >= 75 else 'Decent Disruption 🌀'}")
        await self.channel.send(embed=result)


# ── Time Traveler ─────────────────────────────────────────────────────────────

class TimeTraveler(BaseGame):
    GAME_INFO = {
        "name": "Time Traveler",
        "description": "Each player is secretly from a different era in history. React to scenarios as your era would. Others try to guess which era you're from!",
        "min_players": 4,
        "max_players": 15,
        "emoji": "🌌",
        "duration": "10–20 min",
        "category": "Creative",
    }

    async def run(self):
        eras = random.sample(TIME_TRAVELER_ERAS, min(len(self.players), len(TIME_TRAVELER_ERAS)))
        while len(eras) < len(self.players):
            eras.append(random.choice(TIME_TRAVELER_ERAS))

        era_assignments = {self.players[i]: eras[i] for i in range(len(self.players))}

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        for p, era in era_assignments.items():
            e = discord.Embed(
                title=f"🌌 You Are From: {era['emoji']} {era['name']}",
                color=discord.Color.blurple(),
            )
            e.description = (
                f"**Context:** {era['hint']}\n\n"
                "When scenarios are presented, respond **as someone from your era would**.\n"
                "Others will try to guess your time period — fool them!"
            )
            role_embeds[p] = e

        await self.reveal_roles(
            role_embeds,
            title="🌌 Time Traveler — Eras Assigned!",
            description="Click the button to secretly see your era — only you will see it.",
            button_label="🌌 View My Era",
        )

        era_display = " | ".join(f"{e['emoji']} {e['name']}" for e in eras)
        intro = discord.Embed(
            title="🌌 Time Traveler — Across the Ages!",
            description=f"Everyone has secretly been assigned an era!\n\n"
                        f"**Eras in play:** {era_display}\n\n"
                        "**3 scenarios** will be presented. React as your era would!\n"
                        "After each scenario, everyone votes to guess who came from which era.",
            color=discord.Color.dark_blue(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}
        scenarios = random.sample(TIME_TRAVELER_SCENARIOS, 3)

        for round_num, scenario in enumerate(scenarios, 1):
            if self.is_stopped():
                return

            scen_e = discord.Embed(
                title=f"🌌 Scenario {round_num} / 3",
                description=f"**{scenario}**\n\n"
                            "Everyone respond from **your era's perspective** in the channel! **90 seconds.**",
                color=discord.Color.teal(),
            )
            await self.channel.send(embed=scen_e)
            if await self.wait_or_stop(90):
                return

            if self.is_stopped():
                return

            # Vote: guess which player is from which era
            for guesser in self.players:
                if self.is_stopped():
                    return
                others = [p for p in self.players if p != guesser]
                if not others:
                    continue
                options = [p.display_name for p in others]
                era_list = "\n".join(f"{e['emoji']} {e['name']}" for e in eras[:len(others)])
                vote_e = discord.Embed(
                    title=f"🌌 Guess the Eras! (Round {round_num})",
                    description=f"Eras in play:\n{era_list}\n\n"
                                "Who do you think is from the **oldest era**? **20 seconds.**",
                    color=discord.Color.purple(),
                )
                view = self.track_view(VotingView([guesser], options, timeout=20.0))
                await self.channel.send(content=guesser.mention, embed=vote_e, view=view)
                await asyncio.wait_for(view.wait(), timeout=22.0)
                winner_idx = view.winner_idx()
                if winner_idx is not None:
                    guessed = others[winner_idx]
                    guessed_era = era_assignments[guessed]
                    actual_oldest = min(era_assignments.values(), key=lambda e: TIME_TRAVELER_ERAS.index(e))
                    if guessed_era == actual_oldest:
                        scores[guesser] += 2
                        await self.channel.send(f"✅ Correct! +2 points for {guesser.display_name}")
                    else:
                        await self.channel.send(f"❌ Wrong!")

        if self.is_stopped():
            return

        # Era Reveal
        reveal_e = discord.Embed(title="🌌 Era Reveal!", color=discord.Color.gold())
        for p, era in era_assignments.items():
            reveal_e.add_field(name=p.display_name, value=f"{era['emoji']} {era['name']}", inline=True)
        await self.channel.send(embed=reveal_e)

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        result = discord.Embed(title="🌌 Time Traveler — Final Scores!", color=discord.Color.blurple())
        result.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
            inline=False,
        )
        await self.channel.send(embed=result)


# ── Hot Take ──────────────────────────────────────────────────────────────────

class HotTake(BaseGame):
    GAME_INFO = {
        "name": "Hot Take",
        "description": "Everyone submits their spiciest controversial opinion on a given topic. Vote for the hottest take!",
        "min_players": 3,
        "max_players": 20,
        "emoji": "🔥",
        "duration": "5–15 min",
        "category": "Creative",
    }

    async def run(self):
        prompt = random.choice(HOT_TAKE_PROMPTS)
        takes: Dict = {}

        intro = discord.Embed(
            title="🔥 Hot Take — Submit Your Opinion!",
            description=f"**Topic:** {prompt}\n\n"
                        "Click the button to submit your **spiciest hot take** anonymously! **2 minutes.**",
            color=discord.Color.red(),
        )
        view = self.track_view(
            SubmitModalView(
                eligible=self.players,
                storage=takes,
                modal_kwargs={
                    "title": "Submit Your Hot Take",
                    "label": "Your hot take",
                    "placeholder": "My controversial opinion is...",
                },
                timeout=120.0,
                button_label="🔥 Submit Hot Take",
            )
        )
        await self.channel.send(embed=intro, view=view)
        await asyncio.wait_for(view.wait(), timeout=122.0)

        if self.is_stopped():
            return
        if len(takes) < 2:
            await self.channel.send("Not enough takes submitted. Game cancelled.")
            return

        submitted = list(takes.items())
        random.shuffle(submitted)
        reveal = discord.Embed(title="🔥 The Hot Takes!", color=discord.Color.red())
        for i, (_, take) in enumerate(submitted, 1):
            reveal.add_field(name=f"🌶️ Take #{i}", value=take[:300], inline=False)
        await self.channel.send(embed=reveal)

        vote_e = discord.Embed(
            title="🗳️ Vote: Which Is The HOTTEST Take? (30 sec)",
            color=discord.Color.orange(),
        )
        options = [f"Take #{i+1}" for i in range(len(submitted))]
        view2 = self.track_view(VotingView(self.players, options, timeout=30.0))
        await self.channel.send(embed=vote_e, view=view2)
        await asyncio.wait_for(view2.wait(), timeout=32.0)

        if self.is_stopped():
            return

        winner_idx = view2.winner_idx()
        if winner_idx is not None:
            winning_player, winning_take = submitted[winner_idx]
            result = discord.Embed(title="🔥 Hottest Take Award!", color=discord.Color.red())
            result.add_field(name=f"🏆 {winning_player.display_name} wins!", value=winning_take[:400], inline=False)
            result.set_footer(text="Temperature: SCORCHING 🌡️")
            await self.channel.send(embed=result)


# ── Emoji Story ────────────────────────────────────────────────────────────────

class EmojiStory(BaseGame):
    GAME_INFO = {
        "name": "Emoji Story",
        "description": "One player creates an emoji sequence. Everyone else submits their funniest interpretation. Vote for the best one!",
        "min_players": 3,
        "max_players": 20,
        "emoji": "😂",
        "duration": "5–15 min",
        "category": "Creative",
    }

    async def run(self):
        storyteller = random.choice(self.players)
        interpreters = [p for p in self.players if p != storyteller]

        intro = discord.Embed(
            title="😂 Emoji Story — Create Your Sequence!",
            description=f"**{storyteller.mention}** is the Storyteller!\n\n"
                        "**Storyteller:** Type a sequence of **5–10 emojis** in the channel that tells a story.\n"
                        "Everyone else will interpret what they mean! **60 seconds to create your sequence.**",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)

        emoji_msg = await self.listen_for_answer(
            check=lambda m: m.channel == self.channel and m.author == storyteller and len(m.content) > 1,
            timeout=60.0,
        )
        if not emoji_msg:
            await self.channel.send("No emoji sequence was submitted. Game cancelled.")
            return

        emoji_sequence = emoji_msg.content

        if self.is_stopped():
            return

        interpret_e = discord.Embed(
            title="😂 Interpret The Emojis!",
            description=f"**Emoji sequence:** {emoji_sequence}\n\n"
                        "Click the button to submit your interpretation! **2 minutes.**",
            color=discord.Color.gold(),
        )
        interpretations: Dict = {}
        view = self.track_view(
            SubmitModalView(
                eligible=interpreters,
                storage=interpretations,
                modal_kwargs={
                    "title": "Your Interpretation",
                    "label": "What does this emoji sequence mean?",
                    "placeholder": "In this emoji story...",
                },
                timeout=120.0,
                button_label="😂 Submit Interpretation",
            )
        )
        await self.channel.send(embed=interpret_e, view=view)
        await asyncio.wait_for(view.wait(), timeout=122.0)

        if self.is_stopped():
            return
        if len(interpretations) < 1:
            await self.channel.send("No interpretations submitted. Game cancelled.")
            return

        submitted = list(interpretations.items())
        random.shuffle(submitted)
        reveal = discord.Embed(
            title=f"😂 Interpretations of: {emoji_sequence}",
            color=discord.Color.orange(),
        )
        for i, (_, interp) in enumerate(submitted, 1):
            reveal.add_field(name=f"Interpretation #{i}", value=interp[:300], inline=False)
        await self.channel.send(embed=reveal)

        if len(submitted) >= 2:
            options = [f"#{i+1}" for i in range(len(submitted))]
            view2 = self.track_view(VotingView(self.players, options, timeout=30.0))
            await self.channel.send(
                embed=discord.Embed(title="🗳️ Best Interpretation? (30 sec)", color=discord.Color.purple()),
                view=view2,
            )
            await asyncio.wait_for(view2.wait(), timeout=32.0)

            if self.is_stopped():
                return

            winner_idx = view2.winner_idx()
            if winner_idx is not None:
                w_player, w_interp = submitted[winner_idx]
                await self.channel.send(
                    embed=discord.Embed(
                        title=f"😂 Best Interpretation by {w_player.display_name}!",
                        description=w_interp[:400],
                        color=discord.Color.gold(),
                    )
                )

        # Storyteller reveal
        storyteller_e = discord.Embed(
            title=f"😂 What {storyteller.display_name} Actually Meant:",
            description="*(Only the storyteller knows the true meaning — ask them!)*",
            color=discord.Color.teal(),
        )
        await self.channel.send(embed=storyteller_e)


# ── Story Time ────────────────────────────────────────────────────────────────

class StoryTime(BaseGame):
    GAME_INFO = {
        "name": "Story Time",
        "description": "Players collaborate to write a story one sentence at a time. Each player adds a single sentence. Read the final epic (or disaster) together!",
        "min_players": 3,
        "max_players": 30,
        "emoji": "📖",
        "duration": "5–15 min",
        "category": "Creative",
    }

    STARTERS = [
        "The last train of the night pulled into an empty station, and the only passenger stepped out into the fog.",
        "Nobody expected the new librarian to arrive on a motorcycle and immediately start removing books from the shelves.",
        "The message in the bottle read: 'If you find this, don't go back to your house tonight.'",
        "There was a door at the end of the hallway that nobody in the office had ever noticed — until Tuesday.",
        "The world's best detective retired on a Monday and by Friday had been pulled into the most bizarre case of her career.",
        "It began, as most disasters do, with someone saying 'How hard could it be?'",
        "The alien looked around at Earth and pulled out a clipboard. 'Right,' it said. 'Who's in charge here?'",
        "The old man claimed he'd been asleep for twenty years. The problem was, nobody remembered him waking up.",
    ]

    async def run(self):
        starter = random.choice(self.STARTERS)
        story = [("Narrator", starter)]

        intro = discord.Embed(
            title="📖 Story Time — Let's Write!",
            description=f"**Opening line:** *{starter}*\n\n"
                        "Each player adds **one sentence** in turn. Keep it coherent, interesting, or hilariously chaotic!\n"
                        "**45 seconds per turn.** After everyone goes twice, we'll read the final story.",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        rounds = 2
        for round_num in range(1, rounds + 1):
            for player in self.players:
                if self.is_stopped():
                    return
                last_line = story[-1][1]
                e = discord.Embed(
                    title=f"📖 Round {round_num} — {player.display_name}'s Turn",
                    description=f"**Last line:** *{last_line}*\n\n"
                                f"**{player.mention}** — add your sentence! **45 seconds.**",
                    color=discord.Color.teal(),
                )
                await self.channel.send(embed=e)
                msg = await self.listen_for_answer(
                    check=lambda m: m.channel == self.channel and m.author == player and len(m.content) > 3,
                    timeout=45.0,
                )
                if msg:
                    story.append((player.display_name, msg.content))
                else:
                    story.append((f"{player.display_name} (skipped)", "*(The story paused for a moment…)*"))

        if self.is_stopped():
            return

        full_story = " ".join(line for _, line in story)
        result = discord.Embed(
            title="📖 The Final Story!",
            description=full_story[:4000],
            color=discord.Color.gold(),
        )
        result.set_footer(text="Collaborative masterpiece — or disaster — by " + ", ".join(p.display_name for p in self.players))
        await self.channel.send(embed=result)


# ── Debate Club ───────────────────────────────────────────────────────────────

class DebateClub(BaseGame):
    GAME_INFO = {
        "name": "Debate Club",
        "description": "Players are randomly assigned sides of a debate topic. Make your best argument, then vote for the most convincing debater!",
        "min_players": 4,
        "max_players": 20,
        "emoji": "⚖️",
        "duration": "10–20 min",
        "category": "Creative",
    }

    async def run(self):
        topic_sides = random.choice(DEBATE_TOPICS)
        side_a, side_b = topic_sides
        random.shuffle(self.players)
        mid = len(self.players) // 2
        team_a = self.players[:mid]
        team_b = self.players[mid:]

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        for p in team_a:
            e = discord.Embed(title="⚖️ Your Debate Side", color=discord.Color.blue())
            e.description = f"**You are arguing FOR:**\n\n*\"{side_a}\"*\n\nPrepare your arguments!"
            role_embeds[p] = e
        for p in team_b:
            e = discord.Embed(title="⚖️ Your Debate Side", color=discord.Color.red())
            e.description = f"**You are arguing FOR:**\n\n*\"{side_b}\"*\n\nPrepare your arguments!"
            role_embeds[p] = e

        await self.reveal_roles(
            role_embeds,
            title="⚖️ Debate Club — Sides Assigned!",
            description="Click the button to secretly see which side you're arguing — only you will see it.",
            button_label="⚖️ View My Side",
        )

        intro = discord.Embed(
            title="⚖️ Debate Club — The Topic!",
            description=f"**Today's Debate:**\n\n"
                        f"🔵 **Team A:** *{side_a}*\n"
                        f"🔴 **Team B:** *{side_b}*\n\n"
                        f"**Team A:** {', '.join(p.display_name for p in team_a)}\n"
                        f"**Team B:** {', '.join(p.display_name for p in team_b)}\n\n"
                        "Each team gets **2 minutes** to make their arguments in the channel.\nThen everyone votes!",
            color=discord.Color.gold(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for team, side, color in [(team_a, side_a, "🔵"), (team_b, side_b, "🔴")]:
            if self.is_stopped():
                return
            members = ", ".join(p.display_name for p in team)
            e = discord.Embed(
                title=f"{color} {members} — Argue Your Case!",
                description=f"**Your position:** *\"{side}\"*\n\n"
                            "Make your arguments in the channel! **2 minutes.**",
                color=discord.Color.blue() if color == "🔵" else discord.Color.red(),
            )
            await self.channel.send(embed=e, content=" ".join(p.mention for p in team))
            if await self.wait_or_stop(120):
                return

        if self.is_stopped():
            return

        vote_e = discord.Embed(
            title="🗳️ Vote — Which Side Was More Convincing? (30 sec)",
            color=discord.Color.purple(),
        )
        view = self.track_view(VotingView(self.players, [f"🔵 {side_a[:60]}", f"🔴 {side_b[:60]}"], timeout=30.0))
        await self.channel.send(embed=vote_e, view=view)
        await asyncio.wait_for(view.wait(), timeout=32.0)

        if self.is_stopped():
            return

        tally = view.tally()
        a_votes = tally.get(0, 0)
        b_votes = tally.get(1, 0)
        winner_team = team_a if a_votes >= b_votes else team_b
        winner_side = side_a if a_votes >= b_votes else side_b

        result = discord.Embed(title="⚖️ Debate Club — Verdict!", color=discord.Color.gold())
        result.add_field(name=f"🔵 {side_a[:60]}", value=f"{a_votes} vote(s)", inline=True)
        result.add_field(name=f"🔴 {side_b[:60]}", value=f"{b_votes} vote(s)", inline=True)
        result.add_field(
            name="🏆 Winning Team",
            value=f"{', '.join(p.display_name for p in winner_team)}\n*\"{winner_side}\"*",
            inline=False,
        )
        await self.channel.send(embed=result)


# ── Quiplash ──────────────────────────────────────────────────────────────────

class Quiplash(BaseGame):
    GAME_INFO = {
        "name": "Quiplash",
        "description": "Everyone gets the same absurd prompt and submits a funny answer. Then vote for the best one! 3 rounds of laughs.",
        "min_players": 3,
        "max_players": 20,
        "emoji": "😄",
        "duration": "10–20 min",
        "category": "Creative",
    }

    async def run(self):
        prompts = random.sample(QUIPLASH_PROMPTS, 3)
        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}

        intro = discord.Embed(
            title="😄 Quiplash — Let's Get Weird!",
            description="3 rounds of absurd prompts!\n"
                        "Each round: submit your funniest answer, then vote for the best one.\n"
                        "**You cannot vote for your own answer.**",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        for round_num, prompt in enumerate(prompts, 1):
            if self.is_stopped():
                return

            answers: Dict = {}
            prompt_e = discord.Embed(
                title=f"😄 Round {round_num} / 3",
                description=f"**Prompt:** *{prompt}*\n\nSubmit your answer! **90 seconds.**",
                color=discord.Color.blurple(),
            )
            view = self.track_view(
                SubmitModalView(
                    eligible=self.players,
                    storage=answers,
                    modal_kwargs={
                        "title": f"Round {round_num}: {prompt[:40]}",
                        "label": "Your answer",
                        "placeholder": "Type your funniest answer...",
                        "max_length": 200,
                    },
                    timeout=90.0,
                    button_label="😄 Submit Answer",
                )
            )
            await self.channel.send(embed=prompt_e, view=view)
            await asyncio.wait_for(view.wait(), timeout=92.0)

            if self.is_stopped():
                return
            if len(answers) < 2:
                await self.channel.send(f"Not enough answers for round {round_num}. Skipping.")
                continue

            submitted = list(answers.items())
            random.shuffle(submitted)
            reveal = discord.Embed(
                title=f"😄 Round {round_num} Answers — *{prompt}*",
                color=discord.Color.gold(),
            )
            for i, (_, answer) in enumerate(submitted, 1):
                reveal.add_field(name=f"Answer #{i}", value=answer[:200], inline=False)
            await self.channel.send(embed=reveal)

            # Vote (no self-voting enforced per answer)
            options = [f"Answer #{i+1}" for i in range(len(submitted))]
            view2 = self.track_view(VotingView(self.players, options, timeout=25.0))
            await self.channel.send(
                embed=discord.Embed(title="🗳️ Best Answer? (25 sec)", color=discord.Color.purple()),
                view=view2,
            )
            await asyncio.wait_for(view2.wait(), timeout=27.0)

            if self.is_stopped():
                return

            winner_idx = view2.winner_idx()
            if winner_idx is not None:
                w_player, w_answer = submitted[winner_idx]
                scores[w_player] += 100
                tally = view2.tally()
                votes_got = tally.get(winner_idx, 0)
                scores[w_player] += votes_got * 10
                await self.channel.send(
                    embed=discord.Embed(
                        title=f"😄 Round {round_num} Winner: {w_player.display_name}!",
                        description=f"*\"{w_answer}\"*\n\n+{100 + votes_got * 10} points!",
                        color=discord.Color.gold(),
                    )
                )

        if self.is_stopped():
            return

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        result = discord.Embed(title="😄 Quiplash — Final Scores!", color=discord.Color.gold())
        result.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '🥈' if i==1 else '🥉' if i==2 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        await self.channel.send(embed=result)


# ── Personality Swap ──────────────────────────────────────────────────────────

class PersonalitySwap(BaseGame):
    GAME_INFO = {
        "name": "Personality Swap",
        "description": "Each player is assigned to act like another player. Answer questions as your assigned person would — others guess who you're impersonating!",
        "min_players": 4,
        "max_players": 15,
        "emoji": "🤹",
        "duration": "10–20 min",
        "category": "Creative",
    }

    async def run(self):
        shuffled = list(self.players)
        random.shuffle(shuffled)
        assignments = {shuffled[i]: shuffled[(i + 1) % len(shuffled)] for i in range(len(shuffled))}

        role_embeds: Dict[discord.Member, discord.Embed] = {}
        for p, target in assignments.items():
            e = discord.Embed(title="🤹 Personality Swap — Your Assignment!", color=discord.Color.blurple())
            e.description = (
                f"**Act like: {target.display_name}**\n\n"
                "Answer every question as you think THEY would answer it.\n"
                "If others can't guess you're impersonating them, you win points!\n"
                "Keep it subtle — don't be too obvious!"
            )
            role_embeds[p] = e

        await self.reveal_roles(
            role_embeds,
            title="🤹 Personality Swap — Assignments Sealed!",
            description="Click the button to secretly see who you're impersonating — only you will see it.",
            button_label="🤹 View My Assignment",
        )

        intro = discord.Embed(
            title="🤹 Personality Swap — The Impersonation Begins!",
            description="Everyone has secretly been assigned someone else to impersonate!\n\n"
                        "**3 rounds of questions.** Answer as your assigned person would.\n"
                        "After each round, vote on who you think is impersonating who!",
            color=discord.Color.blurple(),
        )
        await self.channel.send(embed=intro)
        if await self.wait_or_stop(5):
            return

        questions = random.sample(PERSONALITY_SWAP_QUESTIONS, 3)
        scores: Dict[discord.Member, int] = {p: 0 for p in self.players}

        for round_num, question in enumerate(questions, 1):
            if self.is_stopped():
                return

            q_e = discord.Embed(
                title=f"🤹 Round {round_num} / 3",
                description=f"**Question:** {question}\n\n"
                            "Answer in the channel as the person you're impersonating! **60 seconds.**",
                color=discord.Color.teal(),
            )
            await self.channel.send(embed=q_e)
            if await self.wait_or_stop(60):
                return

            if self.is_stopped():
                return

            # Vote for one player to guess who they're impersonating
            spotlight = random.choice(self.players)
            other_players = [p for p in self.players if p != spotlight]
            options = [p.display_name for p in other_players]
            vote_e = discord.Embed(
                title=f"🤹 Who Is {spotlight.display_name} Impersonating?",
                description="Vote! **20 seconds.**",
                color=discord.Color.purple(),
            )
            view = self.track_view(VotingView([p for p in self.players if p != spotlight], options, timeout=20.0))
            await self.channel.send(embed=vote_e, view=view)
            await asyncio.wait_for(view.wait(), timeout=22.0)

            if self.is_stopped():
                return

            winner_idx = view.winner_idx()
            guessed = other_players[winner_idx] if winner_idx is not None else None
            actual_target = assignments[spotlight]

            if guessed == actual_target:
                voters_right = [v for v, idx in view.votes.items() if idx == winner_idx]
                for v in voters_right:
                    scores[v] += 1
                await self.channel.send(f"✅ Correct! **{spotlight.display_name}** was impersonating **{actual_target.display_name}**!")
            else:
                scores[spotlight] += 2
                await self.channel.send(f"❌ Wrong! Nobody guessed **{spotlight.display_name}** was impersonating **{actual_target.display_name}**! +2 for {spotlight.display_name}!")

        if self.is_stopped():
            return

        reveal_e = discord.Embed(title="🤹 The Full Impersonation Reveal!", color=discord.Color.gold())
        for p, target in assignments.items():
            reveal_e.add_field(name=p.display_name, value=f"was impersonating **{target.display_name}**", inline=True)
        await self.channel.send(embed=reveal_e)

        ranking = sorted(scores.items(), key=lambda x: -x[1])
        result = discord.Embed(title="🤹 Personality Swap — Final Scores!", color=discord.Color.blurple())
        result.add_field(
            name="Leaderboard",
            value="\n".join(f"{'🥇' if i==0 else '▪️'} {p.display_name}: {s} pts" for i, (p, s) in enumerate(ranking)),
        )
        await self.channel.send(embed=result)
