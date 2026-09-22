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
| Draft | `[p]fantasy draft setup`, `draft start`, `draft board`, `draft picks`, `draft stop` |
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
