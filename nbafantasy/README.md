## 🚨 2026-10-19 hotfix: pre-season FP inflation (stale-season-data bug)

**Symptom:** the day after a league drafted, one day before the real 2026-27
opener, `.fantasy team` suddenly showed massive totals (thousands of FP per
team, individual players at 700–3000+ FP) with zero games played.

**Root cause:** ESPN's stats leaderboard endpoint doesn't reliably 404/empty
out when you ask for a brand-new season's id (`season=2027`) before that
season is fully live on their end — in the window right before/after a new
season's opening night it can silently serve back **last season's final
totals** as if they were this season's live stats. A background refresh
(`.fantasy update`, or the hourly auto-refresh loop) pulled that stale data
in and it got treated as real, live, current-season production.

This was never a "the season hasn't started yet so give it time" situation —
it would **not** have fixed itself after the first real game. Each refresh
would have kept re-serving the same stale numbers until ESPN's backend
caught up, and real game stats would then have been added on top of the
bogus totals instead of replacing them.

**Fix:** the stats refresh now cross-checks the "current season" numbers it
gets back against last season's final totals before trusting them. If most
overlapping players match almost exactly, that's proof the data isn't live —
it's discarded and every player is correctly treated as scoreless until real
games actually happen. (Draft baselines in your league were captured back
when stats were still correctly at 0, so once you reload this fixed version
and run `.fantasy update`, everyone's total drops right back to 0 — nothing
about your draft, rosters, or standings positions is lost.)

**Also fixed in the same pass:**
- **Trade double-accept race:** validation ran on a snapshot taken *before* the roster lock, so a double-click/retried Accept could process one trade twice and double-bank FP. Validation + swap now happen atomically under one lock; a second accept just reports the trade is already processed.
- **Admin force-add race:** the "already on another team" check now runs inside the same lock as the write.

- **ESPN-accurate positions (main + secondary):** players now carry ESPN's own fantasy eligibility (e.g. Giannis = PF/C, Grayson Allen = SG/PG) instead of the single coarse roster position. Slot rules follow ESPN: G = PG/SG, F = SF/PF, UTIL = anyone, C = centers only. Old lenient mappings (e.g. a PF fitting the C slot, SG fitting SF) were wrong and are fixed. If the position feed is ever unreachable, the last known positions are kept (or the single roster position is used as a fallback).

- **Rostered players can't vanish:** a player on a fantasy roster who disappears from the NBA feed (cut/waived) is kept in the pool as FA, so he stays visible, droppable, and his points aren't lost.
- **Free agency blocked during a draft** even if an admin unlocks it; the draft finishing now unlocks FA atomically with the last pick.
- **`draft forcepick` (alias `skip`):** admin command to auto-pick for whoever is on the clock when a manager is away.
- **Draft safety:** `draft stop` only acts on a live draft; removing a manager can no longer leave a draft stuck "active" with no picks left; the draft board guards against an out-of-range pick pointer.
- **Embed limits:** pick history now respects Discord's 6000-character total embed cap on big drafts.
- **Scoring edits** reject NaN/infinity/absurd values; draft/free-agent/force-add boards can only be paged by whoever opened them.
- **Commands are server-only** (no crash if used in DMs); stats/rosters refresh every 30 minutes instead of hourly.

- **`fantasy repair [banked]` (admin):** fixes leftovers from the stale-stats incident. Players added/traded/dropped while the bad numbers were live got inflated starting points (showing as huge *negative* FP) or inflated banked FP. `repair` lowers any impossible starting point to the player's current total; `repair banked` also zeroes banked FP, but only while no real stats exist yet.

- **Live scoring from box scores:** the season-stats table can keep serving last season's numbers for days after a new season opens (confirmed on opening night 2026-27), so nothing would score. The bot now also builds season totals directly from **finished regular-season games' box scores** (each game counted exactly once, preseason ignored, unfinished games ignored) and uses them whenever the stats table is stale or empty. Points land on the first refresh after ESPN posts a game's box score (every 30 min, or instantly with `update`).

- **Table + box scores never double count:** when both sources have data, each stat takes the *higher* of the two (never the sum). A correct table agrees with the box scores; a lagging table is filled in by box scores; a table that's ahead wins. Any individual player line identical to last season's totals is ignored even if the rest of the table has already switched to the new season.

---

# NBAdex Fantasy (`nbafantasy`)

An ESPN Fantasy-style NBA league that runs entirely in Discord — draft, free agency,
trades, positional lineups, customizable scoring, live NBA stats/injuries pulled from
ESPN, and a full admin toolkit. Revamped and verified ready for the **2026-27 NBA season**.

Load with `[p]load nbafantasy`, then `[p]fantasy setup` to turn it on for your server,
and `[p]fantasy guide` for the full in-Discord player guide.

---

## What changed in this revamp

### 🚨 Critical fix: player pool no longer depends on stats existing
The old code built its entire player list from ESPN's **season stats leaderboard**.
That meant before any games are played (preseason, or the first days of a new season),
the player pool would be **empty or nearly empty** — nobody could draft. This is the
kind of bug that would have made the cog unusable for the start of 2026-27.

Fixed: the player pool is now built from all 30 **team rosters** first (so every
active player is always available, stats or not), then season stats and injury
status are layered on top on a best-effort basis. If the stats or injuries fetch
fails or returns nothing, the roster-based player pool still works and every
player just starts at 0 FP — exactly correct for the start of a season.

A failed fetch of any kind now also **never wipes out** the previously cached
player pool — it just keeps last known-good data and retries later.

### Draft / Free Agency bugs fixed
- **Free agency now actually unlocks when the draft finishes** — including
  when it's stopped early with `draft stop`. Previously the bot announced
  "Free Agency is now open" but never flipped the lock, and stopping a draft
  early left it locked with no obvious way out.
- **Fixed a real concurrency bug in draft picks.** The old "commit roster,
  then separately commit draft state, then roll back if something looks off"
  approach had a window where a duplicate/retried click on the same pick
  could pop a *successfully* drafted player back off the roster while the
  pick history still recorded it as drafted — a permanent desync between
  "who owns this player" and "the draft record." The whole pick (turn check →
  already-drafted check → roster write → pick-advance) is now one atomic
  operation under a single lock. Verified with a concurrent-duplicate-click
  simulation.
- **Removing a manager mid-draft no longer skips turns.** The "on the clock"
  pointer is now recalculated correctly when someone is removed from the order.
- `[p]fantasy draft setup` now:
  - requires the league to be active first (clearer error instead of a broken draft state),
  - de-duplicates repeated mentions,
  - filters out bot accounts,
  - auto-creates a roster/score entry for every drafter so nobody has to remember
    to `[p]fantasy join` separately.
- Trades are now **blocked while a draft is in progress**, preventing roster
  corruption from a trade landing mid-draft.

### Embed crash bugs fixed (would 400 on larger leagues/rosters)
Discord embeds hard-cap at 25 fields and 1024 characters per field. Three
commands built one field per item with no cap, which works fine for a small
test league but throws an HTTP 400 and crashes the command outright with a
bigger one:
- `[p]fantasy team` — one field per roster slot + one per bench player.
- `[p]fantasy standings` — one field per manager.
- `[p]fantasy draft picks` — one field per ~15-20 picks of history.

All three now cap themselves defensively (showing a "+N more" note instead of
crashing), and fantasy-point totals are computed over the *full* data first
so the visible truncation never silently drops points from a total.

### Security fix
- **`[p]fantasy config channel` was not actually admin-gated.** Permission
  checks on a Group in discord.py/Red do *not* automatically cascade to its
  subcommands — every other subcommand in this cog (draft setup/start/stop,
  etc.) correctly had its own explicit admin check, but this one was missed,
  meaning any regular member could redirect or disable the transaction log
  channel. Fixed, then audited every command/subcommand in the file against
  this exact pattern to confirm nothing else was missed.

### Minor UX fix
- The reset confirmation buttons now clear the old "are you sure?" warning
  embed instead of leaving it stacked above the new confirmation text.

### Live fix: ESPN 403 on the team-roster endpoint
Reported live after deployment: `site.api.espn.com/apis/site/v2/.../teams`
started returning `403 Forbidden` on some hosting networks. This endpoint
didn't exist in the original cog — it was only added in this revamp to fix
the empty-preseason-pool bug — so it was a new single point of failure that
needed hardening. Fixed by:
- Trying `site.web.api.espn.com` (the host the stats calls already use
  successfully) *before* falling back to `site.api.espn.com`, since ESPN
  mirrors most `/apis/site/v2/...` paths on both hosts.
- Retrying transient 403/429/5xx responses with backoff before giving up.
- Adding real browser-style headers (`Referer`, `Origin`, `Accept-Language`)
  to every request, since some CDN/WAF layers flag requests missing these
  as bot traffic.
- Applying the same host-fallback treatment to the injuries endpoint too.

Verified with simulated failures: one host down → recovers via the other;
both hosts briefly failing → retries before falling through. The existing
"never wipe the cache on total failure" safety net still applies on top of
all of this if every attempt is exhausted.

### Branding: ESPN mentions removed from everything user-facing
- Every Discord-visible string (guide, status, embeds) no longer mentions
  "ESPN" — it's all just "NBAdex Fantasy" / "the stats provider" now.
- **Error messages no longer leak the data provider's URL into Discord.**
  This is exactly the bug from the live 403 report — the raw exception text
  (which included the full `site.api.espn.com/...` URL) was being posted
  straight into chat. A new sanitizer now turns that into a short, generic
  summary ("the stats provider returned an HTTP 403 error") for anything
  shown in Discord, while the full detail still goes to the console log for
  whoever hosts the bot.
- Internal method/variable names renamed to drop "espn" (`_current_season`,
  `_STATS_SITE_HOSTS`), and comments reworded to say "the stats provider."
- `info.json`'s tags and description no longer mention ESPN.

**One thing that can't change:** the actual HTTP requests still go to
`site.api.espn.com` / `site.web.api.espn.com`, because that's genuinely where
the real NBA rosters/stats/injuries come from — there's no way to fetch real
data without naming the real host in the request itself. Nobody using the
bot in Discord will ever see that, though.

### Permissions
- **`[p]fantasy settings` is now admin-only.** It was previously open to
  everyone, unlike every other settings-viewing/changing command in the cog.

### Roster / lineup bugs fixed
- **Slot overfill prevented.** You could previously assign more players to a
  slot label (e.g. a 4th player into a 3-slot UTIL) than the league allows; the
  slot picker now only offers slot types that actually have room.
- A full league reset now also unlocks Free Agency (previously a reset could
  leave FA stuck locked with no obvious way to unlock it).

### Reliability / UX fixes
- The ESPN injuries endpoint was called over plain `http://`, which some hosts
  block outright — switched to `https://`.
- Explicit `season`/`seasontype` parameters are now sent to ESPN, computed
  dynamically (an "August rollover" rule) so the cog automatically targets the
  **2026-27** season without needing a manual code change, and will keep
  rolling forward automatically in future years.
- The trade-accept flow now defers its interaction response before doing the
  heavier config writes + transaction log post, avoiding the "This interaction
  failed" Discord error under load.
- The HTTP session is now closed cleanly on cog unload.
- `[p]fantasy setslots` now caps at 15 slots and warns (without deleting data)
  if rosters or a draft already exist when slots are changed mid-season.

### New: Player headshots
Real NBA player photos now show up across the cog instead of plain text lists:
- `[p]fantasy player` lookup — big headshot of whichever player you select.
- `[p]fantasy team` — the large thumbnail is now your **top fantasy-point
  player's** photo (the manager's own Discord avatar moved to a small icon
  next to the title instead, so you still see whose team it is).
- `[p]fantasy freeagents`, `[p]fantasy player`, and `draft board` — the photo
  of whichever player is currently on top of the visible page, updating as
  you page through or search.
- `[p]fantasy standings` — the #1 manager's MVP player's photo.
- Every transaction log post (FA pickup, drop, draft pick, auto-draft pick,
  trade accepted) now shows that player's photo.
- Headshots come from the real photo ESPN's roster data provides when
  available, and otherwise fall back to the standard ESPN headshot CDN URL
  pattern, which covers virtually every active player.

### Reliability pass (full code review)
- **`[p]` prefix bug, fixed everywhere.** Every message the bot actually
  *sends* — guide, status, team, join, setup, setslots, freeagents, trade
  accept, newseason, draft setup/start — had the literal text `[p]` hardcoded
  instead of your server's real prefix. Discord doesn't substitute that on
  its own (only Red's help formatter does, for a command's docstring), so
  users were being told to run a command that starts with `[p]`, which
  doesn't exist. Every one of these now shows your actual prefix.
- **`draft start` no longer crashes** if you run it again after a draft has
  already finished (an unguarded index into the pick order caused this).
- **Auto-draft now survives a bot restart.** If the bot restarts mid-draft
  while an auto-draft manager is on the clock, a fresh cog load now checks
  every server's draft state and restarts auto-draft wherever it's needed,
  instead of leaving that manager waiting forever for something to nudge it.
- **Hardened the hourly stat refresh against partial failures**, so a bad
  fetch can no longer silently erase real data:
  - If some (not all) teams' roster calls fail, those teams' existing players
    are kept from the last good snapshot instead of ~15 players per failed
    team vanishing from the pool.
  - If the stats leaderboard call fails or returns something that looks
    wrong mid-season, last-known stats are carried forward instead of every
    player's FP getting zeroed for that refresh (which would have let
    someone bank a bogus "earned 0 FP" drop or start a new pickup at the
    wrong baseline).
  - Same idea for injuries: a failed injuries fetch keeps each player's last
    known status instead of clearing everyone's OUT flag.

### New: Auto-draft
- `[p]fantasy autodraft on|off|status` (alias `ad`) — any league member can turn
  it on. Whenever they're on the clock, the bot drafts the best available
  player who still fits their positional slots. Turning it **off** works at any
  time, including mid-draft, and takes effect immediately (even during the
  short pause before an auto-pick).
- Picks are announced as `🤖 Pick #N (auto-draft)` and logged to the
  transaction channel. The bot doesn't ping managers who are on auto-draft.
- Turning it on while it's already your turn triggers the pick right away.
- **How "best" is decided:** before the season every player has 0 current FP,
  so the ranking uses **last season's stats** (fetched once per season and
  kept); once games are played, whichever of current/last-season is higher
  wins. Players flagged **OUT** are marked down 60%. Rookies with no prior
  stats rank low until they produce. The draft board's sort order uses the
  same ranking, so it's useful in the preseason too.
- Auto-draft runs through the exact same atomic pick logic as manual picks, so
  turn order, duplicate protection and roster-fit rules are identical. If it
  can't find a valid player it switches itself off and tells the channel
  instead of stalling silently. `draft stop` halts it; `reset`/`newseason`
  and removing a manager clear the flag.
- Also fixed: `draft start` crashed with an IndexError if run again after a
  draft had already finished.

### New for the 2026-27 rollover
- **`[p]fantasy newseason`** (admin) — a season-flavored full reset that clears
  rosters/scores/draft history and reminds the bot owner to run
  `[p]fantasy update` once to pull the newest rosters before drafting.
- `[p]fantasy status` and `[p]fantasy update` now display the season label
  (e.g. "2026-27") so it's obvious which season's data is loaded.

### Branding
All player-facing text now consistently says **NBAdex Fantasy** (guide, status,
league messages, standings, `info.json`), while commands/aliases (`[p]fantasy`,
`[p]nbafantasy`, `[p]nbaf`) are unchanged so existing muscle memory still works.

---

## Command overview

| Category | Commands |
|---|---|
| Getting started | `[p]fantasy setup`, `[p]fantasy join`, `[p]fantasy guide`, `[p]fantasy status` |
| Draft | `[p]fantasy draft setup`, `draft start`, `draft board`, `draft picks`, `draft stop`, `[p]fantasy autodraft` |
| Free agency | `[p]fantasy freeagents` (`fa`), `[p]fantasy lock` / `unlock` |
| Team management | `[p]fantasy team [@member]`, drop/assign via dropdowns |
| Trading | `[p]fantasy trade` |
| Info | `[p]fantasy player`, `[p]fantasy standings`, `[p]fantasy settings` |
| Admin | `[p]fantasy setslots`, `setscoring`, `config channel`, `forceadd`, `forcedrop`, `remove`, `reset`, `newseason` |
| Owner-only | `[p]fantasy update` (refreshes the global player pool from ESPN) |

## Notes
- The player pool (`players_cache`) is global (shared across every server the
  bot is in) since it's just public NBA data; everything else (rosters, scores,
  draft state, settings) is per-server.
- Scoring is season-cumulative: you earn the fantasy points a player produces
  **while they're on your roster**, tracked via an FP baseline captured at
  add-time (draft pick, FA add, or trade).
