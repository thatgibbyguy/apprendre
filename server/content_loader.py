"""Load A1 (and future level) content JSON files into the SQLite database."""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from server.models.database import create_content_item, get_connection, init_db

# Path to the content directory relative to this file's project root.
_DEFAULT_CONTENT_DIR = Path(__file__).parent.parent / "content"


def _item_exists(conn: sqlite3.Connection, item_type: str, item_id: str) -> bool:
    """Return True if a content_items row already holds this type + content id."""
    cur = conn.execute(
        "SELECT id FROM content_items WHERE type = ? AND json_extract(content_json, '$.id') = ?",
        (item_type, item_id),
    )
    return cur.fetchone() is not None


def _load_chunks(conn: sqlite3.Connection, level_dir: Path) -> int:
    path = level_dir / "chunks.json"
    if not path.exists():
        return 0
    items: list[Dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    loaded = 0
    for item in items:
        if _item_exists(conn, "chunk", item["id"]):
            continue
        create_content_item(
            conn,
            type="chunk",
            situation=item["situation"],
            cefr_level=item["cefr_level"],
            target_structure="",
            content_json=item,
            register=item.get("register", "spoken"),
        )
        loaded += 1
    return loaded


def _load_scenarios(conn: sqlite3.Connection, level_dir: Path) -> int:
    path = level_dir / "scenarios.json"
    if not path.exists():
        return 0
    items: list[Dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    loaded = 0
    for item in items:
        if _item_exists(conn, "scenario", item["id"]):
            continue
        target_structure = ", ".join(item.get("target_structures", []))
        create_content_item(
            conn,
            type="scenario",
            situation=item["situation"],
            cefr_level=item["cefr_level"],
            target_structure=target_structure,
            content_json=item,
            register="both",
        )
        loaded += 1
    return loaded


def _load_exercises(conn: sqlite3.Connection, level_dir: Path) -> int:
    path = level_dir / "exercises.json"
    if not path.exists():
        return 0
    items: list[Dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    loaded = 0
    for item in items:
        if _item_exists(conn, "exercise", item["id"]):
            continue
        create_content_item(
            conn,
            type="exercise",
            situation=item["situation"],
            cefr_level=item["cefr_level"],
            target_structure=item.get("target_structure", ""),
            content_json=item,
            register="both",
        )
        loaded += 1
    return loaded


def _load_grammar(conn: sqlite3.Connection, level_dir: Path) -> int:
    path = level_dir / "grammar_points.json"
    if not path.exists():
        return 0
    items: list[Dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    loaded = 0
    for item in items:
        if _item_exists(conn, "grammar", item["id"]):
            continue
        situations: list[str] = item.get("situations", [])
        situation = situations[0] if situations else ""
        create_content_item(
            conn,
            type="grammar",
            situation=situation,
            cefr_level=item["cefr_level"],
            target_structure=item.get("title", ""),
            content_json=item,
            register="both",
        )
        loaded += 1
    return loaded


def load_content(conn: sqlite3.Connection, content_dir: Path) -> Dict[str, int]:
    """Read all 4 JSON files from *content_dir* and insert new rows.

    Returns a summary dict: {"chunk": n, "scenario": n, "exercise": n, "grammar": n}
    """
    content_dir = Path(content_dir)
    return {
        "chunk": _load_chunks(conn, content_dir),
        "scenario": _load_scenarios(conn, content_dir),
        "exercise": _load_exercises(conn, content_dir),
        "grammar": _load_grammar(conn, content_dir),
    }


def load_all_content(
    conn: sqlite3.Connection,
    content_base_dir: Optional[Path] = None,
) -> Dict[str, Dict[str, int]]:
    """Scan *content_base_dir* for level sub-directories and load each one.

    Returns a dict keyed by level name, e.g. {"a1": {"chunk": 45, ...}}.
    """
    base = Path(content_base_dir or _DEFAULT_CONTENT_DIR)
    results: Dict[str, Dict[str, int]] = {}
    for level_dir in sorted(base.iterdir()):
        if level_dir.is_dir():
            results[level_dir.name] = load_content(conn, level_dir)
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load French learning content into the database.")
    parser.add_argument(
        "--content-dir",
        type=Path,
        default=_DEFAULT_CONTENT_DIR,
        help="Base content directory (default: <project_root>/content)",
    )
    args = parser.parse_args()

    init_db()
    conn = get_connection()
    try:
        totals = load_all_content(conn, args.content_dir)
        for level, counts in totals.items():
            total = sum(counts.values())
            print(f"{level}: loaded {total} items — {counts}")
    finally:
        conn.close()

    sys.exit(0)
