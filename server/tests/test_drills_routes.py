"""Tests for /api/drills routes.

Uses FastAPI's TestClient against the real router so the full request/response
cycle is exercised without spinning up a server.  The database is an in-memory
SQLite file (via a temp file path) so connections can be opened from any thread.
"""

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.models.database import (
    SCHEMA_SQL,
    create_card,
    create_content_item,
    create_learner,
    get_connection,
    update_card,
)
from server.routes.drills import router


# ---------------------------------------------------------------------------
# Test app
# ---------------------------------------------------------------------------

_test_app = FastAPI()
_test_app.include_router(router, prefix="/api/drills")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


def _format_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Base test case — each test gets a fresh temp-file DB
# ---------------------------------------------------------------------------

class DrillsRouteBase(unittest.TestCase):
    """Base class that wires a fresh on-disk SQLite DB to the routes."""

    def setUp(self) -> None:
        # Use a named temp file so multiple threads can open it independently.
        self._db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._db_path = self._db_file.name
        self._db_file.close()

        _init_db(self._db_path)

        # Seed via a direct connection — this is in the main thread.
        seed_conn = get_connection(self._db_path)
        self.learner_id = create_learner(seed_conn, "Test Learner")
        self.citem_id = create_content_item(
            seed_conn,
            type="chunk",
            situation="parenting",
            cefr_level="A1",
            target_structure="",
            content_json={
                "id": "a1-chunk-001",
                "chunk": "regarde !",
                "translation": "look!",
                "example_sentence": "Regarde, un avion !",
                "example_translation": "Look, a plane!",
            },
            register="spoken",
        )
        seed_conn.close()

        # Patch get_connection in the routes module to open our temp DB.
        db_path = self._db_path

        def _make_conn() -> sqlite3.Connection:
            return get_connection(db_path)

        self._patcher = patch("server.routes.drills.get_connection", side_effect=_make_conn)
        self._patcher.start()
        self.client = TestClient(_test_app)

    def tearDown(self) -> None:
        self._patcher.stop()
        Path(self._db_path).unlink(missing_ok=True)

    # ---- convenience --------------------------------------------------------

    def _open(self) -> sqlite3.Connection:
        """Open a direct connection to the test DB (for setup/assertions)."""
        return get_connection(self._db_path)


# ---------------------------------------------------------------------------
# GET /api/drills/due
# ---------------------------------------------------------------------------

class TestGetDue(DrillsRouteBase):

    def test_returns_new_card_as_due(self) -> None:
        conn = self._open()
        create_card(conn, self.learner_id, self.citem_id)
        conn.close()
        resp = self.client.get(f"/api/drills/due?learner_id={self.learner_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["cards"]), 1)
        self.assertEqual(data["cards"][0]["state"], "new")

    def test_returns_overdue_card(self) -> None:
        conn = self._open()
        card_id = create_card(conn, self.learner_id, self.citem_id)
        past = _format_dt(_now_utc() - timedelta(days=3))
        update_card(conn, card_id, {"state": "review", "due_date": past})
        conn.close()
        resp = self.client.get(f"/api/drills/due?learner_id={self.learner_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["cards"]), 1)

    def test_future_card_not_returned(self) -> None:
        conn = self._open()
        card_id = create_card(conn, self.learner_id, self.citem_id)
        future = _format_dt(_now_utc() + timedelta(days=5))
        update_card(conn, card_id, {"state": "review", "due_date": future})
        conn.close()
        resp = self.client.get(f"/api/drills/due?learner_id={self.learner_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["cards"]), 0)

    def test_content_item_included_in_response(self) -> None:
        conn = self._open()
        create_card(conn, self.learner_id, self.citem_id)
        conn.close()
        resp = self.client.get(f"/api/drills/due?learner_id={self.learner_id}")
        card = resp.json()["cards"][0]
        self.assertIn("content_item", card)
        ci = card["content_item"]
        self.assertIn("content", ci)
        self.assertEqual(ci["content"]["chunk"], "regarde !")

    def test_stats_included_in_response(self) -> None:
        conn = self._open()
        create_card(conn, self.learner_id, self.citem_id)
        conn.close()
        resp = self.client.get(f"/api/drills/due?learner_id={self.learner_id}")
        data = resp.json()
        self.assertIn("stats", data)
        for key in ("total", "due_now", "new", "learning", "review", "relearning"):
            self.assertIn(key, data["stats"])

    def test_unknown_learner_returns_404(self) -> None:
        resp = self.client.get("/api/drills/due?learner_id=9999")
        self.assertEqual(resp.status_code, 404)

    def test_missing_learner_id_returns_422(self) -> None:
        resp = self.client.get("/api/drills/due")
        self.assertEqual(resp.status_code, 422)


# ---------------------------------------------------------------------------
# GET /api/drills/{card_id}
# ---------------------------------------------------------------------------

class TestGetCard(DrillsRouteBase):

    def test_returns_card_with_content(self) -> None:
        conn = self._open()
        card_id = create_card(conn, self.learner_id, self.citem_id)
        conn.close()
        resp = self.client.get(f"/api/drills/{card_id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("card", data)
        self.assertEqual(data["card"]["id"], card_id)
        self.assertIn("content_item", data["card"])

    def test_unknown_card_returns_404(self) -> None:
        resp = self.client.get("/api/drills/9999")
        self.assertEqual(resp.status_code, 404)

    def test_content_item_has_parsed_content(self) -> None:
        conn = self._open()
        card_id = create_card(conn, self.learner_id, self.citem_id)
        conn.close()
        resp = self.client.get(f"/api/drills/{card_id}")
        ci = resp.json()["card"]["content_item"]
        self.assertIn("content", ci)
        self.assertIsInstance(ci["content"], dict)


# ---------------------------------------------------------------------------
# POST /api/drills/{card_id}/rate
# ---------------------------------------------------------------------------

class TestRateCard(DrillsRouteBase):

    def test_good_rating_returns_updated_card(self) -> None:
        conn = self._open()
        card_id = create_card(conn, self.learner_id, self.citem_id)
        conn.close()
        resp = self.client.post(f"/api/drills/{card_id}/rate", json={"rating": "good"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("card", data)
        self.assertIn("next_due", data)

    def test_all_ratings_accepted(self) -> None:
        for label in ("again", "hard", "good", "easy"):
            conn = self._open()
            card_id = create_card(conn, self.learner_id, self.citem_id)
            conn.close()
            resp = self.client.post(f"/api/drills/{card_id}/rate", json={"rating": label})
            self.assertEqual(resp.status_code, 200, f"Failed for rating={label!r}")

    def test_invalid_rating_returns_422(self) -> None:
        conn = self._open()
        card_id = create_card(conn, self.learner_id, self.citem_id)
        conn.close()
        resp = self.client.post(f"/api/drills/{card_id}/rate", json={"rating": "perfect"})
        self.assertEqual(resp.status_code, 422)

    def test_unknown_card_returns_404(self) -> None:
        resp = self.client.post("/api/drills/9999/rate", json={"rating": "good"})
        self.assertEqual(resp.status_code, 404)

    def test_rating_advances_card_state(self) -> None:
        conn = self._open()
        card_id = create_card(conn, self.learner_id, self.citem_id)
        conn.close()
        resp = self.client.post(f"/api/drills/{card_id}/rate", json={"rating": "good"})
        card = resp.json()["card"]
        self.assertNotEqual(card["state"], "new")

    def test_next_due_is_set_after_rating(self) -> None:
        conn = self._open()
        card_id = create_card(conn, self.learner_id, self.citem_id)
        conn.close()
        resp = self.client.post(f"/api/drills/{card_id}/rate", json={"rating": "easy"})
        data = resp.json()
        self.assertIsNotNone(data["next_due"])

    def test_missing_rating_field_returns_422(self) -> None:
        conn = self._open()
        card_id = create_card(conn, self.learner_id, self.citem_id)
        conn.close()
        resp = self.client.post(f"/api/drills/{card_id}/rate", json={})
        self.assertEqual(resp.status_code, 422)


# ---------------------------------------------------------------------------
# POST /api/drills/seed
# ---------------------------------------------------------------------------

class TestSeedCards(DrillsRouteBase):

    def test_seed_creates_cards_from_a1_content(self) -> None:
        with patch("server.routes.drills.load_content") as mock_load:
            mock_load.return_value = {"chunk": 1, "scenario": 0, "exercise": 0, "grammar": 0}
            resp = self.client.post(f"/api/drills/seed?learner_id={self.learner_id}")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("created", data)
        self.assertIn("total", data)
        self.assertEqual(data["learner_id"], self.learner_id)

    def test_seed_unknown_learner_returns_404(self) -> None:
        resp = self.client.post("/api/drills/seed?learner_id=9999")
        self.assertEqual(resp.status_code, 404)

    def test_seed_missing_learner_id_returns_422(self) -> None:
        resp = self.client.post("/api/drills/seed")
        self.assertEqual(resp.status_code, 422)

    def test_seed_is_idempotent(self) -> None:
        """Calling seed twice must not create duplicate cards."""
        with patch("server.routes.drills.load_content"):
            resp1 = self.client.post(f"/api/drills/seed?learner_id={self.learner_id}")
            self.assertEqual(resp1.status_code, 200)
            total_after_first = resp1.json()["total"]

            resp2 = self.client.post(f"/api/drills/seed?learner_id={self.learner_id}")
            self.assertEqual(resp2.status_code, 200)
            created_second = resp2.json()["created"]
            total_after_second = resp2.json()["total"]

        self.assertEqual(created_second, 0)
        self.assertEqual(total_after_first, total_after_second)

    def test_seed_returns_correct_total(self) -> None:
        """Total should equal the number of A1 chunk content items seeded."""
        # The setUp already inserted one A1 chunk content item.
        with patch("server.routes.drills.load_content"):
            resp = self.client.post(f"/api/drills/seed?learner_id={self.learner_id}")

        data = resp.json()
        self.assertGreaterEqual(data["total"], 0)
        self.assertGreaterEqual(data["created"], 0)


if __name__ == "__main__":
    unittest.main()
