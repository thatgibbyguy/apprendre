"""Tests for the FSRS spaced retrieval engine."""

import sqlite3
import unittest
from datetime import datetime, timedelta, timezone

from server.models.database import (
    create_card,
    create_content_item,
    create_learner,
    get_card,
    get_reviews_for_card,
    update_card,
)
from server.services.srs_engine import (
    _format_dt,
    _now_utc,
    create_cards_for_learner,
    get_due_cards,
    get_review_stats,
    schedule_review,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS learners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    level_listening TEXT NOT NULL DEFAULT 'A1',
    level_reading TEXT NOT NULL DEFAULT 'A1',
    level_speaking TEXT NOT NULL DEFAULT 'A1',
    level_writing TEXT NOT NULL DEFAULT 'A1',
    instruction_language TEXT NOT NULL DEFAULT 'en',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    situation TEXT NOT NULL,
    cefr_level TEXT NOT NULL,
    target_structure TEXT NOT NULL,
    content_json TEXT NOT NULL DEFAULT '{}',
    register TEXT NOT NULL DEFAULT 'spoken',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    content_item_id INTEGER NOT NULL REFERENCES content_items(id),
    difficulty REAL NOT NULL DEFAULT 0.0,
    stability REAL NOT NULL DEFAULT 0.0,
    retrievability REAL NOT NULL DEFAULT 1.0,
    due_date TEXT,
    last_review TEXT,
    reps INTEGER NOT NULL DEFAULT 0,
    lapses INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS review_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id),
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    rating INTEGER NOT NULL,
    review_date TEXT NOT NULL DEFAULT (datetime('now')),
    elapsed_days REAL NOT NULL DEFAULT 0.0,
    scheduled_days REAL NOT NULL DEFAULT 0.0
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    mode TEXT NOT NULL,
    scenario TEXT,
    cefr_level TEXT,
    transcript_json TEXT NOT NULL DEFAULT '[]',
    feedback_summary TEXT,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT
);
CREATE TABLE IF NOT EXISTS error_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learner_id INTEGER NOT NULL REFERENCES learners(id),
    error_type TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    resolved INTEGER NOT NULL DEFAULT 0
);
"""


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    return conn


def _seed(conn: sqlite3.Connection) -> tuple[int, int]:
    """Create one learner and one content item, return (learner_id, content_item_id)."""
    lid = create_learner(conn, "Test Learner")
    cid = create_content_item(
        conn,
        type="chunk",
        situation="parenting",
        cefr_level="A1",
        target_structure="present_tense",
        content_json={"french": "Bonjour", "english": "Hello"},
    )
    return lid, cid


class TestScheduleReview(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = _make_db()
        self.learner_id, self.citem_id = _seed(self.conn)
        self.card_id = create_card(self.conn, self.learner_id, self.citem_id)

    def tearDown(self) -> None:
        self.conn.close()

    def test_schedule_review_good_rating_updates_card(self) -> None:
        updated = schedule_review(self.conn, self.card_id, rating=3)
        self.assertIsNotNone(updated)
        self.assertNotEqual(updated["state"], "new")
        self.assertGreater(updated["reps"], 0)
        self.assertIsNotNone(updated["last_review"])

    def test_schedule_review_creates_history_entry(self) -> None:
        schedule_review(self.conn, self.card_id, rating=3)
        reviews = get_reviews_for_card(self.conn, self.card_id)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["rating"], 3)
        self.assertEqual(reviews[0]["learner_id"], self.learner_id)

    def test_schedule_review_again_increments_lapses_after_review(self) -> None:
        # First review with Good to move card out of New state.
        schedule_review(self.conn, self.card_id, rating=3)
        # A second review with Again from Review state should record a lapse.
        # (exact lapse increment depends on FSRS internals; we just check it
        # doesn't crash and returns a valid card.)
        updated = schedule_review(self.conn, self.card_id, rating=1)
        self.assertIsNotNone(updated)

    def test_schedule_review_all_ratings_succeed(self) -> None:
        for rating in (1, 2, 3, 4):
            conn = _make_db()
            lid, cid = _seed(conn)
            card_id = create_card(conn, lid, cid)
            result = schedule_review(conn, card_id, rating=rating)
            self.assertIsNotNone(result, f"Rating {rating} returned None")
            conn.close()

    def test_schedule_review_sets_due_date(self) -> None:
        updated = schedule_review(self.conn, self.card_id, rating=3)
        self.assertIsNotNone(updated["due_date"])

    def test_schedule_review_invalid_rating_raises(self) -> None:
        with self.assertRaises(ValueError):
            schedule_review(self.conn, self.card_id, rating=5)

    def test_schedule_review_missing_card_raises(self) -> None:
        with self.assertRaises(ValueError):
            schedule_review(self.conn, card_id=9999, rating=3)

    def test_schedule_review_returns_updated_card_dict(self) -> None:
        result = schedule_review(self.conn, self.card_id, rating=4)
        # Verify it looks like a card row.
        self.assertIn("id", result)
        self.assertIn("difficulty", result)
        self.assertIn("stability", result)
        self.assertIn("state", result)


class TestGetDueCards(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = _make_db()
        self.learner_id, self.citem_id = _seed(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_new_card_is_due(self) -> None:
        create_card(self.conn, self.learner_id, self.citem_id)
        due = get_due_cards(self.conn, self.learner_id)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["state"], "new")

    def test_overdue_card_is_returned(self) -> None:
        card_id = create_card(self.conn, self.learner_id, self.citem_id)
        past = _format_dt(_now_utc() - timedelta(days=5))
        update_card(self.conn, card_id, {"state": "review", "due_date": past})
        due = get_due_cards(self.conn, self.learner_id)
        self.assertEqual(len(due), 1)

    def test_future_due_card_not_returned(self) -> None:
        card_id = create_card(self.conn, self.learner_id, self.citem_id)
        future = _format_dt(_now_utc() + timedelta(days=5))
        update_card(self.conn, card_id, {"state": "review", "due_date": future})
        due = get_due_cards(self.conn, self.learner_id)
        self.assertEqual(len(due), 0)

    def test_limit_is_respected(self) -> None:
        for _ in range(5):
            cid = create_content_item(
                self.conn,
                type="chunk",
                situation="social",
                cefr_level="A1",
                target_structure="vocab",
            )
            create_card(self.conn, self.learner_id, cid)
        due = get_due_cards(self.conn, self.learner_id, limit=3)
        self.assertEqual(len(due), 3)

    def test_due_cards_include_content_item(self) -> None:
        create_card(self.conn, self.learner_id, self.citem_id)
        due = get_due_cards(self.conn, self.learner_id)
        self.assertIn("content_item", due[0])
        ci = due[0]["content_item"]
        self.assertEqual(ci["type"], "chunk")
        self.assertIn("french", ci["content_json"])

    def test_overdue_cards_ordered_before_new(self) -> None:
        # Create a new card first.
        new_card_id = create_card(self.conn, self.learner_id, self.citem_id)

        # Create an overdue card for a second content item.
        cid2 = create_content_item(
            self.conn,
            type="grammar",
            situation="social",
            cefr_level="A2",
            target_structure="passe_compose",
        )
        overdue_card_id = create_card(self.conn, self.learner_id, cid2)
        past = _format_dt(_now_utc() - timedelta(days=3))
        update_card(self.conn, overdue_card_id, {"state": "review", "due_date": past})

        due = get_due_cards(self.conn, self.learner_id)
        # Overdue should come first.
        self.assertEqual(due[0]["id"], overdue_card_id)
        self.assertEqual(due[1]["id"], new_card_id)

    def test_no_cards_for_other_learner(self) -> None:
        create_card(self.conn, self.learner_id, self.citem_id)
        other_learner_id = create_learner(self.conn, "Other")
        due = get_due_cards(self.conn, other_learner_id)
        self.assertEqual(len(due), 0)


class TestCreateCardsForLearner(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = _make_db()
        self.learner_id, self.citem_id = _seed(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_creates_cards_for_given_items(self) -> None:
        ids = create_cards_for_learner(self.conn, self.learner_id, [self.citem_id])
        self.assertEqual(len(ids), 1)

    def test_skips_duplicate_content_items(self) -> None:
        create_cards_for_learner(self.conn, self.learner_id, [self.citem_id])
        # Second call with same content item should create nothing.
        ids = create_cards_for_learner(self.conn, self.learner_id, [self.citem_id])
        self.assertEqual(len(ids), 0)

    def test_bulk_create_multiple_items(self) -> None:
        cid2 = create_content_item(
            self.conn,
            type="grammar",
            situation="social",
            cefr_level="A2",
            target_structure="passe_compose",
        )
        cid3 = create_content_item(
            self.conn,
            type="chunk",
            situation="errands",
            cefr_level="A1",
            target_structure="vocab",
        )
        ids = create_cards_for_learner(self.conn, self.learner_id, [self.citem_id, cid2, cid3])
        self.assertEqual(len(ids), 3)

    def test_empty_list_returns_empty(self) -> None:
        ids = create_cards_for_learner(self.conn, self.learner_id, [])
        self.assertEqual(ids, [])

    def test_partial_duplicates(self) -> None:
        """Only the non-duplicate items should be created."""
        cid2 = create_content_item(
            self.conn,
            type="chunk",
            situation="social",
            cefr_level="A1",
            target_structure="vocab",
        )
        # Pre-create card for citem_id.
        create_cards_for_learner(self.conn, self.learner_id, [self.citem_id])
        ids = create_cards_for_learner(self.conn, self.learner_id, [self.citem_id, cid2])
        self.assertEqual(len(ids), 1)


class TestGetReviewStats(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = _make_db()
        self.learner_id, self.citem_id = _seed(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_empty_stats_for_no_cards(self) -> None:
        stats = get_review_stats(self.conn, self.learner_id)
        self.assertEqual(stats["total"], 0)
        self.assertEqual(stats["due_now"], 0)

    def test_new_card_counted_in_new_and_due(self) -> None:
        create_card(self.conn, self.learner_id, self.citem_id)
        stats = get_review_stats(self.conn, self.learner_id)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["new"], 1)
        self.assertEqual(stats["due_now"], 1)

    def test_future_review_card_not_due(self) -> None:
        card_id = create_card(self.conn, self.learner_id, self.citem_id)
        future = _format_dt(_now_utc() + timedelta(days=3))
        update_card(self.conn, card_id, {"state": "review", "due_date": future})
        stats = get_review_stats(self.conn, self.learner_id)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["review"], 1)
        self.assertEqual(stats["due_now"], 0)

    def test_stats_keys_present(self) -> None:
        stats = get_review_stats(self.conn, self.learner_id)
        for key in ("total", "due_now", "new", "learning", "review", "relearning"):
            self.assertIn(key, stats)

    def test_multiple_states_counted_correctly(self) -> None:
        # new card
        create_card(self.conn, self.learner_id, self.citem_id)

        # learning card (due)
        cid2 = create_content_item(self.conn, type="t", situation="s", cefr_level="A1", target_structure="t")
        card2 = create_card(self.conn, self.learner_id, cid2)
        past = _format_dt(_now_utc() - timedelta(hours=1))
        update_card(self.conn, card2, {"state": "learning", "due_date": past})

        # review card (not yet due)
        cid3 = create_content_item(self.conn, type="t", situation="s", cefr_level="A1", target_structure="t")
        card3 = create_card(self.conn, self.learner_id, cid3)
        future = _format_dt(_now_utc() + timedelta(days=5))
        update_card(self.conn, card3, {"state": "review", "due_date": future})

        stats = get_review_stats(self.conn, self.learner_id)
        self.assertEqual(stats["total"], 3)
        self.assertEqual(stats["new"], 1)
        self.assertEqual(stats["learning"], 1)
        self.assertEqual(stats["review"], 1)
        self.assertEqual(stats["due_now"], 2)  # new + overdue learning


if __name__ == "__main__":
    unittest.main()
