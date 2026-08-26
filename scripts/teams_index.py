#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local SQLite index for the full pokecamp tournament-teams dataset.

The bundled pack (pokemon-calc/data/teams_full.json.gz, built by
cache/build_teams_pack.py) contains every team in the rolling 30-day window
with full roster details (item/ability/nature/moves). That pack is far too
large for any LLM context, so this module derives a local SQLite index from
it (one-time, a few seconds) and exposes small, hard-capped query functions.

Dependency direction: query.py -> teams_index.py. This module never imports
pokecamp_source; it only consumes the distilled pack dict (whose schema is
produced by pokecamp_source.distill_teams_full()).

Everything here is standard library only. The index DB lives under
data/cache/ (gitignored) and can be rebuilt from the bundled pack at any
time, so it is safe to delete.
"""

import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from damage import _NATURE_ALIASES

SCHEMA_VERSION = "1"
PACK_FILENAME = "teams_full.json.gz"
INDEX_FILENAME = "teams_index.db"

HARD_LIMIT = 50  # maximum rows any query may return (context-size guard)


# ---------------------------------------------------------------------------
# Paths / pack loading
# ---------------------------------------------------------------------------


def pack_path(data_dir: Path) -> Path:
    return data_dir / PACK_FILENAME


def index_path(data_dir: Path) -> Path:
    return data_dir / "cache" / INDEX_FILENAME


def load_pack(data_dir: Path) -> dict[str, Any] | None:
    """Read the bundled gzip teams pack. Returns None when missing/corrupt."""
    path = pack_path(data_dir)
    if not path.exists():
        return None
    try:
        import gzip
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _pack_sha256(data_dir: Path) -> str:
    path = pack_path(data_dir)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


# ---------------------------------------------------------------------------
# Index build
# ---------------------------------------------------------------------------


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS meta;
        DROP TABLE IF EXISTS tournaments;
        DROP TABLE IF EXISTS teams;
        DROP TABLE IF EXISTS team_pokemon;
        DROP TABLE IF EXISTS team_pokemon_moves;

        CREATE TABLE meta (
          key TEXT PRIMARY KEY,
          value TEXT
        );
        CREATE TABLE tournaments (
          id TEXT PRIMARY KEY,
          name TEXT,
          date TEXT,
          team_count INTEGER,
          has_details INTEGER
        );
        CREATE TABLE teams (
          id TEXT PRIMARY KEY,
          tournament_id TEXT REFERENCES tournaments(id),
          player TEXT,
          country TEXT,
          placing INTEGER,
          wins INTEGER, losses INTEGER, ties INTEGER
        );
        CREATE TABLE team_pokemon (
          team_id TEXT REFERENCES teams(id),
          slot INTEGER,
          identifier TEXT,
          name_zh TEXT,
          item_en TEXT,
          ability_en TEXT,
          pre_mega_ability_en TEXT,
          nature_en TEXT,
          tera_type_en TEXT,
          PRIMARY KEY (team_id, slot)
        );
        CREATE TABLE team_pokemon_moves (
          team_id TEXT REFERENCES teams(id),
          slot INTEGER,
          move_en TEXT
        );
        CREATE INDEX idx_tp_identifier ON team_pokemon(identifier);
        CREATE INDEX idx_tp_name_zh    ON team_pokemon(name_zh);
        CREATE INDEX idx_tp_item       ON team_pokemon(item_en);
        CREATE INDEX idx_moves_move    ON team_pokemon_moves(move_en);
        CREATE INDEX idx_teams_player  ON teams(player);
        CREATE INDEX idx_teams_tourn   ON teams(tournament_id);
        """
    )


def build_index(db_path: Path, pack: dict[str, Any], source_origin: str = "snapshot",
                teams_sha256: str = "", pack_sha256: str = "") -> dict[str, Any]:
    """(Re)build the SQLite index from a distilled pack dict.

    source_origin: "snapshot" (bundled pack) or "online" (fresh fetch) — later
    reads report origin "snapshot" / "cache" accordingly.
    """
    meta = dict(pack.get("meta") or {})
    teams = pack.get("teams") or []
    missing_ids = {m.get("id") for m in (meta.get("missing_detail_tournaments") or [])
                   if isinstance(m, dict)}

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        _create_schema(conn)

        tournaments: dict[str, dict[str, Any]] = {}
        for t in teams:
            tinfo = t.get("tournament") or {}
            tid = tinfo.get("id") or ""
            if not tid:
                continue
            rec = tournaments.setdefault(tid, {
                "id": tid, "name": tinfo.get("name"), "date": tinfo.get("date"),
                "team_count": 0,
                "has_details": 0 if tid in missing_ids else 1,
            })
            rec["team_count"] += 1
        conn.executemany(
            "INSERT INTO tournaments VALUES (:id, :name, :date, :team_count, :has_details)",
            list(tournaments.values()),
        )

        conn.executemany(
            "INSERT INTO teams VALUES (:id, :tournament_id, :player, :country,"
            " :placing, :wins, :losses, :ties)",
            [{
                "id": t.get("id"),
                "tournament_id": (t.get("tournament") or {}).get("id"),
                "player": t.get("player"),
                "country": t.get("country"),
                "placing": t.get("placing"),
                "wins": (t.get("record") or {}).get("wins"),
                "losses": (t.get("record") or {}).get("losses"),
                "ties": (t.get("record") or {}).get("ties"),
            } for t in teams],
        )

        mon_rows, move_rows = [], []
        for t in teams:
            tid_team = t.get("id")
            for slot, mon in enumerate(t.get("pokemon") or []):
                mon_rows.append((
                    tid_team, slot, mon.get("identifier"), mon.get("name_zh"),
                    mon.get("item_en"), mon.get("ability_en"),
                    mon.get("pre_mega_ability_en"), mon.get("nature_en"),
                    mon.get("tera_type_en"),
                ))
                for mv in (mon.get("moves_en") or []):
                    move_rows.append((tid_team, slot, mv))
        conn.executemany("INSERT INTO team_pokemon VALUES (?,?,?,?,?,?,?,?,?)", mon_rows)
        conn.executemany("INSERT INTO team_pokemon_moves VALUES (?,?,?)", move_rows)

        name_maps = meta.pop("name_maps", {})
        meta_rows = [
            ("schema_version", SCHEMA_VERSION),
            ("built_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            ("source_origin", source_origin),
            ("teams_sha256", teams_sha256),
            ("pack_sha256", pack_sha256),
            ("team_count", str(len(teams))),
            ("pack_meta", json.dumps(meta, ensure_ascii=False)),
            ("name_maps", json.dumps(name_maps, ensure_ascii=False)),
        ]
        conn.executemany("INSERT INTO meta VALUES (?,?)", meta_rows)
        conn.commit()
    finally:
        conn.close()
    return {
        "teams": len(teams),
        "tournaments": len(tournaments),
        "pokemon_rows": len(mon_rows),
        "move_rows": len(move_rows),
        "missing_detail_tournaments": len(missing_ids),
    }


def ensure_index(data_dir: Path) -> Path | None:
    """Return a usable index DB path, building it from the bundled pack if needed.

    Returns the existing DB when it already matches the bundled pack; rebuilds
    when the pack is newer; returns None when neither DB nor pack exists.
    """
    db = index_path(data_dir)
    pack_sig = _pack_sha256(data_dir)
    if db.exists():
        meta = load_index_meta(db)
        if pack_sig and meta.get("pack_sha256") == pack_sig \
                and meta.get("schema_version") == SCHEMA_VERSION:
            return db
        if not pack_sig:
            # No bundled pack to compare against; keep using whatever DB exists.
            return db
    if not pack_sig:
        return None
    pack = load_pack(data_dir)
    if pack is None:
        return db if db.exists() else None
    print("Building local teams index from bundled pack (one-time, a few seconds) ...",
          file=sys.stderr)
    build_index(db, pack, source_origin="snapshot", pack_sha256=pack_sig)
    return db


# ---------------------------------------------------------------------------
# Meta / provenance
# ---------------------------------------------------------------------------


def load_index_meta(db_path: Path) -> dict[str, Any]:
    """Provenance + stats for the index. origin: snapshot (bundled pack) or
    cache (derived from a past online fetch)."""
    conn = _connect(db_path)
    try:
        rows = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
        missing = [dict(r) for r in conn.execute(
            "SELECT id, name FROM tournaments WHERE has_details = 0")]
    finally:
        conn.close()
    pack_meta = json.loads(rows.get("pack_meta") or "{}")
    origin = "snapshot" if rows.get("source_origin") == "snapshot" else "cache"
    meta: dict[str, Any] = {
        "source": pack_meta.get("source"),
        "source_url": pack_meta.get("source_url"),
        "format": pack_meta.get("format"),
        "date_range": pack_meta.get("date_range"),
        "tournament_count": pack_meta.get("tournament_count"),
        "team_count": int(rows.get("team_count") or 0),
        "data_fetched_at": pack_meta.get("fetched_at"),
        "index_built_at": rows.get("built_at"),
        "schema_version": rows.get("schema_version"),
        "pack_sha256": rows.get("pack_sha256"),
        "origin": origin,
    }
    if missing:
        meta["missing_detail_tournaments"] = missing
    return meta


def _load_name_maps(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    row = conn.execute("SELECT value FROM meta WHERE key='name_maps'").fetchone()
    return json.loads(row["value"]) if row else {"item": {}, "ability": {}, "move": {}}


def nature_zh(en_name: str) -> str:
    if not en_name:
        return ""
    return _NATURE_ALIASES.get(en_name.lower(), en_name)


# ---------------------------------------------------------------------------
# Queries (all hard-capped at HARD_LIMIT rows)
# ---------------------------------------------------------------------------


def _cap(limit: int) -> int:
    return max(1, min(int(limit or 12), HARD_LIMIT))


def _roster_names(conn: sqlite3.Connection, team_id: str) -> list[str]:
    return [r["name_zh"] for r in conn.execute(
        "SELECT name_zh FROM team_pokemon WHERE team_id=? ORDER BY slot", (team_id,))]


def _team_row_summary(conn: sqlite3.Connection, row: sqlite3.Row, no: int) -> dict[str, Any]:
    return {
        "no": no,
        "id": row["id"],
        "tournament": row["tournament_name"],
        "date": row["tournament_date"],
        "player": row["player"],
        "country": row["country"],
        "placing": row["placing"],
        "record": {"wins": row["wins"], "losses": row["losses"], "ties": row["ties"]},
        "pokemon": _roster_names(conn, row["id"]),
    }


def find_teams(db_path: Path, pokemon_identifier: str | None = None,
               pokemon_name_zh: str | None = None, player: str | None = None,
               tournament: str | None = None, limit: int = 12) -> dict[str, Any]:
    """Team summaries filtered by pokemon / player / tournament, most recent first."""
    where, params = [], []
    if pokemon_identifier or pokemon_name_zh:
        ident = (pokemon_identifier or "").lower()
        name_zh = pokemon_name_zh or ""
        where.append(
            "EXISTS (SELECT 1 FROM team_pokemon tp WHERE tp.team_id = t.id"
            " AND (lower(tp.identifier) = ? OR tp.name_zh = ?))")
        params += [ident, name_zh]
    if player:
        where.append("lower(t.player) LIKE '%' || lower(?) || '%'")
        params.append(player)
    if tournament:
        where.append("tn.name LIKE '%' || ? || '%'")
        params.append(tournament)
    sql = (
        "SELECT t.id, t.placing, t.player, t.country, t.wins, t.losses, t.ties,"
        " tn.name AS tournament_name, tn.date AS tournament_date"
        " FROM teams t JOIN tournaments tn ON tn.id = t.tournament_id"
        + (" WHERE " + " AND ".join(where) if where else "")
        + " ORDER BY tn.date DESC, t.placing ASC LIMIT ?"
    )
    params.append(_cap(limit))
    conn = _connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
        teams = [_team_row_summary(conn, r, i + 1) for i, r in enumerate(rows)]
    finally:
        conn.close()
    return {"count": len(teams), "teams": teams}


def _usage_where(placing_max: int | None, tournament: str | None,
                 alias: str = "t", tourn_alias: str = "tn") -> tuple[str, list[Any]]:
    where, params = [], []
    if placing_max is not None:
        where.append(f"{alias}.placing <= ?")
        params.append(placing_max)
    if tournament:
        where.append(f"{tourn_alias}.name LIKE '%' || ? || '%'")
        params.append(tournament)
    return (" WHERE " + " AND ".join(where) if where else ""), params


def aggregate_pokemon_usage(db_path: Path, placing_max: int | None = None,
                            tournament: str | None = None,
                            limit: int = 20) -> dict[str, Any]:
    """Pokemon appearance share across indexed teams (optionally a subset:
    only teams placing <= placing_max, or a single tournament)."""
    where, params = _usage_where(placing_max, tournament)
    conn = _connect(db_path)
    try:
        total = conn.execute(
            f"SELECT COUNT(*) AS c FROM teams t JOIN tournaments tn ON tn.id = t.tournament_id{where}",
            params).fetchone()["c"]
        rows = conn.execute(
            "SELECT tp.identifier, tp.name_zh, COUNT(DISTINCT tp.team_id) AS c"
            " FROM team_pokemon tp"
            " JOIN teams t ON t.id = tp.team_id"
            " JOIN tournaments tn ON tn.id = t.tournament_id"
            f"{where} GROUP BY tp.identifier ORDER BY c DESC LIMIT ?",
            params + [_cap(limit)]).fetchall()
    finally:
        conn.close()
    stats = [{
        "rank": i + 1,
        "identifier": r["identifier"],
        "name_zh": r["name_zh"],
        "team_count": r["c"],
        "usage_percent": round(r["c"] * 100.0 / total, 3) if total else 0,
    } for i, r in enumerate(rows)]
    scope: dict[str, Any] = {"teams_in_scope": total}
    if placing_max is not None:
        scope["placing_max"] = placing_max
    if tournament:
        scope["tournament"] = tournament
    return {"scope": scope, "stats": stats}


def aggregate_teammates(db_path: Path, identifier: str, limit: int = 12) -> dict[str, Any]:
    """Most common teammates of a pokemon across all indexed teams."""
    ident = identifier.lower()
    conn = _connect(db_path)
    try:
        base = conn.execute(
            "SELECT COUNT(DISTINCT team_id) AS c FROM team_pokemon"
            " WHERE lower(identifier) = ?", (ident,)).fetchone()["c"]
        rows = conn.execute(
            "SELECT tp.identifier, tp.name_zh, COUNT(DISTINCT tp.team_id) AS c"
            " FROM team_pokemon tp"
            " WHERE lower(tp.identifier) != ? AND tp.team_id IN"
            "   (SELECT team_id FROM team_pokemon WHERE lower(identifier) = ?)"
            " GROUP BY tp.identifier ORDER BY c DESC LIMIT ?",
            (ident, ident, _cap(limit))).fetchall()
    finally:
        conn.close()
    teammates = [{
        "identifier": r["identifier"],
        "name_zh": r["name_zh"],
        "team_count": r["c"],
        "percentage": round(r["c"] * 100.0 / base, 1) if base else 0,
    } for r in rows]
    return {"identifier": identifier, "team_count": base, "teammates": teammates}


def aggregate_pokemon_builds(db_path: Path, identifier: str) -> dict[str, Any]:
    """Item/ability/nature/move shares of one pokemon across all indexed teams."""
    ident = identifier.lower()
    conn = _connect(db_path)
    try:
        name_maps = _load_name_maps(conn)
        rows = conn.execute(
            "SELECT team_id, slot, item_en, ability_en, nature_en, tera_type_en"
            " FROM team_pokemon WHERE lower(identifier) = ?", (ident,)).fetchall()
        move_rows = conn.execute(
            "SELECT m.move_en FROM team_pokemon_moves m"
            " JOIN team_pokemon tp ON tp.team_id = m.team_id AND tp.slot = m.slot"
            " WHERE lower(tp.identifier) = ?", (ident,)).fetchall()
        name_row = conn.execute(
            "SELECT name_zh FROM team_pokemon WHERE lower(identifier) = ? LIMIT 1",
            (ident,)).fetchone()
    finally:
        conn.close()

    from collections import Counter
    n = len(rows)

    def _top(counter: Counter, kind: str, limit: int) -> list[dict[str, Any]]:
        out = []
        for en, c in counter.most_common(limit):
            if not en:
                continue
            out.append({
                "name_en": en,
                "name_zh": (name_maps.get(kind) or {}).get(en, en),
                "percentage": round(c * 100.0 / n, 1) if n else 0,
            })
            if len(out) >= limit:
                break
        return out

    result: dict[str, Any] = {
        "identifier": identifier,
        "name_zh": name_row["name_zh"] if name_row else "",
        "team_count": n,
        "items": _top(Counter(r["item_en"] for r in rows), "item", 8),
        "abilities": _top(Counter(r["ability_en"] for r in rows), "ability", 8),
        "natures": [{"name_en": en, "name_zh": nature_zh(en),
                     "percentage": round(c * 100.0 / n, 1) if n else 0}
                    for en, c in Counter(r["nature_en"] for r in rows).most_common(8) if en],
        "moves": _top(Counter(r["move_en"] for r in move_rows), "move", 12),
    }
    tera = Counter(r["tera_type_en"] for r in rows
                   if r["tera_type_en"] and r["tera_type_en"] not in ("None", "nothing"))
    if tera:
        result["tera_types"] = [{"name_en": en,
                                 "percentage": round(c * 100.0 / n, 1) if n else 0}
                                for en, c in tera.most_common(5)]
    return result


def get_team_detail(db_path: Path, team_id: str) -> dict[str, Any] | None:
    """Full detail of one team (items/abilities/moves/natures, zh + en)."""
    conn = _connect(db_path)
    try:
        name_maps = _load_name_maps(conn)
        row = conn.execute(
            "SELECT t.id, t.placing, t.player, t.country, t.wins, t.losses, t.ties,"
            " tn.name AS tournament_name, tn.date AS tournament_date"
            " FROM teams t JOIN tournaments tn ON tn.id = t.tournament_id"
            " WHERE t.id = ?", (team_id,)).fetchone()
        if row is None:
            return None
        mons = []
        for mon in conn.execute(
                "SELECT * FROM team_pokemon WHERE team_id=? ORDER BY slot", (team_id,)):
            moves_en = [r["move_en"] for r in conn.execute(
                "SELECT move_en FROM team_pokemon_moves WHERE team_id=? AND slot=?",
                (team_id, mon["slot"]))]
            item_en = mon["item_en"] or ""
            ability_en = mon["ability_en"] or ""
            pre_en = mon["pre_mega_ability_en"] or ""
            entry: dict[str, Any] = {
                "identifier": mon["identifier"],
                "name_zh": mon["name_zh"],
                "item_en": item_en,
                "item_zh": (name_maps.get("item") or {}).get(item_en, item_en),
                "ability_en": ability_en,
                "ability_zh": (name_maps.get("ability") or {}).get(ability_en, ability_en),
                "moves_en": moves_en,
                "moves_zh": [(name_maps.get("move") or {}).get(m, m) for m in moves_en],
                "nature_en": mon["nature_en"] or "",
                "nature_zh": nature_zh(mon["nature_en"] or ""),
            }
            if mon["tera_type_en"]:
                entry["tera_type_en"] = mon["tera_type_en"]
            if pre_en:
                entry["pre_mega_ability_en"] = pre_en
                entry["pre_mega_ability_zh"] = (name_maps.get("ability") or {}).get(pre_en, pre_en)
            mons.append(entry)
    finally:
        conn.close()
    return {
        "id": row["id"],
        "tournament": {"name": row["tournament_name"], "date": row["tournament_date"]},
        "player": row["player"],
        "country": row["country"],
        "placing": row["placing"],
        "record": {"wins": row["wins"], "losses": row["losses"], "ties": row["ties"]},
        "pokemon": mons,
    }
