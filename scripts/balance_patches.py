"""Load the bundled, date-keyed Pokémon Champions balance changes."""

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=4)
def load_patches(data_dir: Path) -> dict[str, dict[str, Any]]:
    patches = {}
    for path in sorted((data_dir / "champions_balance_patches").glob("*.json")):
        patch_id = path.stem
        if date.fromisoformat(patch_id).isoformat() != patch_id:
            raise ValueError(f"Invalid Champions balance patch filename: {path.name}")
        with path.open(encoding="utf-8") as handle:
            patch = json.load(handle)
        if (patch.get("schema_version") != 1 or patch.get("id") != patch_id
                or patch.get("effective_date") != patch_id):
            raise ValueError(f"Invalid Champions balance patch metadata: {path.name}")
        patches[patch_id] = patch
    return patches


def metadata(patch: dict[str, Any]) -> dict[str, str]:
    return {key: patch[key] for key in ("id", "title", "effective_date", "source")}


def changes(patches: tuple[dict[str, Any], ...], section: str, stem: str) -> dict[str, Any]:
    """Return the latest value and contributing patch for each changed field."""
    return {
        field: {"value": value, "patch": metadata(patch)}
        for patch in patches
        for field, value in patch.get(section, {}).get(stem, {}).items()
    }


def learnset_additions(patches: tuple[dict[str, Any], ...], stem: str) -> dict[str, dict[str, Any]]:
    """Index additions by exact form and move, retaining their source."""
    additions: dict[str, dict[str, Any]] = {}
    for patch in patches:
        for form, moves in patch.get("learnsets", {}).get(stem, {}).items():
            form_moves = additions.setdefault(form, {})
            for move in moves:
                form_moves.setdefault(move, metadata(patch))
    return additions


def result_fields(changed: dict[str, Any]) -> dict[str, Any]:
    if not changed:
        return {}
    return {
        "balance_patch": max((change["patch"] for change in changed.values()), key=lambda patch: patch["id"]),
        "balance_changes": {
            key: {**change, "patch": change["patch"]["id"]}
            for key, change in changed.items()
        },
    }
