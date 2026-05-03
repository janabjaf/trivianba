"""data.py – Persistent bet storage (per-guild JSON files)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from redbot.core.data_manager import cog_data_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BetsManager:
    """Per-guild JSON-backed bet storage with in-memory caching."""

    def __init__(self, cog) -> None:
        self._base: Path = cog_data_path(cog) / "bets"
        self._base.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict] = {}   # str(guild_id) -> {"active": {}, "settled": {}}

    # ── Internal ───────────────────────────────────────────────────────────────

    def _path(self, guild_id: int) -> Path:
        return self._base / f"{guild_id}.json"

    def _load(self, guild_id: int) -> Dict:
        gid = str(guild_id)
        if gid in self._cache:
            return self._cache[gid]
        path = self._path(guild_id)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {"active": {}, "settled": {}}
        else:
            data = {"active": {}, "settled": {}}
        self._cache[gid] = data
        return data

    def _save(self, guild_id: int) -> None:
        gid = str(guild_id)
        if gid not in self._cache:
            return
        path = self._path(guild_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._cache[gid], f, indent=2)

    # ── Public API ─────────────────────────────────────────────────────────────

    def place_bet(
        self,
        guild_id: int,
        user_id: int,
        *,
        event_id: str,
        home_team: str,
        away_team: str,
        game_name: str,
        commence_time: str,
        bet_type: str,
        selection: str,
        odds: int,
        point: Optional[float],
        stake: float,
        potential_payout: float,
    ) -> str:
        """Save a new bet and return its ID."""
        bet_id = str(uuid.uuid4())[:8].upper()
        data   = self._load(guild_id)
        data["active"][bet_id] = {
            "id":               bet_id,
            "guild_id":         str(guild_id),
            "user_id":          str(user_id),
            "event_id":         event_id,
            "home_team":        home_team,
            "away_team":        away_team,
            "game_name":        game_name,
            "commence_time":    commence_time,
            "bet_type":         bet_type,
            "selection":        selection,
            "odds":             odds,
            "point":            point,
            "stake":            stake,
            "potential_payout": potential_payout,
            "status":           "pending",
            "placed_at":        _now(),
            "settled_at":       None,
            "result":           None,
            "actual_payout":    None,
        }
        self._save(guild_id)
        return bet_id

    def get_user_bets(
        self,
        guild_id: int,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        data  = self._load(guild_id)
        uid   = str(user_id)
        bets: List[Dict] = []
        for pool in ("active", "settled"):
            for bet in data[pool].values():
                if bet["user_id"] == uid:
                    if status is None or bet["status"] == status:
                        bets.append(bet)
        bets.sort(key=lambda b: b["placed_at"], reverse=True)
        return bets[:limit]

    def get_all_pending(self, guild_id: int) -> List[Dict]:
        data = self._load(guild_id)
        return [b for b in data["active"].values() if b["status"] == "pending"]

    def get_bet(self, guild_id: int, bet_id: str) -> Optional[Dict]:
        data = self._load(guild_id)
        return data["active"].get(bet_id) or data["settled"].get(bet_id)

    def settle_bet(
        self,
        guild_id: int,
        bet_id: str,
        result: str,
        actual_payout: float,
    ) -> bool:
        data = self._load(guild_id)
        if bet_id not in data["active"]:
            return False
        bet                  = data["active"].pop(bet_id)
        bet["status"]        = result
        bet["result"]        = result
        bet["settled_at"]    = _now()
        bet["actual_payout"] = actual_payout
        data["settled"][bet_id] = bet
        self._save(guild_id)
        return True

    def clear_all_bets(self, guild_id: int) -> Tuple[int, List[Dict]]:
        """
        Wipe ALL active and settled bets for a guild.
        Returns (active_count, list_of_active_bets_for_refund).
        Call this before resetting balances so the caller can refund stakes.
        """
        data   = self._load(guild_id)
        active = list(data["active"].values())
        data["active"]   = {}
        data["settled"]  = {}
        self._save(guild_id)
        return len(active), active

    def get_bet_distribution(self, guild_id: int, event_id: str) -> Dict[str, float]:
        """
        Return total money wagered per selection for an event.
        Used by the odds engine for line movement.
        e.g. {"Lakers": 1500.0, "Warriors": 800.0, "Over": 600.0, "Under": 200.0}
        """
        data = self._load(guild_id)
        dist: Dict[str, float] = {}
        for pool in ("active", "settled"):
            for bet in data[pool].values():
                if bet.get("event_id") != event_id:
                    continue
                if bet.get("status") == "cancelled":
                    continue
                if bet.get("bet_type") == "player_props":
                    continue   # props don't affect spread/total lines
                sel = bet.get("selection", "")
                if sel:
                    dist[sel] = dist.get(sel, 0.0) + bet.get("stake", 0.0)
        return dist

    def get_all_guilds(self) -> List[int]:
        return [int(p.stem) for p in self._base.glob("*.json")]
