"""Tests for server/content_loader.py."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from server.models.database import get_all_content_items, init_db
from server.content_loader import load_content, load_all_content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # init_db normally opens its own connection, so we run the schema directly.
    from server.models.database import SCHEMA_SQL
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_level_dir(base: Path, level: str = "a1") -> Path:
    level_dir = base / level
    level_dir.mkdir(parents=True, exist_ok=True)
    return level_dir


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn():
    c = _make_conn()
    yield c
    c.close()


@pytest.fixture()
def tmp_content(tmp_path):
    """Return a base content directory with a populated a1/ sub-directory."""
    level_dir = _make_level_dir(tmp_path)

    _write_json(level_dir / "chunks.json", [
        {
            "id": "a1-chunk-001",
            "chunk": "regarde !",
            "translation": "look!",
            "situation": "parenting",
            "cefr_level": "A1",
            "register": "spoken",
        },
        {
            "id": "a1-chunk-002",
            "chunk": "oh non !",
            "translation": "oh no!",
            "situation": "parenting",
            "cefr_level": "A1",
            "register": "spoken",
        },
    ])

    _write_json(level_dir / "scenarios.json", [
        {
            "id": "a1-scenario-001",
            "title": "Playing at the park",
            "situation": "parenting",
            "cefr_level": "A1",
            "target_structures": ["imperative", "present tense -er verbs"],
        },
    ])

    _write_json(level_dir / "exercises.json", [
        {
            "id": "a1-exercise-001",
            "type": "gap_fill",
            "situation": "parenting",
            "cefr_level": "A1",
            "target_structure": "passé composé with être",
        },
    ])

    _write_json(level_dir / "grammar_points.json", [
        {
            "id": "a1-grammar-001",
            "title": "Present tense: être",
            "cefr_level": "A1",
            "situations": ["social", "parenting"],
        },
    ])

    return tmp_path


# ---------------------------------------------------------------------------
# Tests: individual content types
# ---------------------------------------------------------------------------

class TestLoadChunks:
    def test_loads_all_chunks(self, conn, tmp_content):
        level_dir = tmp_content / "a1"
        summary = load_content(conn, level_dir)
        assert summary["chunk"] == 2

    def test_chunk_fields(self, conn, tmp_content):
        load_content(conn, tmp_content / "a1")
        items = [i for i in get_all_content_items(conn) if i["type"] == "chunk"]
        assert len(items) == 2
        item = items[0]
        assert item["situation"] == "parenting"
        assert item["cefr_level"] == "A1"
        assert item["target_structure"] == ""
        assert item["register"] == "spoken"
        data = json.loads(item["content_json"])
        assert data["id"] == "a1-chunk-001"

    def test_chunk_idempotency(self, conn, tmp_content):
        level_dir = tmp_content / "a1"
        load_content(conn, level_dir)
        summary = load_content(conn, level_dir)
        assert summary["chunk"] == 0
        assert len([i for i in get_all_content_items(conn) if i["type"] == "chunk"]) == 2


class TestLoadScenarios:
    def test_loads_scenarios(self, conn, tmp_content):
        summary = load_content(conn, tmp_content / "a1")
        assert summary["scenario"] == 1

    def test_scenario_fields(self, conn, tmp_content):
        load_content(conn, tmp_content / "a1")
        items = [i for i in get_all_content_items(conn) if i["type"] == "scenario"]
        assert len(items) == 1
        item = items[0]
        assert item["register"] == "both"
        assert item["target_structure"] == "imperative, present tense -er verbs"
        data = json.loads(item["content_json"])
        assert data["id"] == "a1-scenario-001"

    def test_scenario_idempotency(self, conn, tmp_content):
        level_dir = tmp_content / "a1"
        load_content(conn, level_dir)
        summary = load_content(conn, level_dir)
        assert summary["scenario"] == 0


class TestLoadExercises:
    def test_loads_exercises(self, conn, tmp_content):
        summary = load_content(conn, tmp_content / "a1")
        assert summary["exercise"] == 1

    def test_exercise_fields(self, conn, tmp_content):
        load_content(conn, tmp_content / "a1")
        items = [i for i in get_all_content_items(conn) if i["type"] == "exercise"]
        assert len(items) == 1
        item = items[0]
        assert item["register"] == "both"
        assert item["target_structure"] == "passé composé with être"
        data = json.loads(item["content_json"])
        assert data["id"] == "a1-exercise-001"

    def test_exercise_idempotency(self, conn, tmp_content):
        level_dir = tmp_content / "a1"
        load_content(conn, level_dir)
        summary = load_content(conn, level_dir)
        assert summary["exercise"] == 0


class TestLoadGrammar:
    def test_loads_grammar(self, conn, tmp_content):
        summary = load_content(conn, tmp_content / "a1")
        assert summary["grammar"] == 1

    def test_grammar_fields(self, conn, tmp_content):
        load_content(conn, tmp_content / "a1")
        items = [i for i in get_all_content_items(conn) if i["type"] == "grammar"]
        assert len(items) == 1
        item = items[0]
        assert item["register"] == "both"
        assert item["situation"] == "social"  # first element of situations array
        assert item["target_structure"] == "Present tense: être"
        data = json.loads(item["content_json"])
        assert data["id"] == "a1-grammar-001"

    def test_grammar_idempotency(self, conn, tmp_content):
        level_dir = tmp_content / "a1"
        load_content(conn, level_dir)
        summary = load_content(conn, level_dir)
        assert summary["grammar"] == 0


# ---------------------------------------------------------------------------
# Tests: load_all_content
# ---------------------------------------------------------------------------

class TestLoadAllContent:
    def test_scans_level_directories(self, conn, tmp_content):
        # Add a second level directory so we can verify scanning.
        a2_dir = _make_level_dir(tmp_content, "a2")
        _write_json(a2_dir / "chunks.json", [
            {
                "id": "a2-chunk-001",
                "chunk": "c'est bon",
                "translation": "that's good",
                "situation": "social",
                "cefr_level": "A2",
                "register": "spoken",
            }
        ])
        # Provide empty files for the other types so the loader doesn't crash.
        for fname in ("scenarios.json", "exercises.json", "grammar_points.json"):
            _write_json(a2_dir / fname, [])

        results = load_all_content(conn, tmp_content)
        assert "a1" in results
        assert "a2" in results
        assert results["a1"]["chunk"] == 2
        assert results["a2"]["chunk"] == 1

    def test_full_idempotency(self, conn, tmp_content):
        load_all_content(conn, tmp_content)
        second = load_all_content(conn, tmp_content)
        for counts in second.values():
            assert all(v == 0 for v in counts.values())

    def test_missing_files_are_skipped(self, conn, tmp_path):
        """A level directory with no JSON files loads 0 items without error."""
        level_dir = _make_level_dir(tmp_path, "a1")
        summary = load_content(conn, level_dir)
        assert summary == {"chunk": 0, "scenario": 0, "exercise": 0, "grammar": 0}

    def test_total_item_count(self, conn, tmp_content):
        load_all_content(conn, tmp_content)
        all_items = get_all_content_items(conn)
        # 2 chunks + 1 scenario + 1 exercise + 1 grammar = 5
        assert len(all_items) == 5
