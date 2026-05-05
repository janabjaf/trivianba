# NBAdex — NBA All-Time Draft Game for Red-DiscordBot

The most complete NBA draft system ever built for Discord.  
400+ all-time players, 4 draft modes, full Discord UI, season simulation, and detailed rankings.

**Author:** jaffar21  
**Red Version:** 3.5.x  
**Python:** 3.8+

---

## Features

- **400+ NBA players** from every era — GOATs to role players, all rated
- **4 Draft Modes:** Snake, Auction, Best Ball, Random
- **Discord UI:** Dropdowns + buttons for picks and bids
- **Season Simulation:** 8-category scoring (PPG, RPG, APG, BPG, SPG, 3PM, FG%, FT%)
- **Playoffs & Champion** — Full bracket with detailed results
- **Player Rankings** — Paginated, filterable by position
- **Player Search** — Partial name search with stat breakdowns
- **Auto-pick** — Toggle autopick for any manager
- **Pick Timer** — 120s per pick, auto-picks on timeout
- **Draft History** — Last 10 drafts stored per server
- **Team Grades** — Letter grade system (S/A+/A/B+/B/C)

---

## Installation

```
[p]repo add jaffar21-cogs https://github.com/<your-username>/<your-repo-name>
[p]cog install jaffar21-cogs nbadex
[p]load nbadex
```

---

## Commands

All commands use the `[p]nbadraft` prefix (also aliased as `[p]nba` and `[p]nbadex`).

| Command | Description |
|---|---|
| `[p]nbadraft create [mode] [rounds] [teams]` | Create a new draft |
| `[p]nbadraft join` | Join a waiting draft |
| `[p]nbadraft begin` | Start the draft (host only) |
| `[p]nbadraft pick <player>` | Pick a player on your turn |
| `[p]nbadraft pickui [position]` | Open the dropdown pick menu |
| `[p]nbadraft nominate <player>` | Nominate a player (auction mode) |
| `[p]nbadraft bid <amount>` | Bid in auction mode |
| `[p]nbadraft pass` | Pass on auction nomination |
| `[p]nbadraft board` | Show the draft board |
| `[p]nbadraft team [@user]` | View a team's roster |
| `[p]nbadraft teams` | Browse all teams with navigation |
| `[p]nbadraft remaining [pos]` | Show available players |
| `[p]nbadraft autopick` | Toggle autopick |
| `[p]nbadraft simulate` | Simulate season & crown champion |
| `[p]nbadraft rankings [pos]` | Browse all-time player rankings |
| `[p]nbadraft player <name>` | Get full player stats |
| `[p]nbadraft search <query>` | Search players by name |
| `[p]nbadraft status` | Show current draft status |
| `[p]nbadraft modes` | Show all draft modes |
| `[p]nbadraft history` | Server draft history |
| `[p]nbadraft cancel` | Cancel draft (host/admin) |

---

## Draft Modes

### 🐍 Snake Draft (default)
Classic snake order — picks go 1→N in odd rounds, N→1 in even rounds. Best for strategic drafts.

### 💰 Auction Draft
Every manager starts with a $200 budget. Players are nominated one at a time and managers bid against each other. Any player is obtainable — if you're willing to pay.

### 🎱 Best Ball Draft
No lineup management required. Best available roster lineup is auto-calculated. Focus on depth and upside.

### 🎲 Random Draft
Players randomly assigned to all teams. Pure chaos — who gets Jordan?

---

## Player Tiers

| Tier | Label | Examples |
|---|---|---|
| 👑 1 | GOAT | Jordan, LeBron, Kareem, Magic, Wilt |
| ⭐ 2 | All-Time Great | Bird, Shaq, Duncan, Kobe, Russell |
| 🔥 3 | Star | Dirk, Stockton, Drexler, Durant, Curry |
| 💎 4 | Solid | Carmelo, Paul George, Butler, Westbrook |
| 🏃 5 | Role Player | Notable veterans and complementary pieces |

---

## Simulation

Uses 8-category fantasy scoring system:
- **PPG** — Points Per Game
- **RPG** — Rebounds Per Game  
- **APG** — Assists Per Game
- **BPG** — Blocks Per Game
- **SPG** — Steals Per Game
- **3PM** — 3-Pointers Made
- **FG%** — Field Goal Percentage
- **FT%** — Free Throw Percentage

Teams are scored by their top 8 players (85%) + bench (15%). Round-robin regular season followed by a playoff bracket. Slight variance added to simulate real-season randomness.

---

## Examples

**Create a standard 13-round snake draft for 8 teams:**
```
[p]nbadraft create
```

**Create a 10-round auction draft for 6 teams:**
```
[p]nbadraft create auction 10 6
```

**Look up Michael Jordan:**
```
[p]nbadraft player Michael Jordan
```

**Browse top centers:**
```
[p]nbadraft rankings C
```

**Simulate the season after the draft:**
```
[p]nbadraft simulate
```
