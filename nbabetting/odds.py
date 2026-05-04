"""odds.py — Enhanced odds engine: real team stats, power ratings, vig variation,
ML-from-spread derivation, back-to-back detection, form weighting, line movement."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import aiohttp

# ── ESPN endpoints ────────────────────────────────────────────────────────────
ESPN_SCOREBOARD  = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_INJURIES    = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
ESPN_SUMMARY     = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"
ESPN_LEADERS     = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/leaders"
ESPN_TEAM_STATS    = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/statistics"
ESPN_TEAM_LEADERS  = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/leaders"
ESPN_TEAM_ROSTER   = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"

# ── Cache TTLs (seconds) ──────────────────────────────────────────────────────
GAMES_TTL        = 120     # 2 min
INJURIES_TTL     = 300     # 5 min
LEADERS_TTL      = 3600    # 1 hr
TEAM_STATS_TTL   = 21600   # 6 hrs  — scoring avgs barely shift day-to-day
YESTERDAY_TTL    = 3600    # 1 hr   — who played yesterday

# ── ESPN numeric team IDs (permanent, never change) ──────────────────────────
TEAM_IDS: Dict[str, int] = {
    "ATL": 1,  "BOS": 2,  "NOP": 3,  "CHI": 4,  "CLE": 5,
    "DAL": 6,  "DEN": 7,  "DET": 8,  "GSW": 9,  "HOU": 10,
    "IND": 11, "LAC": 12, "LAL": 13, "MIA": 14, "MIL": 15,
    "MIN": 16, "BKN": 17, "NYK": 18, "ORL": 19, "PHI": 20,
    "PHX": 21, "POR": 22, "SAC": 23, "SAS": 24, "OKC": 25,
    "UTA": 26, "WAS": 27, "TOR": 28, "MEM": 29, "CHA": 30,
}

# ── Moneyline lookup table derived from spread (NBA-calibrated) ───────────────
# (max_spread, fav_ml, dog_ml)  — nearest row for any spread value
_ML_TABLE: List[Tuple[float, int, int]] = [
    (0.5,  -115, +100),
    (1.0,  -120, +100),
    (1.5,  -130, +110),
    (2.0,  -140, +120),
    (2.5,  -150, +130),
    (3.0,  -165, +140),
    (3.5,  -180, +155),
    (4.0,  -195, +168),
    (4.5,  -210, +180),
    (5.0,  -225, +192),
    (5.5,  -240, +205),
    (6.0,  -258, +220),
    (6.5,  -275, +235),
    (7.0,  -295, +252),
    (7.5,  -318, +270),
    (8.0,  -342, +290),
    (8.5,  -368, +310),
    (9.0,  -395, +330),
    (9.5,  -425, +355),
    (10.0, -460, +380),
    (11.0, -520, +430),
    (12.0, -600, +480),
]

HOME_COURT_ADV = 2.0   # pts — modern NBA, down from historical 3


# ══════════════════════════════════════════════════════════════════════════════
# Small helpers
# ══════════════════════════════════════════════════════════════════════════════

def _parse_record(summary: str) -> Tuple[int, int]:
    try:
        w, l = summary.split("-")
        return int(w), int(l)
    except Exception:
        return 0, 0


def _win_pct(wins: int, losses: int) -> float:
    t = wins + losses
    return wins / t if t > 0 else 0.5


def _first(d: Dict, keys: List[str]) -> Optional[float]:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def _ml_from_spread(spread_abs: float) -> Tuple[int, int]:
    """Return (favourite_ml, underdog_ml) for a given absolute spread."""
    for threshold, fav, dog in _ML_TABLE:
        if spread_abs <= threshold:
            return fav, dog
    # Extrapolate beyond 12 pts
    extra = spread_abs - 12.0
    fav = -600 - int(extra * 50)
    dog = +480 + int(extra * 40)
    return fav, dog


def _spread_vig(spread_abs: float) -> Tuple[int, int]:
    """Spread juice: (fav_price, dog_price). NBA spreads are usually close to -110/-110."""
    if spread_abs <= 3.0:   return -110, -110
    if spread_abs <= 6.0:   return -112, -108
    if spread_abs <= 9.0:   return -115, -105
    return -118, -102


# ── Opening line tracking (in-memory, never overwritten after first set) ──────

_opening_lines: Dict[str, Dict[str, float]] = {}


def record_opening_line(event_id: str, spread: float, total: float) -> None:
    """Record the first computed spread/total for an event. Never updates after set."""
    if event_id not in _opening_lines:
        _opening_lines[event_id] = {"spread": spread, "total": total}


def get_opening_line(event_id: str) -> Optional[Dict[str, float]]:
    """Return the opening spread/total dict if we have seen this event before."""
    return _opening_lines.get(event_id)


# ── Parlay odds combiner ───────────────────────────────────────────────────────

def calc_parlay_odds(prices: List[int]) -> int:
    """
    Convert a list of American odds into combined parlay odds.
    Each price is converted to a decimal multiplier, multiplied together,
    then converted back to American.

    Examples:
        [-110, -110]        → +264  (2-team parlay, standard juice)
        [-110, -110, -110]  → +596  (3-team parlay)
        [-150, +130, -110]  → approximately +350
    """
    if not prices:
        return -110
    if len(prices) == 1:
        return prices[0]
    decimal = 1.0
    for p in prices:
        if p >= 0:
            decimal *= (p / 100.0) + 1.0
        else:
            decimal *= (100.0 / abs(p)) + 1.0
    if decimal >= 2.0:
        return int(round((decimal - 1.0) * 100))
    return int(round(-100.0 / (decimal - 1.0)))


# ── Prop juice engine ─────────────────────────────────────────────────────────

def _prop_juice(tier: int, is_questionable: bool = False) -> Tuple[int, int]:
    """
    Return (over_price, under_price) for a player prop.

    Real bookmakers shade props based on:
    - Stars attract massive public over action → over is more expensive
    - Questionable players → wider spread (uncertainty premium)
    - Bench players → near-standard juice
    """
    if is_questionable:
        if tier == 1:
            return (-108, -112)   # star questionable: slight under-juice edge
        return (-105, -115)       # role player questionable: under is the sharper side
    if tier == 1:
        return (-118, +100)       # public hammers star overs — charge extra vig
    if tier == 2:
        return (-115, -105)       # rotation players: mild public over lean
    return (-110, -110)           # bench: standard flat juice


# ── Public-action vig boost ───────────────────────────────────────────────────

def _public_vig_boost(pct_on_popular_side: float) -> int:
    """
    Extra juice (pts magnitude) charged to the popular side.
    When 65%+ of server money is on one side, the book shades the price.
    Returns a non-negative int to ADD to the popular side's juice magnitude.
    """
    if pct_on_popular_side >= 0.82:
        return 12
    if pct_on_popular_side >= 0.74:
        return 8
    if pct_on_popular_side >= 0.65:
        return 4
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# Power rating
# ══════════════════════════════════════════════════════════════════════════════

def _power_rating(
    wins: int,
    losses: int,
    last10_wins: int,
    home_wins: int,
    home_losses: int,
    away_wins: int,
    away_losses: int,
    is_home: bool,
) -> float:
    """
    Weighted composite win probability:
      50% season record + 30% last-10 form + 20% home/away venue record.
    Returns a value in [0.05, 0.95].
    """
    season_pct = _win_pct(wins, losses)
    last10_pct = last10_wins / 10.0

    if is_home:
        venue_pct = (
            _win_pct(home_wins, home_losses)
            if (home_wins + home_losses) >= 5
            else season_pct
        )
    else:
        venue_pct = (
            _win_pct(away_wins, away_losses)
            if (away_wins + away_losses) >= 5
            else season_pct
        )

    rating = season_pct * 0.50 + last10_pct * 0.30 + venue_pct * 0.20
    return max(0.05, min(0.95, rating))


# ══════════════════════════════════════════════════════════════════════════════
# Injury impact
# ══════════════════════════════════════════════════════════════════════════════

_OUT_IMPACT         = {1: 3.5,  2: 1.5,  3: 0.5}
_DOUBTFUL_IMPACT    = {1: 2.0,  2: 0.75, 3: 0.25}
_QUESTIONABLE_IMPACT= {1: 0.75, 2: 0.25, 3: 0.0}
_IMPACTFUL_STATUSES = {"out", "doubtful", "questionable"}


def _player_tier(pts_avg: float) -> int:
    if pts_avg >= 20: return 1
    if pts_avg >= 12: return 2
    return 3


def _injury_shift(
    abbr: str,
    injuries: Dict[str, List[Dict]],
    stat_leaders: Dict[str, Dict],
) -> Tuple[float, List[str]]:
    """Return (pts_to_shift, [display_notes])."""
    team_injuries = injuries.get(abbr, [])
    if not team_injuries:
        return 0.0, []

    team_pts: Dict[str, float] = {
        name.lower(): info["pts"]
        for name, info in stat_leaders.items()
        if info.get("team_abbr") == abbr
    }

    shift = 0.0
    notes: List[str] = []
    emoji_map = {"out": "🚫", "doubtful": "⚠️", "questionable": "❓"}

    for inj in team_injuries:
        status = inj.get("status", "").lower()
        if status not in _IMPACTFUL_STATUSES:
            continue
        name = inj.get("name", "")
        pts  = team_pts.get(name.lower(), 0.0)
        if pts == 0.0:
            continue
        tier = _player_tier(pts)
        if status == "out":
            shift += _OUT_IMPACT.get(tier, 0.5)
        elif status == "doubtful":
            shift += _DOUBTFUL_IMPACT.get(tier, 0.25)
        else:
            shift += _QUESTIONABLE_IMPACT.get(tier, 0.0)
        notes.append(f"{emoji_map[status]} **{name}** ({abbr}) — {inj['status']}")

    return shift, notes


# ══════════════════════════════════════════════════════════════════════════════
# Line movement from bet distribution
# ══════════════════════════════════════════════════════════════════════════════

def _line_movement(
    home_team: str,
    away_team: str,
    bet_dist: Dict[str, float],
) -> Tuple[float, float]:
    """
    Given the total money wagered on each side (from the server's bets),
    return (spread_shift, total_shift).

    spread_shift > 0  → home getting heavier action → shift line against home
                        (make home more expensive, reduce underdog price)
    total_shift  > 0  → Over getting heavier action → bump total up
    """
    # ── Spread / moneyline side action ───────────────────────────────────────
    home_money = bet_dist.get(home_team, 0.0)
    away_money = bet_dist.get(away_team, 0.0)
    h2h_total  = home_money + away_money

    spread_shift = 0.0
    if h2h_total >= 100:   # need meaningful volume
        home_pct = home_money / h2h_total
        if home_pct >= 0.80:
            spread_shift = 1.5
        elif home_pct >= 0.70:
            spread_shift = 1.0
        elif home_pct >= 0.60:
            spread_shift = 0.5
        elif home_pct <= 0.20:
            spread_shift = -1.5
        elif home_pct <= 0.30:
            spread_shift = -1.0
        elif home_pct <= 0.40:
            spread_shift = -0.5

    # ── Totals side action ────────────────────────────────────────────────────
    over_money  = bet_dist.get("Over",  0.0)
    under_money = bet_dist.get("Under", 0.0)
    ou_total    = over_money + under_money

    total_shift = 0.0
    if ou_total >= 100:
        over_pct = over_money / ou_total
        if over_pct >= 0.80:
            total_shift = 1.0
        elif over_pct >= 0.70:
            total_shift = 0.5
        elif over_pct <= 0.20:
            total_shift = -1.0
        elif over_pct <= 0.30:
            total_shift = -0.5

    return spread_shift, total_shift


# ══════════════════════════════════════════════════════════════════════════════
# Core odds generation
# ══════════════════════════════════════════════════════════════════════════════

def generate_odds_for_game(
    game: Dict,
    injuries:       Optional[Dict[str, List[Dict]]] = None,
    stat_leaders:   Optional[Dict[str, Dict]]       = None,
    home_ts:        Optional[Dict]                  = None,
    away_ts:        Optional[Dict]                  = None,
    bet_dist:       Optional[Dict[str, float]]      = None,
) -> Dict[str, Any]:
    """
    Produce h2h / spreads / totals with:
     - Real team ppg/papg from ESPN stats (if available)
     - Power rating (season + last-10 + venue record)
     - Back-to-back penalty
     - Injury adjustment
     - Line movement from server bet volume
     - Spread-derived moneyline (not flat win%)
     - Spread-appropriate vig
    """
    injuries     = injuries     or {}
    stat_leaders = stat_leaders or {}
    home_ts      = home_ts      or {}
    away_ts      = away_ts      or {}
    bet_dist     = bet_dist     or {}

    home_team  = game["home_team"]
    away_team  = game["away_team"]
    home_abbr  = game.get("home_abbr", "")
    away_abbr  = game.get("away_abbr", "")

    # ── Parse records from game ───────────────────────────────────────────────
    hw,  hl  = _parse_record(game.get("home_record",       "0-0"))
    aw,  al  = _parse_record(game.get("away_record",       "0-0"))
    hh_w, hh_l = _parse_record(game.get("home_home_record","0-0"))
    ar_w, ar_l = _parse_record(game.get("away_road_record","0-0"))
    h_l10w = game.get("home_last10_wins", 5)
    a_l10w = game.get("away_last10_wins", 5)

    # ── Power ratings ─────────────────────────────────────────────────────────
    h_power = _power_rating(hw, hl, h_l10w, hh_w, hh_l, 0, 0, is_home=True)
    a_power = _power_rating(aw, al, a_l10w, 0, 0, ar_w, ar_l, is_home=False)

    # ── Spread from real scoring data (preferred) or power rating (fallback) ──
    h_ppg  = home_ts.get("ppg")
    h_papg = home_ts.get("papg")
    a_ppg  = away_ts.get("ppg")
    a_papg = away_ts.get("papg")

    if h_ppg and h_papg and a_ppg and a_papg:
        # Vegas-style power rating: avg of team's offence vs opponent's defence
        h_expected = (h_ppg + a_papg) / 2
        a_expected = (a_ppg + h_papg) / 2
        raw_spread = h_expected - a_expected + HOME_COURT_ADV
    else:
        # Fallback: pure win-percentage spread (~4% win-pct gap per point)
        raw_spread = (h_power - a_power) * 25 + HOME_COURT_ADV

    # ── Back-to-back penalty (-2.5 pts for team on B2B) ──────────────────────
    if home_ts.get("is_back_to_back"):
        raw_spread -= 2.5
    if away_ts.get("is_back_to_back"):
        raw_spread += 2.5

    # ── Injury adjustment ─────────────────────────────────────────────────────
    h_inj_shift, h_notes = _injury_shift(home_abbr, injuries, stat_leaders)
    a_inj_shift, a_notes = _injury_shift(away_abbr, injuries, stat_leaders)
    injury_notes = h_notes + a_notes
    raw_spread  -= h_inj_shift
    raw_spread  += a_inj_shift

    # ── Line movement ─────────────────────────────────────────────────────────
    spread_mv, total_mv = _line_movement(home_team, away_team, bet_dist)
    raw_spread += spread_mv   # positive = home favoured more → home side more expensive

    # ── Round to nearest 0.5, clamp ──────────────────────────────────────────
    spread = round(raw_spread * 2) / 2
    spread = max(-24.0, min(24.0, spread))

    # ── Moneyline derived from spread ─────────────────────────────────────────
    spread_abs = abs(spread)
    fav_ml, dog_ml = _ml_from_spread(spread_abs)

    if spread >= 0:   # home is favourite (or PK)
        h_ml, a_ml = fav_ml, dog_ml
    else:             # away is favourite
        h_ml, a_ml = dog_ml, fav_ml

    if spread_abs < 0.5:  # pick'em
        h_ml = a_ml = -110

    # ── Public action vig boost ───────────────────────────────────────────────
    # When the server's bettors heavily lean one side, charge that side extra vig
    h2h_money = bet_dist.get(home_team, 0.0) + bet_dist.get(away_team, 0.0)
    if h2h_money >= 50:
        home_pct = bet_dist.get(home_team, 0.0) / h2h_money
        away_pct = 1.0 - home_pct
        if home_pct >= 0.65:
            h_ml -= _public_vig_boost(home_pct)
        elif away_pct >= 0.65:
            a_ml -= _public_vig_boost(away_pct)

    # ── Total ─────────────────────────────────────────────────────────────────
    if h_ppg and h_papg and a_ppg and a_papg:
        h_expected = (h_ppg + a_papg) / 2
        a_expected = (a_ppg + h_papg) / 2
        base_total = h_expected + a_expected
    else:
        base_total = 225.0 + (h_power + a_power - 1.0) * 10

    # Back-to-back teams score fewer points
    if home_ts.get("is_back_to_back"):
        base_total -= 2.0
    if away_ts.get("is_back_to_back"):
        base_total -= 2.0

    # Injury total impact
    base_total -= (h_inj_shift + a_inj_shift) * 2.5

    # Line movement
    base_total += total_mv

    total = round(base_total * 2) / 2

    # ── Spread vig ────────────────────────────────────────────────────────────
    fav_price, dog_price = _spread_vig(spread_abs)
    if spread >= 0:
        h_spread_price, a_spread_price = fav_price, dog_price
    else:
        h_spread_price, a_spread_price = dog_price, fav_price

    # ── Totals juice (varies with public action) ──────────────────────────────
    over_price  = -110
    under_price = -110
    ou_money = bet_dist.get("Over", 0.0) + bet_dist.get("Under", 0.0)
    if ou_money >= 50:
        over_pct  = bet_dist.get("Over",  0.0) / ou_money
        under_pct = 1.0 - over_pct
        if over_pct >= 0.65:
            boost       = _public_vig_boost(over_pct)
            over_price  -= boost
            under_price  = min(under_price + boost - 2, -102)
        elif under_pct >= 0.65:
            boost       = _public_vig_boost(under_pct)
            under_price -= boost
            over_price   = min(over_price + boost - 2, -102)

    # ── Record opening line & compute movement ────────────────────────────────
    record_opening_line(game["event_id"], spread, total)
    opening        = get_opening_line(game["event_id"]) or {}
    opening_spread = opening.get("spread", spread)
    opening_total  = opening.get("total",  total)

    # ── Line movement note ────────────────────────────────────────────────────
    if abs(spread_mv) >= 0.5 or abs(total_mv) >= 0.5:
        injury_notes.append("📊 Line has moved due to betting action on this server.")

    return {
        "h2h": {
            home_team: h_ml,
            away_team: a_ml,
        },
        "spreads": {
            home_team: {"price": h_spread_price, "point": -spread},
            away_team: {"price": a_spread_price, "point":  spread},
        },
        "totals": {
            "Over":  {"price": over_price,  "point": total},
            "Under": {"price": under_price, "point": total},
        },
        "injury_notes": injury_notes,
        "_meta": {
            "spread":           spread,
            "total":            total,
            "opening_spread":   opening_spread,
            "opening_total":    opening_total,
            "spread_move":      round(spread - opening_spread, 1),
            "total_move":       round(total  - opening_total,  1),
            "h_power":          round(h_power, 3),
            "a_power":          round(a_power, 3),
            "h_back_to_back":   home_ts.get("is_back_to_back", False),
            "a_back_to_back":   away_ts.get("is_back_to_back", False),
            "spread_moved":     spread_mv,
            "total_moved":      total_mv,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# Player props
# ══════════════════════════════════════════════════════════════════════════════

def generate_player_props_for_game(
    game: Dict,
    props_pool: Dict[str, Dict],
    questionable_players: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Build player prop over/under lines for every available player.

    props_pool keys: {player_name: {pts, reb, ast, pra, tier, team_abbr}}

    Line logic:
    - Star players (tier 1, pts >= 20):  line = avg - 0.5, rounded to nearest 0.5
    - Rotation players (tier 2, pts >= 12): same formula
    - Bench players (tier 3 / pts < 12): minimum lines set (pts 7.5, reb 3.5, ast 1.5)
      so betting is still meaningful rather than on trivially small numbers.

    Players with completely zero stats AND not in the game summary are skipped —
    they are likely two-way / G-League call-ups with no ESPN data.
    """
    props: Dict[str, Any] = {}
    home_abbr = game.get("home_abbr", "")
    away_abbr = game.get("away_abbr", "")

    def _line(val: float, offset: float = -0.5) -> float:
        """Round to nearest 0.5 with the given offset."""
        return round((val + offset) * 2) / 2

    def _bench_line(val: float, minimum: float, offset: float = -0.5) -> float:
        raw = _line(val, offset)
        return max(raw, minimum)

    for pname, pdata in props_pool.items():
        if pdata.get("team_abbr", "") not in (home_abbr, away_abbr):
            continue

        pts  = float(pdata.get("pts", 0.0))
        reb  = float(pdata.get("reb", 0.0))
        ast  = float(pdata.get("ast", 0.0))
        pra  = pts + reb + ast
        tier = _player_tier(pts)

        # Skip players with no stats at all (truly unknown bench players)
        if pts == 0.0 and reb == 0.0 and ast == 0.0:
            continue

        if tier == 3:
            # Bench players: enforce minimum lines so bets are meaningful
            pts_line = _bench_line(pts, 7.5)
            reb_line = _bench_line(reb, 3.5)
            ast_line = _bench_line(ast, 1.5)
            pra_line = _bench_line(pra, 13.5, -1.0)
        else:
            pts_line = _line(pts)
            reb_line = _line(reb)
            ast_line = _line(ast)
            pra_line = _line(pra, -1.0)

        is_questionable = pname in (questionable_players or set())
        over_p, under_p = _prop_juice(tier, is_questionable)

        props[pname] = {
            "pts":        pts_line,
            "pts_over":   over_p,
            "pts_under":  under_p,
            "reb":        reb_line,
            "reb_over":   over_p,
            "reb_under":  under_p,
            "ast":        ast_line,
            "ast_over":   over_p,
            "ast_under":  under_p,
            "pra":        pra_line,
            "pra_over":   over_p,
            "pra_under":  under_p,
            "team_abbr":  pdata.get("team_abbr", ""),
            "tier":       tier,
            "status":     "questionable" if is_questionable else "active",
        }

    return props


# ══════════════════════════════════════════════════════════════════════════════
# ESPN event parser (updated: home/away/last-10 records)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_record_by_type(records: List[Dict], *type_names: str) -> str:
    for r in records:
        if r.get("type") in type_names or r.get("name", "").lower() in type_names:
            return r.get("summary", "0-0")
    return "0-0"


def _parse_espn_event(event: Dict) -> Optional[Dict]:
    try:
        comp        = event["competitions"][0]
        competitors = comp["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")

        status_obj = event["status"]["type"]
        completed  = status_obj.get("completed", False)
        state      = status_obj.get("name", "")

        home_score = away_score = None
        if completed or state == "STATUS_IN_PROGRESS":
            try:
                home_score = int(home.get("score") or 0)
                away_score = int(away.get("score") or 0)
            except (TypeError, ValueError):
                pass

        h_records = home.get("records", [])
        a_records = away.get("records", [])

        # Overall record
        home_record = _parse_record_by_type(h_records, "total", "overall")
        away_record = _parse_record_by_type(a_records, "total", "overall")

        # Home/away venue records
        home_home_record = _parse_record_by_type(h_records, "home")
        away_road_record = _parse_record_by_type(a_records, "road", "away")

        # Last-10 records
        h_last10 = _parse_record_by_type(h_records, "lastTen", "last-10", "l10")
        a_last10 = _parse_record_by_type(a_records, "lastTen", "last-10", "l10")
        h_l10_wins, _ = _parse_record(h_last10)
        a_l10_wins, _ = _parse_record(a_last10)

        return {
            "event_id":            event["id"],
            "name":                event.get("name", ""),
            "short_name":          event.get("shortName", ""),
            "commence_time":       event.get("date", ""),
            "home_team":           home["team"]["displayName"],
            "away_team":           away["team"]["displayName"],
            "home_abbr":           home["team"].get("abbreviation", "").upper(),
            "away_abbr":           away["team"].get("abbreviation", "").upper(),
            "home_record":         home_record,
            "away_record":         away_record,
            "home_home_record":    home_home_record,
            "away_road_record":    away_road_record,
            "home_last10_wins":    h_l10_wins,
            "away_last10_wins":    a_l10_wins,
            "completed":           completed,
            "state":               state,
            "home_score":          home_score,
            "away_score":          away_score,
        }
    except (KeyError, IndexError, StopIteration, TypeError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# ESPN Fetcher
# ══════════════════════════════════════════════════════════════════════════════

class OddsFetcher:
    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None

        self._games_cache:      List[Dict] = []
        self._games_ts:         float = 0.0

        self._injuries_cache:   Dict[str, List[Dict]] = {}
        self._injuries_ts:      float = 0.0

        self._leaders_cache:    Dict[str, Dict] = {}
        self._leaders_ts:       float = 0.0

        # Per-team scoring stats cache: {abbr: {ppg, papg, ...}}
        self._team_stats_cache: Dict[str, Dict] = {}
        self._team_stats_ts:    Dict[str, float] = {}

        # Per-team roster cache: {abbr: {player_name: status_str}}
        self._team_roster_cache: Dict[str, Dict] = {}
        self._team_roster_ts:    Dict[str, float] = {}

        # Per-game summary roster cache: {event_id: {player_name: {pts,reb,ast,pra,team_abbr,available}}}
        self._summary_roster_cache: Dict[str, Dict] = {}
        self._summary_roster_ts:    Dict[str, float] = {}

        # Set of team abbrs that played yesterday (for B2B detection)
        self._played_yesterday: Set[str] = set()
        self._played_yesterday_ts: float = 0.0

    # ── Session ───────────────────────────────────────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── Team stats ────────────────────────────────────────────────────────────

    async def get_team_stats(self, abbr: str) -> Dict:
        """
        Fetch season averages for a team from ESPN.
        Returns {ppg, papg, off_rtg, def_rtg, is_back_to_back}.
        Falls back to empty dict on failure — caller uses win-pct path.
        """
        now = time.monotonic()
        if (
            abbr in self._team_stats_cache
            and now - self._team_stats_ts.get(abbr, 0) < TEAM_STATS_TTL
        ):
            ts = self._team_stats_cache[abbr]
            # B2B is time-sensitive — refresh regardless of TTL
            ts["is_back_to_back"] = abbr in await self._get_played_yesterday()
            return ts

        team_id = TEAM_IDS.get(abbr)
        if not team_id:
            return {}

        session = await self._get_session()
        stats: Dict = {}
        try:
            url = ESPN_TEAM_STATS.format(team_id=team_id)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json(content_type=None)

            # Try multiple response shapes ESPN uses
            raw: List[Dict] = []

            # Shape 1: data["results"]["stats"]["categories"][n]["stats"]
            cats = (
                data.get("results", {})
                    .get("stats", {})
                    .get("categories", [])
            )
            for cat in cats:
                raw.extend(cat.get("stats", []))

            # Shape 2: data["statistics"]["categories"][n]["stats"]
            if not raw:
                cats2 = data.get("statistics", {}).get("categories", [])
                for cat in cats2:
                    raw.extend(cat.get("stats", []))

            # Shape 3: flat data["statistics"] list
            if not raw:
                flat = data.get("statistics", [])
                if isinstance(flat, list):
                    raw = flat

            stat_map: Dict[str, float] = {}
            for item in raw:
                name = (item.get("name") or "").lower()
                try:
                    val = float(item.get("value", 0))
                except (TypeError, ValueError):
                    continue
                stat_map[name] = val

            ppg  = _first(stat_map, ["avgpoints",  "pointspergame",      "points"])
            papg = _first(stat_map, ["avgpointsallowed", "pointsallowedpergame"])
            offr = _first(stat_map, ["offensiverating", "offrtg", "offeff"])
            defr = _first(stat_map, ["defensiverating", "defrtg", "defeff"])

            if ppg is not None:
                stats["ppg"]  = ppg
            if papg is not None:
                stats["papg"] = papg
            if offr is not None:
                stats["off_rtg"] = offr
            if defr is not None:
                stats["def_rtg"] = defr

        except Exception:
            pass

        stats["is_back_to_back"] = abbr in await self._get_played_yesterday()
        self._team_stats_cache[abbr] = stats
        self._team_stats_ts[abbr]    = now
        return stats

    # ── Back-to-back detection ────────────────────────────────────────────────

    async def _get_played_yesterday(self) -> Set[str]:
        """Return set of team abbrs that had a game yesterday."""
        now = time.monotonic()
        if self._played_yesterday and now - self._played_yesterday_ts < YESTERDAY_TTL:
            return self._played_yesterday

        yesterday = (
            datetime.now(timezone.utc) - timedelta(days=1)
        ).strftime("%Y%m%d")
        session = await self._get_session()
        played: Set[str] = set()

        try:
            async with session.get(
                ESPN_SCOREBOARD,
                params={"dates": yesterday, "limit": 20},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    for event in data.get("events", []):
                        g = _parse_espn_event(event)
                        if g:
                            played.add(g["home_abbr"])
                            played.add(g["away_abbr"])
        except Exception:
            pass

        self._played_yesterday    = played
        self._played_yesterday_ts = now
        return played

    # ── Per-team roster (availability) ───────────────────────────────────────

    async def get_team_roster(self, abbr: str) -> Dict[str, str]:
        """
        Fetch the full active roster for a team from ESPN.
        Returns {player_name: status} where status is lowercase e.g. "active", "out",
        "questionable", "doubtful", "day-to-day", "inactive".
        Used to know every player on the team and filter unavailable ones.
        """
        now = time.monotonic()
        if (
            abbr in self._team_roster_cache
            and now - self._team_roster_ts.get(abbr, 0) < LEADERS_TTL
        ):
            return self._team_roster_cache[abbr]

        team_id = TEAM_IDS.get(abbr)
        if not team_id:
            return {}

        session  = await self._get_session()
        result: Dict[str, str] = {}

        try:
            url = ESPN_TEAM_ROSTER.format(team_id=team_id)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json(content_type=None)

            # ESPN roster: top-level "athletes" can be:
            #   (a) flat list of athlete dicts, OR
            #   (b) list of position-group dicts each with "items" list
            raw_athletes: List[Dict] = []
            for item in data.get("athletes", []):
                if "items" in item:
                    raw_athletes.extend(item["items"])
                elif "displayName" in item or "fullName" in item:
                    raw_athletes.append(item)

            for athlete in raw_athletes:
                pname = athlete.get("displayName") or athlete.get("fullName", "")
                if not pname:
                    continue

                # Determine availability status
                # injuries is a list; if empty or first entry is "Active" → active
                injuries = athlete.get("injuries", [])
                if not injuries:
                    status = "active"
                else:
                    raw_status = (injuries[0].get("status", "") or "").lower()
                    # Normalise ESPN status strings
                    if raw_status in ("", "active"):
                        status = "active"
                    elif "out" in raw_status:
                        status = "out"
                    elif "questionable" in raw_status:
                        status = "questionable"
                    elif "doubtful" in raw_status:
                        status = "doubtful"
                    elif "day" in raw_status:
                        status = "day-to-day"
                    elif "inactive" in raw_status or "suspension" in raw_status:
                        status = "inactive"
                    else:
                        status = "active"

                result[pname] = status

        except Exception:
            pass

        if result:
            self._team_roster_cache[abbr] = result
            self._team_roster_ts[abbr]    = now
        return result

    # ── Per-game summary roster (player stats from ESPN pre-game data) ─────────

    async def _parse_summary_roster(
        self, event_id: str, home_abbr: str, away_abbr: str
    ) -> Dict[str, Dict]:
        """
        Parse the ESPN game summary's 'rosters' section.
        Returns {player_name: {pts, reb, ast, pra, tier, team_abbr, available}}.
        ESPN pre-game summaries include every expected player with season averages
        and their game-day availability status.
        Falls back to empty dict if the section is missing or the call fails.
        """
        now = time.monotonic()
        if (
            event_id in self._summary_roster_cache
            and now - self._summary_roster_ts.get(event_id, 0) < LEADERS_TTL
        ):
            return self._summary_roster_cache[event_id]

        session = await self._get_session()
        result: Dict[str, Dict] = {}
        valid_abbrs = {home_abbr, away_abbr}

        # ESPN stat name → our internal key
        stat_name_map: Dict[str, str] = {
            "avgpoints":    "pts", "points":    "pts", "pointspergame":    "pts",
            "avgrebounds":  "reb", "rebounds":  "reb", "reboundspergame":  "reb",
            "avgassists":   "ast", "assists":   "ast", "assistspergame":   "ast",
            "ppg": "pts", "rpg": "reb", "apg": "ast",
        }

        def _extract_stats(athlete: Dict) -> Dict[str, float]:
            """Walk the nested statistics tree ESPN uses."""
            out: Dict[str, float] = {"pts": 0.0, "reb": 0.0, "ast": 0.0}
            stats_obj = athlete.get("statistics") or {}
            splits    = stats_obj.get("splits") or {}
            categories = splits.get("categories") or []
            for cat in categories:
                for s in cat.get("stats") or []:
                    sname = (s.get("name") or "").lower().replace(" ", "").replace("_", "")
                    skey  = stat_name_map.get(sname)
                    if skey and s.get("value") is not None:
                        try:
                            out[skey] = float(s["value"])
                        except (TypeError, ValueError):
                            pass
            return out

        try:
            async with session.get(
                ESPN_SUMMARY,
                params={"event": event_id},
                timeout=aiohttp.ClientTimeout(total=12),
            ) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json(content_type=None)

            for team_block in data.get("rosters", []):
                team_abbr = (
                    team_block.get("team", {}).get("abbreviation", "")
                    or team_block.get("team", {}).get("abbrev", "")
                ).upper()
                if team_abbr not in valid_abbrs:
                    continue

                for entry in team_block.get("roster") or []:
                    athlete = entry.get("athlete") or {}
                    pname   = athlete.get("displayName") or athlete.get("fullName", "")
                    if not pname:
                        continue

                    # Availability
                    did_not_play = entry.get("didNotPlay", False)
                    status_name  = (
                        (entry.get("status") or {})
                        .get("type", {})
                        .get("name", "")
                    ).lower()
                    available = (
                        not did_not_play
                        and status_name not in ("inactive", "out", "suspended")
                    )

                    stats = _extract_stats(athlete)
                    pts, reb, ast = stats["pts"], stats["reb"], stats["ast"]
                    pra   = pts + reb + ast
                    tier  = _player_tier(pts)

                    result[pname] = {
                        "pts":       pts,
                        "reb":       reb,
                        "ast":       ast,
                        "pra":       pra,
                        "tier":      tier,
                        "team_abbr": team_abbr,
                        "available": available,
                    }

        except Exception:
            pass

        if result:
            self._summary_roster_cache[event_id] = result
            self._summary_roster_ts[event_id]    = now
        return result

    # ── Season stat leaders ───────────────────────────────────────────────────

    async def get_stat_leaders(self, force: bool = False) -> Dict[str, Dict]:
        """
        Fetch season stat leaders from ESPN with a high limit (500).
        Tries multiple paths to extract team abbreviation from each athlete entry.
        """
        now = time.monotonic()
        if not force and self._leaders_cache and now - self._leaders_ts < LEADERS_TTL:
            return self._leaders_cache

        session = await self._get_session()
        merged: Dict[str, Dict] = {}

        # ESPN uses different category names depending on endpoint version
        category_key_map = {
            "pointspergame":   "pts",
            "reboundspergame": "reb",
            "assistspergame":  "ast",
            "points":          "pts",
            "rebounds":        "reb",
            "assists":         "ast",
            "scoring":         "pts",
            "ppg":             "pts",
            "rpg":             "reb",
            "apg":             "ast",
        }

        def _abbr_from_athlete(athlete: Dict) -> str:
            """Try every known path ESPN uses to store team abbreviation."""
            checks = [
                lambda a: a.get("team", {}).get("abbreviation", ""),
                lambda a: a.get("teamAbbrev", ""),
                lambda a: a.get("team", {}).get("abbrev", ""),
                lambda a: (a.get("team") or {}).get("shortDisplayName", ""),
                lambda a: a.get("teamShortName", ""),
            ]
            for fn in checks:
                try:
                    v = fn(athlete)
                    if v and len(v) <= 4:
                        return v.upper()
                except Exception:
                    pass
            return ""

        try:
            async with session.get(
                ESPN_LEADERS,
                params={"limit": 500},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return self._leaders_cache
                data = await resp.json(content_type=None)

            for category in data.get("leaders", []):
                cat_name = (
                    category.get("name", "")
                    or category.get("abbreviation", "")
                ).lower().replace(" ", "").replace("_", "")
                stat_key = category_key_map.get(cat_name)
                if not stat_key:
                    continue
                for entry in category.get("leaders", []):
                    try:
                        athlete    = entry["athlete"]
                        pname      = athlete.get("displayName", "") or athlete.get("fullName", "")
                        if not pname:
                            continue
                        team_abbr  = _abbr_from_athlete(athlete)
                        value      = float(entry.get("value", 0))
                    except (KeyError, TypeError, ValueError):
                        continue
                    if pname not in merged:
                        merged[pname] = {"pts": 0.0, "reb": 0.0, "ast": 0.0, "team_abbr": ""}
                    merged[pname][stat_key] = value
                    if team_abbr:
                        merged[pname]["team_abbr"] = team_abbr

            leaders: Dict[str, Dict] = {}
            for pname, d in merged.items():
                if d["pts"] == 0.0 and d["reb"] == 0.0 and d["ast"] == 0.0:
                    continue
                d["pra"]  = d["pts"] + d["reb"] + d["ast"]
                d["tier"] = _player_tier(d["pts"])
                leaders[pname] = d

            if leaders:
                self._leaders_cache = leaders
                self._leaders_ts    = now

        except Exception:
            pass

        return self._leaders_cache

    # ── Injury report ─────────────────────────────────────────────────────────

    async def get_injuries(self, force: bool = False) -> Dict[str, List[Dict]]:
        now = time.monotonic()
        if not force and self._injuries_cache and now - self._injuries_ts < INJURIES_TTL:
            return self._injuries_cache

        session = await self._get_session()
        result: Dict[str, List[Dict]] = {}

        try:
            async with session.get(
                ESPN_INJURIES,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return self._injuries_cache
                data = await resp.json(content_type=None)

            for team_entry in data.get("injuries", []):
                abbr    = team_entry.get("team", {}).get("abbreviation", "").upper()
                players = []
                for inj in team_entry.get("injuries", []):
                    athlete  = inj.get("athlete", {})
                    full_name = athlete.get("fullName", "")
                    status    = inj.get("status", "")
                    desc      = inj.get("longComment", inj.get("shortComment", ""))
                    if full_name and status:
                        players.append({"name": full_name, "status": status, "description": desc})
                if abbr and players:
                    result[abbr] = players

            self._injuries_cache = result
            self._injuries_ts    = now

        except Exception:
            pass

        return self._injuries_cache

    # ── Scoreboard ────────────────────────────────────────────────────────────

    async def get_games(self, force: bool = False) -> List[Dict]:
        now = time.monotonic()
        if not force and self._games_cache and now - self._games_ts < GAMES_TTL:
            return self._games_cache

        session = await self._get_session()
        games: List[Dict] = []
        seen: set = set()

        for delta in [0, 1]:
            date = (datetime.now(timezone.utc) + timedelta(days=delta)).strftime("%Y%m%d")
            try:
                async with session.get(
                    ESPN_SCOREBOARD,
                    params={"dates": date, "limit": 20},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    for event in data.get("events", []):
                        g = _parse_espn_event(event)
                        if g and g["event_id"] not in seen:
                            seen.add(g["event_id"])
                            games.append(g)
            except Exception:
                pass

        if games:
            self._games_cache = games
            self._games_ts    = now
        return self._games_cache

    async def get_completed_games(self, days_back: int = 2) -> List[Dict]:
        session = await self._get_session()
        games: List[Dict] = []
        seen: set = set()

        for delta in range(days_back + 1):
            date = (datetime.now(timezone.utc) - timedelta(days=delta)).strftime("%Y%m%d")
            try:
                async with session.get(
                    ESPN_SCOREBOARD,
                    params={"dates": date, "limit": 20},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    for event in data.get("events", []):
                        g = _parse_espn_event(event)
                        if g and g["event_id"] not in seen and g.get("completed"):
                            seen.add(g["event_id"])
                            games.append(g)
            except Exception:
                pass

        return games

    # ── Full game + odds ──────────────────────────────────────────────────────

    async def get_game_with_odds(
        self,
        event_id: str,
        guild_id: Optional[int] = None,
        bets_manager=None,
    ) -> Optional[Dict]:
        """
        Return game data merged with fully enhanced odds:
         - Injury-adjusted, power-rated, back-to-back-aware
         - Line movement applied if guild_id + bets_manager provided
        """
        games = await self.get_games()
        game  = next((g for g in games if g["event_id"] == event_id), None)
        if not game:
            return None

        home_abbr = game.get("home_abbr", "")
        away_abbr = game.get("away_abbr", "")

        # Fetch all data sources in parallel
        (
            injuries, stat_leaders,
            home_ts, away_ts,
            home_roster, away_roster,
            summary_roster,
        ) = await asyncio.gather(
            self.get_injuries(),
            self.get_stat_leaders(),
            self.get_team_stats(home_abbr),
            self.get_team_stats(away_abbr),
            self.get_team_roster(home_abbr),
            self.get_team_roster(away_abbr),
            self._parse_summary_roster(event_id, home_abbr, away_abbr),
        )

        # ── Build props player pool ────────────────────────────────────────────
        #
        # Priority (highest → lowest):
        #   1. ESPN game summary rosters  — game-specific players + season avgs
        #   2. Global stat leaders        — wide coverage, season avgs
        #   3. Team roster names          — guarantees every player appears
        #
        # Availability filter:
        #   - Players marked "out" or "inactive" in team roster are excluded.
        #   - Players marked unavailable in the game summary are also excluded.
        #   - Injured players from the injuries endpoint (status "out") are excluded.
        # ──────────────────────────────────────────────────────────────────────

        # Collect injury "out" names from the injuries report
        injury_out: set = set()
        for team_abbr_key in (home_abbr, away_abbr):
            for inj in injuries.get(team_abbr_key, []):
                if inj.get("status", "").lower() in ("out",):
                    injury_out.add(inj["name"])

        # Merge availability from team rosters
        combined_roster: Dict[str, str] = {}
        for pname, status in home_roster.items():
            combined_roster[pname] = status
        for pname, status in away_roster.items():
            combined_roster[pname] = status

        def _is_available(pname: str, summary_entry: Optional[Dict] = None) -> bool:
            if pname in injury_out:
                return False
            if summary_entry is not None and not summary_entry.get("available", True):
                return False
            roster_status = combined_roster.get(pname, "active")
            return roster_status not in ("out", "inactive")

        # Start with global leaders that belong to either team in this game
        props_pool: Dict[str, Dict] = {}

        for pname, pdata in stat_leaders.items():
            t = pdata.get("team_abbr", "")
            if t in (home_abbr, away_abbr):
                if _is_available(pname):
                    props_pool[pname] = dict(pdata)

        # Overlay/add from game summary (most authoritative for this specific game)
        for pname, sdata in summary_roster.items():
            if not _is_available(pname, sdata):
                continue
            if pname in props_pool:
                # Keep the higher stats (summary may have more recent data)
                ex = props_pool[pname]
                for key in ("pts", "reb", "ast", "pra"):
                    if sdata.get(key, 0) > ex.get(key, 0):
                        ex[key] = sdata[key]
                ex["tier"] = _player_tier(ex["pts"])
            else:
                props_pool[pname] = dict(sdata)

        # Fill in any roster player not yet in the pool with zero-stats placeholder
        # (they still appear as bettable — bench contribution bets are valid)
        for pname, status in combined_roster.items():
            if status in ("out", "inactive"):
                continue
            if pname in injury_out:
                continue
            if pname not in props_pool:
                # Determine team_abbr from which roster they're in
                t = home_abbr if pname in home_roster else away_abbr
                props_pool[pname] = {
                    "pts": 0.0, "reb": 0.0, "ast": 0.0, "pra": 0.0,
                    "tier": 3, "team_abbr": t,
                }

        # Line movement from server's bet volume (optional)
        bet_dist: Dict[str, float] = {}
        if guild_id is not None and bets_manager is not None:
            try:
                bet_dist = bets_manager.get_bet_distribution(guild_id, event_id)
            except Exception:
                pass

        # Build questionable/doubtful players set for prop juice shading
        questionable_players: Set[str] = set()
        for team_abbr_key in (home_abbr, away_abbr):
            for inj in injuries.get(team_abbr_key, []):
                if inj.get("status", "").lower() in ("questionable", "doubtful", "day-to-day"):
                    questionable_players.add(inj["name"])

        odds  = generate_odds_for_game(game, injuries, stat_leaders, home_ts, away_ts, bet_dist)
        props = generate_player_props_for_game(game, props_pool, questionable_players)

        # Build public betting action percentages for UI display
        h2h_money = bet_dist.get(game["home_team"], 0.0) + bet_dist.get(game["away_team"], 0.0)
        ou_money  = bet_dist.get("Over", 0.0) + bet_dist.get("Under", 0.0)
        public_action = {
            "h2h_total": int(h2h_money),
            "ou_total":  int(ou_money),
            "home_pct":  round(bet_dist.get(game["home_team"], 0.0) / h2h_money, 3) if h2h_money > 0 else 0.5,
            "away_pct":  round(bet_dist.get(game["away_team"], 0.0) / h2h_money, 3) if h2h_money > 0 else 0.5,
            "over_pct":  round(bet_dist.get("Over",  0.0) / ou_money, 3) if ou_money > 0 else 0.5,
            "under_pct": round(bet_dist.get("Under", 0.0) / ou_money, 3) if ou_money > 0 else 0.5,
        }

        return {**game, "odds": odds, "player_props": props, "public_action": public_action}

    # ── Box score ─────────────────────────────────────────────────────────────

    async def get_game_box_score(self, event_id: str) -> Optional[Dict[str, Dict]]:
        session = await self._get_session()
        try:
            async with session.get(
                ESPN_SUMMARY,
                params={"event": event_id},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)

            stat_map: Dict[str, Dict] = {}
            for team_block in data.get("boxscore", {}).get("players", []):
                for stat_group in team_block.get("statistics", []):
                    keys = stat_group.get("keys", [])
                    for athlete_entry in stat_group.get("athletes", []):
                        display_name = athlete_entry.get("athlete", {}).get("displayName", "")
                        raw_stats    = athlete_entry.get("stats", [])
                        if not display_name or not raw_stats:
                            continue
                        parsed: Dict[str, float] = {}
                        for key, val in zip(keys, raw_stats):
                            try:
                                parsed[key.lower()] = float(val)
                            except (ValueError, TypeError):
                                parsed[key.lower()] = 0.0
                        stat_map[display_name] = parsed

            return stat_map or None
        except Exception:
            return None


# ══════════════════════════════════════════════════════════════════════════════
# Utility functions
# ══════════════════════════════════════════════════════════════════════════════

def fmt_odds(american: int) -> str:
    return f"+{american}" if american > 0 else str(american)


def calc_profit(stake: float, american: int) -> float:
    if american > 0:
        return round(stake * (american / 100), 2)
    return round(stake * (100 / abs(american)), 2)


def implied_prob(american: int) -> float:
    if american > 0:
        return 100 / (american + 100)
    return abs(american) / (abs(american) + 100)


def fmt_prop_selection(selection: str) -> str:
    parts = selection.split("|")
    if len(parts) == 3:
        pname, stat, direction = parts
        stat_labels = {
            "pts": "Points", "reb": "Rebounds",
            "ast": "Assists", "pra": "Pts+Reb+Ast",
        }
        return f"{pname} — {stat_labels.get(stat, stat)} {direction}"
    return selection


def evaluate_bet(
    bet_type: str,
    selection: str,
    point: Optional[float],
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    player_stats: Optional[Dict[str, Dict]] = None,
) -> str:
    """Return 'won', 'lost', or 'push'."""

    if bet_type == "h2h":
        if home_score == away_score:
            return "push"
        winner = home_team if home_score > away_score else away_team
        return "won" if selection == winner else "lost"

    elif bet_type == "spreads":
        if point is None:
            return "lost"
        margin = (
            home_score - away_score if selection == home_team
            else away_score - home_score
        )
        covered = margin + point
        if covered > 0:  return "won"
        if covered < 0:  return "lost"
        return "push"

    elif bet_type == "totals":
        if point is None:
            return "lost"
        total = home_score + away_score
        if selection == "Over":
            if total > point:  return "won"
            if total < point:  return "lost"
            return "push"
        else:
            if total < point:  return "won"
            if total > point:  return "lost"
            return "push"

    elif bet_type == "player_props":
        if point is None or player_stats is None:
            return "push"
        parts = selection.split("|")
        if len(parts) != 3:
            return "push"
        pname, stat, direction = parts[0], parts[1], parts[2]
        pstat = player_stats.get(pname) or {}
        if stat == "pts":
            actual = _first(pstat, ["points", "pts"])
        elif stat == "reb":
            actual = _first(pstat, ["rebounds", "totalrebounds", "reb"])
        elif stat == "ast":
            actual = _first(pstat, ["assists", "ast"])
        elif stat == "pra":
            pts = _first(pstat, ["points",   "pts"])  or 0.0
            reb = _first(pstat, ["rebounds", "reb"])  or 0.0
            ast = _first(pstat, ["assists",  "ast"])  or 0.0
            actual = pts + reb + ast
        else:
            return "push"
        if actual is None:
            return "push"
        if direction == "Over":
            if actual > point:  return "won"
            if actual < point:  return "lost"
            return "push"
        else:
            if actual < point:  return "won"
            if actual > point:  return "lost"
            return "push"

    return "lost"
