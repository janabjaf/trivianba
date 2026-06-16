# 🎮 PartyGames

A [Red-DiscordBot](https://github.com/Cog-Creators/Red-DiscordBot) cog (v3.5.x compatible) featuring **35 fully playable party games** — no web app, no external services, 100% Discord.

---

## Installation

```bash
[p]repo add jaffar21-cogs https://github.com/jaffar21/red-cogs
[p]cog install jaffar21-cogs partygames
[p]load partygames
```

---

## Quick Start

```
/play                          → picks from autocomplete list
/play Werewolf                 → starts Werewolf directly
/play Trivia Clash             → starts Trivia
/play Word Bomb                → starts Word Bomb
```

A **30-second lobby** opens. Players click **Join Game**. When time is up the game starts automatically.

---

## Admin Commands

| Command | Description |
|---|---|
| `/games end` | Force-stop the active game in the current channel |
| `/games setrole @Role` | Restrict game-starting to a specific role |
| `/games removerole @Role` | Remove a role from the allowed list |
| `/games listroles` | See which roles can start games |
| `/games status` | Show all games running on this server |
| `/games list` | Browse all 35 games with descriptions |
| `/games info <name>` | Detailed info about a specific game |

---

## All 35 Games

### 🎭 Social Deduction (9 games)

| Game | Players | Duration | Description |
|---|---|---|---|
| 🎭 Identity Theft | 3–20 | 5–20 min | Get a secret character. One player impersonates someone else. Vote to find the impersonator! |
| 🕵️ Alibi | 4–12 | 10–20 min | One player secretly committed the crime. Everyone presents an alibi — vote to find the culprit. |
| 🐺 Werewolf | 4–10 | 15–40 min | Classic werewolf with Seer, Doctor, Hunter, and Witch roles. Night DM actions + day voting. |
| 🌍 Spyfall | 3–10 | 10–20 min | Everyone knows the location except the Spy. Ask questions without giving it away. Vote for the spy! |
| 🎨 Fake Artist | 4–15 | 5–15 min | Give one-word clues about a secret word — one player doesn't know it. Vote for the fake! |
| 🔍 Murder Mystery | 4–12 | 10–25 min | A murder occurred! The detective eliminates suspects round by round using revealed clues. |
| 🏺 Auction Heist | 4–15 | 10–25 min | Bid on stolen artifacts (some fake). Undercover cops lurk among the bidders! |
| 👑 Kingmaker | 5–25 | 10–30 min | Nobles vote each round to change who wears the crown. Most total rounds as King wins! |
| 🗡️ Assassin | 4–20 | 15–60 min | Secret targets. Eliminate yours by saying their name + the code word. Last one standing wins! |

### 🎬 Creative (9 games)

| Game | Players | Duration | Description |
|---|---|---|---|
| 🎬 Movie Pitch | 3–20 | 5–15 min | Random genre + actors + object. Write the funniest pitch. Vote for the best! |
| 🔗 Chain Reaction | 3–30 | 5–20 min | Players take turns adding consequences to a starter event. Read the full chaos story at the end! |
| 🌌 Time Traveler | 4–15 | 10–20 min | Each player is secretly from a different era. React to scenarios as your era would. Others guess! |
| 🔥 Hot Take | 3–20 | 5–15 min | Submit your spiciest controversial opinion anonymously. Vote for the hottest take! |
| 😂 Emoji Story | 3–20 | 5–15 min | One player creates an emoji sequence. Others submit their funniest interpretation. |
| 📖 Story Time | 3–30 | 5–15 min | Build a collaborative story one sentence at a time. Read the masterpiece (or disaster) at the end! |
| ⚖️ Debate Club | 4–20 | 10–20 min | Randomly assigned sides of a debate. Make your case, then vote for the most convincing debater! |
| 😄 Quiplash | 3–20 | 10–20 min | Same absurd prompt, everyone submits a funny answer. Vote for the best. 3 rounds! |
| 🤹 Personality Swap | 4–15 | 10–20 min | Act like another player. Answer questions as them. Others guess who you're impersonating! |

### 💣 Word & Puzzle (8 games)

| Game | Players | Duration | Description |
|---|---|---|---|
| 💣 Word Bomb | 2–20 | 5–15 min | Type a word containing the shown letter combo before time runs out. Wrong or slow = eliminated! |
| 🔤 Alphabet Chain | 2–20 | 5–15 min | Name things in a category in alphabetical order. Fail to answer = out! |
| 🎯 Hangman | 2–20 | 5–10 min | Classic hangman! One player sets a word, everyone else guesses letters together. |
| 🔐 Escape Room | 2–30 | 5–20 min | Race to solve puzzles first. First correct answer = 2 pts, second = 1 pt. |
| ❓ 20 Questions | 2–20 | 5–15 min | One player thinks of something. Others ask yes/no questions to guess it in 20 questions. |
| 〰️ Wavelength | 2–20 | 10–20 min | Guess where a one-word clue lands on a spectrum (e.g. Cold ↔ Hot). Closest = most points! |
| 🚫 Taboo | 4–20 | 10–25 min | Describe a word without saying 5 forbidden words. Team guesses in 60 seconds. |
| 🔑 Codenames | 4–20 | 10–25 min | Two-team word guessing. Spymasters give clues. Avoid the assassin word! |

### 🏆 Competition (9 games)

| Game | Players | Duration | Description |
|---|---|---|---|
| 🎓 Trivia Clash | 2–30 | 10–20 min | 10 trivia questions from various categories. First to type the correct answer earns the point! |
| 🤔 Would You Rather | 2–30 | 5–15 min | Vote A or B on dilemmas. Match the majority → point. Who knows the group best? |
| 💰 Price Is Right | 2–20 | 10–20 min | Guess real-world prices without going over. Closest without exceeding wins each round! |
| 🔥 Hot Seat | 3–15 | 10–30 min | One player answers anything asked by the group. Majority votes Honest or BS. |
| ⚔️ Gladiator Draft | 2–8 | 10–25 min | Draft warriors from a pool of epic gladiators. Auto-simulated battles determine the champion! |
| 🧮 Math Duel | 2–20 | 5–10 min | Speed math competition! Problems get harder. First with the right answer wins. |
| 🎱 Bingo | 2–20 | 5–15 min | Classic B-I-N-G-O! Each player gets a unique card. Numbers called one by one. Shout BINGO! |
| 🤥 Two Truths and a Lie | 3–20 | 10–20 min | Submit 2 truths + 1 lie. Others vote for the lie. Fool everyone = max points! |
| 🏆 Gladiator Tournament | 2–16 | 10–30 min | Create a custom gladiator with a name + special ability. Bot narrates the epic tournament! |

---

## Architecture

```
partygames/
├── __init__.py            ← Red setup() entrypoint
├── partygames.py          ← Main cog: /play command + /games admin group
├── game_base.py           ← BaseGame ABC, LobbyView, VotingView, utilities
├── game_data.py           ← All static data (trivia, locations, fighters, words, etc.)
├── lobby.py               ← run_lobby() + start_game() lifecycle helpers
├── info.json              ← Cog metadata (Red-DiscordBot standard)
├── README.md              ← This file
└── games/
    ├── __init__.py        ← GAME_REGISTRY dict mapping names → classes
    ├── social.py          ← 9 social deduction games
    ├── creative.py        ← 9 creative games
    ├── word.py            ← 8 word & puzzle games
    └── competition.py     ← 9 competition & trivia games
```

### Key design decisions

- **Hybrid commands** — every command works as both a slash command (`/play`) and a text prefix command (`[p]play`), as required by Red-DiscordBot 3.5.x.
- **Autocomplete** — `/play` uses `@app_commands.autocomplete` so players can search all 35 game names inline.
- **BaseGame ABC** — all games inherit from `BaseGame` with a `run()` abstract method. Shared utilities: `wait_or_stop()`, `send_dm_safe()`, `track_view()`, `force_end()`.
- **Async-safe force-end** — `_stop_event: asyncio.Event` allows any game to be cancelled cleanly from `/games end` without leaving zombie tasks.
- **LobbyView** — all games use the same 30-second join lobby with Join/Leave buttons before the game starts.
- **No external services** — every game runs purely over Discord (DMs + channel messages + buttons + modals). No web server, no database.
- **Config** — uses `redbot.core.Config` for per-guild role restrictions. No SQL needed.

---

## Permissions

The bot needs:
- `Send Messages`
- `Embed Links`
- `Read Message History`
- `Add Reactions` (optional)
- **Send DMs** — several games (Werewolf, Spyfall, Assassin, etc.) require DMing players their secret roles. Players must have DMs open from server members.

---

## Compatibility

- Red-DiscordBot `3.5.x`
- discord.py `2.x`
- Python `3.8+`
- No extra pip dependencies

---

## License

MIT — free to use, fork, and modify.
