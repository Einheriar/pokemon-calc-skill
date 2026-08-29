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

import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
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

    # -- ladder endpoints (ingame / showdown) -----------------------------

    def pokemon_page_path(self, source_kind: str) -> str:
        """Per-source usage list: pokemon-page/{ingame|showdown|limitless}.json"""
        return self._regulation_path(f"pokemon-page/{source_kind}.json")

    def fetch_pokemon_page(self, source_kind: str) -> dict[str, Any]:
        return self.fetch_json(self.pokemon_page_path(source_kind))

    def fetch_text(self, path: str, timeout: int = 60) -> str:
        """Fetch a non-JSON document (e.g. the page HTML for build-id discovery)."""
        req = urllib.request.Request(
            self.url(path),
            headers={
                "User-Agent": "pokemon-calc-skill (on-demand meta query; +https://github.com/)",
                "Accept": "text/html,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def next_data_detail_path(self, build_id: str, pokemon_id: int) -> str:
        """Next.js data route carrying detailBySource for all three sources.

        ~1.34 MB raw / ~127 KB gzip per pokemon (mostly page furniture); always
        fetch with gzip and cache per pokemon.
        """
        return f"/_next/data/{build_id}/{self.locale}/champions/pokemon/{pokemon_id}.json"

    def fetch_next_data_detail(self, pokemon_id: int, build_id: str) -> dict[str, Any]:
        return self.fetch_json(self.next_data_detail_path(build_id, pokemon_id))


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


# ---------------------------------------------------------------------------
# Full teams pack (bundled snapshot) + local index orchestration
# ---------------------------------------------------------------------------


def _sort_key_team(team: dict[str, Any]) -> tuple:
    date = ((team.get("tournament") or {}).get("date") or "")
    return (date, -(team.get("placing") or 9999))


TEAM_DETAILS_CACHE_DIR = "team_details"
REQUEST_DELAY = 0.15  # seconds between detail requests (crawler etiquette)


def distill_teams_full(teams_data: list[dict[str, Any]],
                       details_by_tournament: dict[str, dict[str, Any]],
                       teams_page: dict[str, Any],
                       fetched_at: str,
                       missing_tournaments: list[dict[str, str]] | None = None
                       ) -> dict[str, Any]:
    """Distill the FULL teams list (all teams, all details) into the pack
    document that teams_index.py consumes. Unlike distill_teams_snapshot this
    keeps every team, the tournament id, tera types, and the EN->ZH name maps.
    """
    name_maps = build_name_maps(teams_page)
    meta_page = (teams_page or {}).get("meta") or {}
    out_teams = []
    for team in teams_data:
        tinfo = team.get("tournament") or {}
        tid = tinfo.get("id")
        detail_map = details_by_tournament.get(tid) or {}
        detail_list = detail_map.get(team.get("id")) or []
        detail_by_ident = {}
        roster = team.get("pokemon") or []
        for d, base in zip(detail_list, roster):
            detail_by_ident[base.get("identifier")] = d
        mons = []
        for base in roster:
            d = detail_by_ident.get(base.get("identifier")) or {}
            mons.append({
                "identifier": base.get("identifier"),
                "name_zh": base.get("displayName") or "",
                "item_en": base.get("item") or "",
                "ability_en": d.get("ability") or "",
                "pre_mega_ability_en": d.get("preMegaAbility") or "",
                "nature_en": d.get("nature") or "",
                "tera_type_en": d.get("teraType") or "",
                "moves_en": d.get("moves") or [],
            })
        rec = team.get("record") or {}
        out_teams.append({
            "id": team.get("id"),
            "tournament": {"id": tid, "name": tinfo.get("name"),
                           "date": (tinfo.get("date") or "")[:10]},
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
            "fetched_at": fetched_at,
            "name_maps": name_maps,
            "missing_detail_tournaments": list(missing_tournaments or []),
        },
        "teams": out_teams,
    }


def meta_snapshot_from_pack(pack: dict[str, Any], top: int) -> dict[str, Any]:
    """Derive the light meta_teams.json document (top N by recency, zh names
    resolved) from a full pack — no extra fetching needed."""
    meta = dict(pack.get("meta") or {})
    name_maps = meta.pop("name_maps", {}) or {}
    meta.pop("missing_detail_tournaments", None)
    meta["top"] = top
    sorted_teams = sorted(pack.get("teams") or [], key=_sort_key_team, reverse=True)
    out_teams = []
    for team in sorted_teams[:top]:
        mons = []
        for mon in team.get("pokemon") or []:
            item_en = mon.get("item_en") or ""
            ability_en = mon.get("ability_en") or ""
            pre_en = mon.get("pre_mega_ability_en") or ""
            moves_en = mon.get("moves_en") or []
            entry: dict[str, Any] = {
                "identifier": mon.get("identifier"),
                "name_zh": mon.get("name_zh"),
                "item_en": item_en,
                "item_zh": name_maps["item"].get(item_en, item_en),
                "ability_en": ability_en,
                "ability_zh": name_maps["ability"].get(ability_en, ability_en),
                "moves_en": moves_en,
                "moves_zh": [name_maps["move"].get(m, m) for m in moves_en],
                "nature_en": mon.get("nature_en") or "",
                "nature_zh": nature_zh(mon.get("nature_en") or ""),
            }
            if pre_en:
                entry["pre_mega_ability_en"] = pre_en
                entry["pre_mega_ability_zh"] = name_maps["ability"].get(pre_en, pre_en)
            mons.append(entry)
        out_teams.append({
            "id": team.get("id"),
            "tournament": {"name": (team.get("tournament") or {}).get("name"),
                           "date": (team.get("tournament") or {}).get("date")},
            "player": team.get("player"),
            "country": team.get("country"),
            "placing": team.get("placing"),
            "record": team.get("record"),
            "pokemon": mons,
        })
    return {"meta": meta, "teams": out_teams}


def _team_detail_cache_file(cache_dir: Path, tournament_id: str) -> Path:
    from urllib.parse import quote
    return cache_dir / f"{quote(tournament_id, safe='')}.json"


def fetch_team_details_cached(cache_dir: Path, source: PokecampSource,
                              tournament_ids: list[str], online: bool = True,
                              delay: float = REQUEST_DELAY,
                              log=None) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load team-details per tournament with a permanent on-disk cache.

    Tournament results are immutable once the event ends, so cached files
    never expire; only uncached tournament ids are fetched (with `delay`
    seconds between requests). Returns (details_by_tournament, missing_ids).
    """
    details: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for i, tid in enumerate(tournament_ids):
        path = _team_detail_cache_file(cache_dir, tid)
        if path.exists():
            try:
                details[tid] = _read_json_file(path)
                continue
            except Exception:
                pass  # corrupt cache file -> refetch
        if not online:
            missing.append(tid)
            continue
        try:
            if delay:
                time.sleep(delay)
            data = source.fetch_team_details(tid)
            cache_dir.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            details[tid] = data
            if log:
                log(f"  [{i + 1}/{len(tournament_ids)}] fetched team-details {tid}")
        except Exception as e:
            missing.append(tid)
            if log:
                log(f"  [{i + 1}/{len(tournament_ids)}] FAILED team-details {tid}: {e}")
    return details, missing


def _teams_sha256(teams_data: list[dict[str, Any]]) -> str:
    blob = json.dumps(teams_data, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


#: Repeated `teams --online` calls within this window reuse the current index
#: without any network request (the teams list alone is ~1.3 MB gzip).
ONLINE_MIN_INTERVAL_SEC = 24 * 3600


def _parse_iso_utc(text: str) -> float | None:
    """Parse 'YYYY-MM-DDTHH:MM:SSZ' as a UTC epoch; None on failure."""
    try:
        import calendar
        return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


def get_teams_index(data_dir: Path, online: bool = False,
                    source: PokecampSource | None = None) -> dict[str, Any]:
    """Make the local teams index available and return {db_path, meta}.

    offline: reuse the existing index DB; rebuild from the bundled
    teams_full.json.gz pack when the DB is missing or the pack changed
    (pack_sha256 mismatch). A cache/online-derived index is never
    downgraded by the bundled pack. db_path is None when neither DB nor
    pack exists (callers fall back to the light meta_teams.json snapshot).

    online: throttled — if the current index was built from a fetch less than
    ONLINE_MIN_INTERVAL_SEC (24h) ago, it is returned as-is with a note and
    no network request is made. Otherwise fetch teams.json once (gzip ~1.3
    MB), skip the rebuild when the content hash is unchanged, otherwise
    incrementally fetch team-details for new tournaments only (per-tournament
    permanent cache) and rebuild.
    Fallback chain on network failure: existing DB -> bundled pack -> raise.
    meta.origin in {"online", "cache", "snapshot"}; meta.online_error carries
    the failure reason when a fallback was used.
    """
    import teams_index as tix

    db_path = tix.index_path(data_dir)

    if not online:
        # ensure_index reuses a matching DB, rebuilds when the bundled pack
        # changed, and never downgrades a cache/online-derived index.
        built = tix.ensure_index(data_dir)
        if built is None:
            return {"db_path": None, "meta": {
                "origin": "snapshot",
                "note": "teams_full pack missing; only the light top-12 snapshot is available",
            }}
        return {"db_path": built, "meta": tix.load_index_meta(built)}

    source = source or get_source()
    try:
        if db_path.exists():
            cur_meta = tix.load_index_meta(db_path)
            last_fetch = _parse_iso_utc(cur_meta.get("data_fetched_at") or "")
            if last_fetch is not None \
                    and (time.time() - last_fetch) < ONLINE_MIN_INTERVAL_SEC:
                cur_meta["note"] = (
                    f"teams data was fetched at {cur_meta['data_fetched_at']} "
                    "(less than 24h ago); skipped re-download")
                return {"db_path": db_path, "meta": cur_meta}
        teams = source.fetch_teams()
        sha = _teams_sha256(teams)
        if db_path.exists():
            cur = tix.load_index_meta(db_path)
            if cur and _read_meta_value(db_path, "teams_sha256") == sha:
                cur["origin"] = "online"
                cur["note"] = "teams list unchanged since last fetch; index not rebuilt"
                return {"db_path": db_path, "meta": cur}
        teams_page = _get_raw(data_dir, "teams_page", source.fetch_teams_page,
                              online=True) or {}
        tournament_ids: list[str] = []
        for t in teams:
            tid = (t.get("tournament") or {}).get("id")
            if tid and tid not in tournament_ids:
                tournament_ids.append(tid)
        details, missing = fetch_team_details_cached(
            data_dir / "cache" / TEAM_DETAILS_CACHE_DIR, source, tournament_ids,
            online=True, log=lambda m: print(m, file=sys.stderr))
        missing_meta = []
        for tid in missing:
            tname = next(((t.get("tournament") or {}).get("name")
                          for t in teams if (t.get("tournament") or {}).get("id") == tid), "")
            missing_meta.append({"id": tid, "name": tname})
        pack = distill_teams_full(teams, details, teams_page,
                                  fetched_at=_now_iso(),
                                  missing_tournaments=missing_meta)
        tix.build_index(db_path, pack, source_origin="online", teams_sha256=sha)
        meta = tix.load_index_meta(db_path)
        meta["origin"] = "online"
        return {"db_path": db_path, "meta": meta}
    except Exception as e:
        if db_path.exists():
            meta = tix.load_index_meta(db_path)
            meta["online_error"] = f"{type(e).__name__}: {e}"
            return {"db_path": db_path, "meta": meta}
        built = tix.ensure_index(data_dir)
        if built is not None:
            meta = tix.load_index_meta(built)
            meta["online_error"] = f"{type(e).__name__}: {e}"
            return {"db_path": built, "meta": meta}
        raise


def _read_meta_value(db_path: Path, key: str) -> str:
    import sqlite3
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception:
        return ""


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


# ---------------------------------------------------------------------------
# Ladder sources (ingame = official ranked, showdown = Showdown monthly)
#
# Both are single lightweight JSON lists (~230 KB) on the same static host —
# no teams concept, no index/SQLite needed. The ingame list is rank-only:
# usagePercent/teamCount/winRate are placeholder constants (0/1/null) that
# pokecamp fills to keep one record shape across sources; they are dropped at
# distill time so downstream never sees fake numbers. Mega forms are merged
# into their base species for ingame (the official ranking is per-species and
# pokecamp expands it into identical-rank rows); showdown keeps mega rows
# separate because Smogon counts them independently.
# ---------------------------------------------------------------------------

LADDER_REGULATION = "m-b"  # ladder data is published for the latest regulation only
LADDER_SOURCE_KINDS = ("ingame", "showdown")
LADDER_DISPLAY_NAMES = {
    "ingame": "pokecamp.cc（Pokémon Champions 官方实机排位数据）",
    "showdown": "pokecamp.cc（Pokémon Showdown 天梯月报）",
}
LADDER_SNAPSHOT_FILES = {"ingame": "ladder_ingame.json",
                         "showdown": "ladder_showdown.json"}
LADDER_CACHE_FILES = {"ingame": "ladder_ingame_online.json",
                      "showdown": "ladder_showdown_online.json"}

#: Ladder online queries within this window reuse the local cache without any
#: network request (official ranked data refreshes every 1-3 days, showdown
#: monthly, so 24h is already tighter than upstream).
LADDER_ONLINE_MIN_INTERVAL_SEC = 24 * 3600

_BUILD_ID_CACHE = "pokecamp_build_id.txt"
_BUILD_ID_RE = re.compile(r"/_next/static/([^/\"']+)/_buildManifest\.js")


def _ladder_source(source: PokecampSource | None) -> PokecampSource:
    """Ladder data lives under the latest regulation, not the default one."""
    if source is not None:
        return source
    return PokecampSource(regulation=LADDER_REGULATION)


def _cache_fresh(payload: dict[str, Any] | None,
                 max_age_sec: float = LADDER_ONLINE_MIN_INTERVAL_SEC) -> bool:
    if not payload:
        return False
    fetched = _parse_iso_utc(str((payload.get("meta") or {}).get("fetched_at") or ""))
    return fetched is not None and (time.time() - fetched) < max_age_sec


def distill_ladder_page(source_kind: str, page: dict[str, Any],
                        fetched_at: str) -> dict[str, Any]:
    """Distill a pokemon-page/{kind}.json list into the ladder snapshot doc."""
    meta_in = page.get("meta") or {}
    plist = page.get("pokemonList") or []
    meta: dict[str, Any] = {
        "source": LADDER_DISPLAY_NAMES[source_kind],
        "source_kind": source_kind,
        "source_url": f"https://pokecamp.cc/zh/champions/pokemon",
        "regulation": LADDER_REGULATION,
        "format": meta_in.get("format"),
        "date_range": meta_in.get("dateRange"),
        "generated_at": meta_in.get("generatedAt"),
        "fetched_at": fetched_at,
        "rank_only": source_kind == "ingame",
    }
    if source_kind == "ingame":
        meta["season"] = meta_in.get("sourceSeason")
        meta["data_version"] = meta_in.get("dataVersion")
    else:
        meta["month"] = meta_in.get("month")
        meta["cutoff"] = meta_in.get("cutoff")
        meta["raw_count"] = meta_in.get("rawCount")

    pokemon: list[dict[str, Any]] = []
    if source_kind == "ingame":
        # Merge mega rows into their base species (same speciesIdentifier,
        # identical ranks by construction).
        merged: dict[str, dict[str, Any]] = {}
        for rec in plist:
            u = rec.get("usage") or {}
            sp = rec.get("speciesIdentifier") or rec.get("identifier") or ""
            cur = merged.get(sp)
            if cur is None or (cur.get("_is_mega") and not rec.get("isMega")):
                merged[sp] = {
                    "id": rec.get("id"),
                    "identifier": rec.get("identifier"),
                    "name_zh": rec.get("displayName") or rec.get("nameZh") or "",
                    "name_en": rec.get("nameEn") or "",
                    "singles_rank": u.get("singlesRank") or None,
                    "doubles_rank": u.get("doublesRank") or None,
                    "includes_mega": False,
                    "_is_mega": bool(rec.get("isMega")),
                }
                if cur is not None:
                    merged[sp]["includes_mega"] = True
            else:
                cur["includes_mega"] = True
        pokemon = list(merged.values())
        for e in pokemon:
            e.pop("_is_mega", None)
            # A species seen only as a mega row is not "base + mega".
            if e["identifier"] and "-mega" in str(e["identifier"]):
                e["includes_mega"] = False
    else:
        for rec in plist:
            u = rec.get("usage") or {}
            pokemon.append({
                "id": rec.get("id"),
                "identifier": rec.get("identifier"),
                "name_zh": rec.get("displayName") or rec.get("nameZh") or "",
                "name_en": rec.get("nameEn") or "",
                "singles_rank": u.get("singlesRank") or None,
                "doubles_rank": u.get("doublesRank") or None,
                "singles_usage_percent": u.get("singlesUsagePercent") or 0,
                "doubles_usage_percent": u.get("doublesUsagePercent") or 0,
                "is_mega": bool(rec.get("isMega")),
            })

    rank_key = "doubles_rank"
    pokemon.sort(key=lambda e: e.get(rank_key) or 99999)
    return {"meta": meta, "pokemon": pokemon}


def get_ladder_data(data_dir: Path, source_kind: str, online: bool = False,
                    source: PokecampSource | None = None) -> dict[str, Any]:
    """Load a ladder usage dataset (ingame / showdown).

    offline: bundled snapshot ladder_{kind}.json.
    online: throttled — a cache younger than LADDER_ONLINE_MIN_INTERVAL_SEC is
    returned as-is; otherwise fetch pokemon-page/{kind}.json (~230 KB), distill
    and cache. Fallback chain on network failure: online cache -> snapshot.
    """
    if source_kind not in LADDER_SOURCE_KINDS:
        raise ValueError(f"Unknown ladder source: {source_kind!r} "
                         f"(available: {list(LADDER_SOURCE_KINDS)})")

    def _snap() -> dict[str, Any] | None:
        path = data_dir / LADDER_SNAPSHOT_FILES[source_kind]
        return _read_json_file(path) if path.exists() else None

    if not online:
        snap = _snap()
        if snap is None:
            raise FileNotFoundError(
                f"{LADDER_SNAPSHOT_FILES[source_kind]} snapshot is missing")
        return _with_provenance(snap, "snapshot")

    source = _ladder_source(source)
    cached = _read_cache(data_dir, LADDER_CACHE_FILES[source_kind])
    if _cache_fresh(cached):
        cached = _with_provenance(cached, "cache")
        cached["meta"]["note"] = (
            f"ladder data was fetched at {cached['meta'].get('fetched_at')} "
            "(less than 24h ago); skipped re-download")
        return cached
    try:
        page = source.fetch_pokemon_page(source_kind)
        data = distill_ladder_page(source_kind, page, fetched_at=_now_iso())
        _write_cache(data_dir, LADDER_CACHE_FILES[source_kind], data)
        return _with_provenance(data, "online")
    except Exception as e:
        if cached is not None:
            return _with_provenance(cached, "cache", online_error=e)
        snap = _snap()
        if snap is None:
            raise
        return _with_provenance(snap, "snapshot", online_error=e)


# -- ladder single-pokemon detail (Next.js data route, all sources in one) ---


def _discover_build_id(source: PokecampSource) -> str:
    html = source.fetch_text(f"/{source.locale}/champions/pokemon")
    m = _BUILD_ID_RE.search(html)
    if not m:
        raise RuntimeError("could not extract pokecamp build id from page HTML")
    return m.group(1)


def _get_build_id(data_dir: Path, source: PokecampSource,
                  refresh: bool = False) -> str:
    cache_path = data_dir / "cache" / _BUILD_ID_CACHE
    if not refresh and cache_path.exists():
        cached = cache_path.read_text(encoding="utf-8").strip()
        if cached:
            return cached
    build_id = _discover_build_id(source)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(build_id, encoding="utf-8")
    return build_id


def _fetch_next_data(data_dir: Path, source: PokecampSource,
                     pokemon_id: int) -> dict[str, Any]:
    """Fetch the next-data detail; on 404 rediscover the build id once and retry."""
    try:
        return source.fetch_next_data_detail(pokemon_id, _get_build_id(data_dir, source))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        return source.fetch_next_data_detail(
            pokemon_id, _get_build_id(data_dir, source, refresh=True))


def _detail_name_maps(mb: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Build en->zh maps from the pageProps-level item/ability/move maps."""
    maps: dict[str, dict[str, str]] = {"item": {}, "ability": {}, "move": {}, "teammate": {}}
    for kind, key in (("item", "itemMap"), ("ability", "abilityMap"), ("move", "moveMap")):
        for en, info in (mb.get(key) or {}).items():
            zh = (info or {}).get("localName") or (info or {}).get("nameZh")
            if zh:
                maps[kind][en] = zh
    # teammateMap keys are a mix of zh display names and identifiers
    for key, info in (mb.get("teammateMap") or {}).items():
        zh = (info or {}).get("displayName")
        if zh:
            maps["teammate"][key] = zh
    return maps


def _teammate_zh(name: str, tmap: dict[str, str]) -> str:
    if name in tmap:
        return tmap[name]
    key = name.lower().replace(" ", "-").replace(".", "").replace("'", "")
    return tmap.get(key, name)


def _pct_entries(rows: list[dict[str, Any]], name_map: dict[str, str],
                 limit: int) -> list[dict[str, Any]]:
    """[{name, percentage}] -> distilled rows with zh translation."""
    out = []
    for row in (rows or [])[:limit]:
        en = row.get("name", "")
        out.append({"name_en": en, "name_zh": name_map.get(en, en),
                    "percentage": row.get("percentage", 0)})
    return out


def distill_ladder_detail(page_props: dict[str, Any], source_kind: str,
                          battle_format: str = "doubles") -> dict[str, Any]:
    """Distill one pokemon's ladder detail from a next-data pageProps payload.

    ingame:   detailBySource.ingame.inGameReferenceByFormat[format]
              (real percentages for moves/items/abilities/natures/spreads;
              teammates are rank-only)
    showdown: detailBySource.showdown.smogonReferenceByFormat[format]
    """
    reg_key = LADDER_REGULATION.upper()
    mb = ((page_props.get("dataByRegulation") or {}).get(reg_key)) or {}
    dbs = mb.get("detailBySource") or {}
    maps = _detail_name_maps(mb)
    if source_kind == "ingame":
        src = ((dbs.get("ingame") or {}).get("inGameReferenceByFormat") or {})
    else:
        src = ((dbs.get("showdown") or {}).get("smogonReferenceByFormat") or {})
    rec = src.get(battle_format) or src.get("doubles") or {}
    if not rec:
        return {}

    entry: dict[str, Any] = {
        "detail_format": rec.get("format") or battle_format,
        "abilities": _pct_entries(rec.get("abilities"), maps["ability"], 8),
        "items": _pct_entries(rec.get("items"), maps["item"], 8),
        "moves": _pct_entries(rec.get("moves"), maps["move"], 12),
        "natures": [{"name_en": r.get("name", ""), "name_zh": nature_zh(r.get("name", "")),
                     "percentage": r.get("percentage", 0)}
                    for r in (rec.get("natures") or [])[:8]],
        "spreads": [{
            "nature_en": s.get("nature", "") or "",
            "nature_zh": nature_zh(s.get("nature", "") or ""),
            "hp": s.get("hp", 0), "attack": s.get("attack", 0),
            "defense": s.get("defense", 0), "special_attack": s.get("specialAttack", 0),
            "special_defense": s.get("specialDefense", 0), "speed": s.get("speed", 0),
            "percentage": s.get("percentage", 0),
        } for s in (rec.get("spreads") or [])[:8]],
    }
    teammates = []
    for r in (rec.get("teammates") or [])[:12]:
        en = r.get("name", "")
        t: dict[str, Any] = {"name_en": en, "name_zh": _teammate_zh(en, maps["teammate"])}
        if source_kind == "ingame":
            t["rank"] = r.get("rank")  # official ranked data: teammates are rank-only
        else:
            t["percentage"] = r.get("percentage", 0)
        teammates.append(t)
    entry["teammates"] = teammates
    if source_kind == "ingame":
        entry["ladder_season"] = rec.get("season")
    else:
        entry["ladder_month"] = rec.get("month")
        entry["ladder_cutoff"] = rec.get("cutoff")
    return entry


def get_ladder_entry_detail(data_dir: Path, pokemon_id: int,
                            battle_format: str = "doubles",
                            source_kind: str = "ingame",
                            online: bool = False,
                            source: PokecampSource | None = None
                            ) -> dict[str, Any] | None:
    """Fetch + distill one pokemon's ladder detail (online only).

    One ~127 KB gzip request per pokemon, cached for 24h; the cached payload
    covers both formats and both ladder sources.
    """
    if not online or pokemon_id is None:
        return None
    source = _ladder_source(source)
    cache_file = f"ladder_detail_{pokemon_id}.json"
    cached = _read_cache(data_dir, cache_file)
    raw = None
    if cached and _cache_fresh(cached):
        raw = cached.get("payload")
    if raw is None:
        try:
            raw = _fetch_next_data(data_dir, source, pokemon_id)
            _write_cache(data_dir, cache_file,
                         {"meta": {"fetched_at": _now_iso()},
                          "payload": (raw or {}).get("pageProps") or {}})
            raw = (raw or {}).get("pageProps") or {}
        except Exception:
            raw = (cached or {}).get("payload")
    if not raw:
        return None
    return distill_ladder_detail(raw, source_kind, battle_format)
