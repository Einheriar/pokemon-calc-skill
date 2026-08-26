#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pokecamp.cc data source for meta-environment data (usage stats & tournament teams).

Pluggable source design: query.py never talks to pokecamp directly — it calls
get_source() and uses the source object's fetch methods plus the distill/load
helpers in this module. A different source can be added later by implementing
the same methods and registering it in SOURCES.

Data provenance:
- Bundled snapshots (data/usage_stats.json, data/meta_teams.json) are built
  offline by cache/build_usage_stats.py and cache/build_meta_teams.py.
- --online mode fetches fresh data from pokecamp.cc on demand, caches the
  distilled result under data/cache/ (gitignored), and falls back to cache ->
  bundled snapshot on network failure.

Crawler etiquette (per project decision): requests are made only on explicit
user demand (--online) or by maintainers when refreshing snapshots; results
are cached locally; no site-wide crawling; robots.txt is respected
(pokecamp.cc allows all). Only standard library is used.
"""

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from damage import _NATURE_ALIASES

# ---------------------------------------------------------------------------
# Source registry (pluggable)
# ---------------------------------------------------------------------------


class PokecampSource:
    """pokecamp.cc static JSON endpoints (Champions regulation M-B)."""

    name = "pokecamp"
    display_name = "pokecamp.cc（基于 Limitless 公开赛事统计）"

    def __init__(self, base_url: str = "https://pokecamp.cc",
                 locale: str = "zh", regulation: str = "m-b") -> None:
        self.base_url = base_url.rstrip("/")
        self.locale = locale
        self.regulation = regulation

    # -- low level ------------------------------------------------------

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _regulation_path(self, suffix: str) -> str:
        return (f"/data/{self.locale}/champions/regulations/"
                f"{self.regulation}/{suffix}")

    def fetch_json(self, path: str, timeout: int = 120) -> Any:
        """Fetch a JSON document. Honors HTTP_PROXY/HTTPS_PROXY env vars.

        Requests gzip transfer encoding (the 15 MB teams list compresses to
        ~1.3 MB) and transparently decompresses.
        """
        req = urllib.request.Request(
            self.url(path),
            headers={
                # Identify the tool instead of masquerading as a browser.
                "User-Agent": "pokemon-calc-skill (on-demand meta query; +https://github.com/)",
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                import gzip
                body = gzip.decompress(body)
            return json.loads(body)

    # -- endpoints --------------------------------------------------------

    def usage_index_path(self) -> str:
        return self._regulation_path("pokemon.json")

    def pokemon_detail_path(self, pokemon_id: int) -> str:
        return self._regulation_path(f"pokemon/{pokemon_id}.json")

    def teams_path(self) -> str:
        return self._regulation_path("teams.json")

    def teams_page_path(self) -> str:
        return self._regulation_path("teams-page.json")

    def team_details_path(self, tournament_id: str) -> str:
        from urllib.parse import quote
        return self._regulation_path(f"team-details/{quote(tournament_id, safe='')}.json")

    def fetch_usage_index(self) -> list[dict[str, Any]]:
        return self.fetch_json(self.usage_index_path())

    def fetch_pokemon_detail(self, pokemon_id: int) -> dict[str, Any]:
        return self.fetch_json(self.pokemon_detail_path(pokemon_id))

    def fetch_teams(self) -> list[dict[str, Any]]:
        # NOTE: ~15 MB single file; call only on explicit --online demand.
        return self.fetch_json(self.teams_path())

    def fetch_teams_page(self) -> dict[str, Any]:
        return self.fetch_json(self.teams_page_path())

    def fetch_team_details(self, tournament_id: str) -> dict[str, Any]:
        return self.fetch_json(self.team_details_path(tournament_id))


SOURCES: dict[str, type[PokecampSource]] = {"pokecamp": PokecampSource}
DEFAULT_SOURCE = "pokecamp"


def get_source(name: str | None = None) -> PokecampSource:
    """Return a data source instance. Defaults to pokecamp."""
    key = name or DEFAULT_SOURCE
    cls = SOURCES.get(key)
    if cls is None:
        raise ValueError(f"Unknown meta data source: {key!r} (available: {sorted(SOURCES)})")
    return cls()


# ---------------------------------------------------------------------------
# Name translation helpers
# ---------------------------------------------------------------------------


def nature_zh(en_name: str) -> str:
    """English nature name -> Chinese canonical name (empty-safe)."""
    if not en_name:
        return ""
    return _NATURE_ALIASES.get(en_name.lower(), en_name)


def build_name_maps(teams_page: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Extract English -> Chinese maps from teams-page.json nameMaps."""
    maps: dict[str, dict[str, str]] = {"item": {}, "ability": {}, "move": {}}
    raw = (teams_page or {}).get("nameMaps", {})
    for kind, key in (("item", "itemMap"), ("ability", "abilityMap"), ("move", "moveMap")):
        for en, info in (raw.get(key) or {}).items():
            zh = (info or {}).get("localName") or (info or {}).get("nameZh")
            if zh:
                maps[kind][en] = zh
    return maps


# ---------------------------------------------------------------------------
# Distillers (shared by cache/build_*.py snapshot builders and --online mode)
# ---------------------------------------------------------------------------


def _top_entries(pairs: list[dict[str, Any]], name_map: dict[str, str], limit: int,
                 zh_field: str | None = None) -> list[dict[str, Any]]:
    """Convert pokecamp [{name, count, percentage}] rows to distilled top-N rows."""
    out = []
    for row in (pairs or [])[:limit]:
        en = row.get("name", "")
        entry: dict[str, Any] = {"name_en": en, "percentage": row.get("percentage", 0)}
        if zh_field and row.get(zh_field):
            entry["name_zh"] = row[zh_field]
        elif en in name_map:
            entry["name_zh"] = name_map[en]
        else:
            entry["name_zh"] = en
        out.append(entry)
    return out


def distill_pokemon_entry(index_rec: dict[str, Any],
                          detail: dict[str, Any] | None,
                          name_maps: dict[str, dict[str, str]],
                          sp_recs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Distill one pokemon's meta entry from pokecamp index + detail records."""
    usage = index_rec.get("usage") or {}
    entry: dict[str, Any] = {
        "id": index_rec.get("id"),
        "identifier": index_rec.get("identifier"),
        "name_zh": index_rec.get("nameZh") or index_rec.get("displayName") or "",
        "name_en": index_rec.get("nameEn") or "",
        "rank": usage.get("rank"),
        "usage_percent": usage.get("usagePercent"),
        "team_count": usage.get("teamCount"),
        "win_rate": usage.get("winRate"),
        "tournament_count": usage.get("tournamentCount"),
    }
    stats = ((detail or {}).get("limitlessStats") or {})
    if stats:
        entry["abilities"] = _top_entries(stats.get("abilities"), name_maps["ability"], 8)
        entry["items"] = _top_entries(stats.get("items"), name_maps["item"], 8)
        entry["moves"] = _top_entries(stats.get("moves"), name_maps["move"], 12)
        natures = [{"name_en": r.get("name", ""), "name_zh": nature_zh(r.get("name", "")),
                    "percentage": r.get("percentage", 0)}
                   for r in (stats.get("natures") or [])[:8]]
        entry["natures"] = natures
        # Teammates are already Chinese names in pokecamp data
        entry["teammates"] = [{"name_zh": r.get("name", ""), "percentage": r.get("percentage", 0)}
                              for r in (stats.get("teammates") or [])[:12]]
        tera = [r for r in (stats.get("teraTypes") or [])
                if r.get("name") not in (None, "", "None", "nothing")]
        if tera:
            entry["tera_types"] = [{"name_en": r["name"], "percentage": r.get("percentage", 0)}
                                   for r in tera[:5]]
    # Recommended stat-point spreads (32-point Champions system), doubles
    if sp_recs:
        rec = sp_recs.get(str(index_rec.get("id"))) or {}
        spreads = []
        for s in (rec.get("doubles") or [])[:8]:
            spreads.append({
                "nature_en": s.get("nature", ""),
                "nature_zh": nature_zh(s.get("nature", "")),
                "hp": s.get("hp", 0), "attack": s.get("attack", 0),
                "defense": s.get("defense", 0), "special_attack": s.get("specialAttack", 0),
                "special_defense": s.get("specialDefense", 0), "speed": s.get("speed", 0),
                "percentage": s.get("percentage", 0),
            })
        if spreads:
            entry["spreads"] = spreads
    return entry


def distill_usage_snapshot(index_data: list[dict[str, Any]],
                           details_by_id: dict[int, dict[str, Any]],
                           teams_page: dict[str, Any],
                           fetched_at: str) -> dict[str, Any]:
    """Build the usage_stats.json snapshot document."""
    name_maps = build_name_maps(teams_page)
    sp_recs = (teams_page or {}).get("statPointRecommendations") or {}
    meta_page = (teams_page or {}).get("meta") or {}
    pokemon = [
        distill_pokemon_entry(rec, details_by_id.get(rec.get("id")), name_maps, sp_recs)
        for rec in index_data
    ]
    pokemon.sort(key=lambda e: e.get("rank") or 99999)
    return {
        "meta": {
            "source": PokecampSource.display_name,
            "source_url": "https://pokecamp.cc/zh/champions/pokemon",
            "format": meta_page.get("format", "M-B"),
            "date_range": meta_page.get("dateRange"),
            "tournament_count": meta_page.get("tournamentCount"),
            "team_count": meta_page.get("teamCount"),
            "fetched_at": fetched_at,
        },
        "pokemon": pokemon,
    }


def _sort_key_team(team: dict[str, Any]) -> tuple:
    date = ((team.get("tournament") or {}).get("date") or "")
    return (date, -(team.get("placing") or 9999))


def distill_teams_snapshot(teams_data: list[dict[str, Any]],
                           details_by_tournament: dict[str, dict[str, Any]],
                           teams_page: dict[str, Any],
                           top: int,
                           fetched_at: str) -> dict[str, Any]:
    """Build the meta_teams.json snapshot document (top N teams by recency)."""
    name_maps = build_name_maps(teams_page)
    meta_page = (teams_page or {}).get("meta") or {}
    sorted_teams = sorted(teams_data, key=_sort_key_team, reverse=True)
    out_teams = []
    for team in sorted_teams[:top]:
        tinfo = team.get("tournament") or {}
        detail_map = details_by_tournament.get(tinfo.get("id")) or {}
        detail_list = detail_map.get(team.get("id")) or []
        detail_by_ident = {}
        roster = team.get("pokemon") or []
        for d, base in zip(detail_list, roster):
            detail_by_ident[base.get("identifier")] = d
        mons = []
        for base in roster:
            d = detail_by_ident.get(base.get("identifier")) or {}
            item_en = base.get("item") or ""
            ability_en = d.get("ability") or ""
            pre_en = d.get("preMegaAbility") or ""
            mons.append({
                "identifier": base.get("identifier"),
                "name_zh": base.get("displayName") or "",
                "item_en": item_en,
                "item_zh": name_maps["item"].get(item_en, item_en),
                "ability_en": ability_en,
                "ability_zh": name_maps["ability"].get(ability_en, ability_en),
                **({"pre_mega_ability_en": pre_en,
                    "pre_mega_ability_zh": name_maps["ability"].get(pre_en, pre_en)} if pre_en else {}),
                "moves_en": d.get("moves") or [],
                "moves_zh": [name_maps["move"].get(m, m) for m in (d.get("moves") or [])],
                "nature_en": d.get("nature") or "",
                "nature_zh": nature_zh(d.get("nature") or ""),
            })
        rec = team.get("record") or {}
        out_teams.append({
            "id": team.get("id"),
            "tournament": {"name": tinfo.get("name"), "date": (tinfo.get("date") or "")[:10]},
            "player": team.get("playerName"),
            "country": team.get("country"),
            "placing": team.get("placing"),
            "record": {"wins": rec.get("wins"), "losses": rec.get("losses"),
                       "ties": rec.get("ties")},
            "pokemon": mons,
        })
    return {
        "meta": {
            "source": PokecampSource.display_name,
            "source_url": "https://pokecamp.cc/zh/champions/teams",
            "format": meta_page.get("format", "M-B"),
            "date_range": meta_page.get("dateRange"),
            "tournament_count": meta_page.get("tournamentCount"),
            "team_count": meta_page.get("teamCount"),
            "top": top,
            "fetched_at": fetched_at,
        },
        "teams": out_teams,
    }


# ---------------------------------------------------------------------------
# Snapshot / cache IO with online fallback
# ---------------------------------------------------------------------------

SNAPSHOT_FILES = {"usage": "usage_stats.json", "teams": "meta_teams.json"}
CACHE_FILES = {"usage": "usage_stats_online.json", "teams": "meta_teams_online.json"}
RAW_CACHE_FILES = {"index": "pokecamp_pokemon_index.json",
                   "teams_page": "pokecamp_teams_page.json"}


def _read_json_file(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_cache(data_dir: Path, filename: str, payload: Any) -> None:
    cache_dir = data_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_dir / filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def _read_cache(data_dir: Path, filename: str) -> Any:
    path = data_dir / "cache" / filename
    if not path.exists():
        return None
    try:
        return _read_json_file(path)
    except Exception:
        return None


def load_snapshot(data_dir: Path, kind: str) -> dict[str, Any] | None:
    path = data_dir / SNAPSHOT_FILES[kind]
    return _read_json_file(path) if path.exists() else None


def load_online_cache(data_dir: Path, kind: str) -> dict[str, Any] | None:
    return _read_cache(data_dir, CACHE_FILES[kind])


def save_online_cache(data_dir: Path, kind: str, payload: dict[str, Any]) -> None:
    _write_cache(data_dir, CACHE_FILES[kind], payload)


def _with_provenance(data: dict[str, Any], origin: str,
                     online_error: Exception | None = None) -> dict[str, Any]:
    """Attach provenance (origin + meta) so callers can label the output.

    When an --online fetch failed and we fell back, online_error carries the
    failure reason so the caller can report it to the user.
    """
    meta = dict(data.get("meta") or {})
    meta["origin"] = origin
    if online_error is not None:
        meta["online_error"] = f"{type(online_error).__name__}: {online_error}"
    out = dict(data)
    out["meta"] = meta
    return out


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _get_raw(data_dir: Path, kind: str, fetcher, online: bool) -> Any:
    """Fetch a raw pokecamp document with cache write-through / read fallback.

    Re-raises the original error when no cache exists, so callers can report
    the real failure reason to the user.
    """
    if not online:
        return _read_cache(data_dir, RAW_CACHE_FILES[kind])
    try:
        data = fetcher()
        _write_cache(data_dir, RAW_CACHE_FILES[kind], data)
        return data
    except Exception:
        cached = _read_cache(data_dir, RAW_CACHE_FILES[kind])
        if cached is not None:
            return cached
        raise


def get_usage_data(data_dir: Path, online: bool = False,
                   source: PokecampSource | None = None) -> dict[str, Any]:
    """Load the usage dataset.

    offline: bundled snapshot (full per-pokemon top lists).
    online: fresh index + teams-page fetch distilled into a *light* snapshot
    (ranking fields only, no per-pokemon top lists — use
    get_usage_entry_detail() for a single pokemon's detail, which costs just
    one extra ~23 KB request instead of ~300).

    Fallback chain on network failure: online cache -> bundled snapshot.
    Returned dict always has meta.origin in {"snapshot", "cache", "online"}.
    """
    if not online:
        snap = load_snapshot(data_dir, "usage")
        if snap is None:
            raise FileNotFoundError("usage_stats.json snapshot is missing")
        return _with_provenance(snap, "snapshot")

    source = source or get_source()
    try:
        index = _get_raw(data_dir, "index", source.fetch_usage_index, online=True)
        teams_page = _get_raw(data_dir, "teams_page", source.fetch_teams_page, online=True)
        if index is None or teams_page is None:
            raise ConnectionError("pokecamp fetch failed and no raw cache exists")
        data = distill_usage_snapshot(index, {}, teams_page, fetched_at=_now_iso())
        save_online_cache(data_dir, "usage", data)
        return _with_provenance(data, "online")
    except Exception as e:
        cached = load_online_cache(data_dir, "usage")
        if cached is not None:
            return _with_provenance(cached, "cache", online_error=e)
        snap = load_snapshot(data_dir, "usage")
        if snap is None:
            raise
        return _with_provenance(snap, "snapshot", online_error=e)


def get_usage_entry_detail(data_dir: Path, pokemon_id: int, online: bool = False,
                           source: PokecampSource | None = None) -> dict[str, Any] | None:
    """Fetch + distill a single pokemon's full entry (lightweight online path).

    Costs one ~23 KB detail request (cached per pokemon) plus the cheap raw
    index / teams-page documents (also cached). Returns None when offline or
    when every fetch/cache path fails — callers then degrade to the light
    entry from get_usage_data().
    """
    if not online:
        return None
    source = source or get_source()
    detail_cache = f"usage_detail_{pokemon_id}.json"
    try:
        detail = source.fetch_pokemon_detail(pokemon_id)
        _write_cache(data_dir, detail_cache, detail)
    except Exception:
        detail = _read_cache(data_dir, detail_cache)
    if detail is None:
        return None
    index = _get_raw(data_dir, "index", source.fetch_usage_index, online=True)
    teams_page = _get_raw(data_dir, "teams_page", source.fetch_teams_page, online=True)
    index_rec = next((r for r in (index or []) if r.get("id") == pokemon_id), None)
    if index_rec is None:
        index_rec = (detail.get("pokemon") or {})
    name_maps = build_name_maps(teams_page or {})
    sp_recs = (teams_page or {}).get("statPointRecommendations") or {}
    return distill_pokemon_entry(index_rec, detail, name_maps, sp_recs)


def get_teams_data(data_dir: Path, online: bool = False, top: int = 12,
                   source: PokecampSource | None = None) -> dict[str, Any]:
    """Load the meta teams dataset (same fallback chain as usage).

    NOTE: online mode downloads the full teams.json (~15 MB) once, then the
    team-details for the involved tournaments only.
    """
    if not online:
        snap = load_snapshot(data_dir, "teams")
        if snap is None:
            raise FileNotFoundError("meta_teams.json snapshot is missing")
        return _with_provenance(snap, "snapshot")

    source = source or get_source()
    try:
        teams = source.fetch_teams()
        teams_page = _get_raw(data_dir, "teams_page", source.fetch_teams_page, online=True) or {}
        sorted_teams = sorted(teams, key=_sort_key_team, reverse=True)
        tournament_ids = []
        for t in sorted_teams[:top]:
            tid = (t.get("tournament") or {}).get("id")
            if tid and tid not in tournament_ids:
                tournament_ids.append(tid)
        details = {tid: source.fetch_team_details(tid) for tid in tournament_ids}
        data = distill_teams_snapshot(teams, details, teams_page, top=top,
                                      fetched_at=_now_iso())
        save_online_cache(data_dir, "teams", data)
        return _with_provenance(data, "online")
    except Exception as e:
        cached = load_online_cache(data_dir, "teams")
        if cached is not None:
            return _with_provenance(cached, "cache", online_error=e)
        snap = load_snapshot(data_dir, "teams")
        if snap is None:
            raise
        return _with_provenance(snap, "snapshot", online_error=e)
