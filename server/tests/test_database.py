"""Tests for database schema and data access layer."""

import sqlite3
import unittest

from server.models.database import (
    create_card,
    create_content_item,
    create_error_pattern,
    create_learner,
    create_review,
    create_session,
    delete_learner,
    end_session,
    get_all_content_items,
    get_all_learners,
    get_card,
    get_cards_for_learner,
    get_connection,
    get_content_item,
    get_error_patterns_for_learner,
    get_learner,
    get_reviews_for_card,
    get_session,
    increment_error_pattern,
    init_db,
    resolve_error_pattern,
    seed_test_data,
    update_card,
    update_learner,
)


class TestDatabase(unittest.TestCase):
    """Test database operations using an in-memory SQLite database."""

    def setUp(self) -> None:
        self.conn = get_connection(":memory:")
        init_db(":memory:")
        # Re-init on our connection since get_connection creates a new one
        self.conn.executescript(
            """
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
        )

    def tearDown(self) -> None:
        self.conn.close()

    # -- Learners --

    def test_create_and_get_learner(self) -> None:
        lid = create_learner(self.conn, "Test User")
        learner = get_learner(self.conn, lid)
        self.assertIsNotNone(learner)
        self.assertEqual(learner["name"], "Test User")
        self.assertEqual(learner["level_listening"], "A1")

    def test_get_all_learners(self) -> None:
        create_learner(self.conn, "A")
        create_learner(self.conn, "B")
        self.assertEqual(len(get_all_learners(self.conn)), 2)

    def test_update_learner(self) -> None:
        lid = create_learner(self.conn, "Old Name")
        update_learner(self.conn, lid, {"name": "New Name", "level_reading": "B1"})
        learner = get_learner(self.conn, lid)
        self.assertEqual(learner["name"], "New Name")
        self.assertEqual(learner["level_reading"], "B1")

    def test_delete_learner(self) -> None:
        lid = create_learner(self.conn, "To Delete")
        self.assertTrue(delete_learner(self.conn, lid))
        self.assertIsNone(get_learner(self.conn, lid))

    def test_get_nonexistent_learner(self) -> None:
        self.assertIsNone(get_learner(self.conn, 9999))

    # -- Content Items --

    def test_create_and_get_content_item(self) -> None:
        cid = create_content_item(
            self.conn,
            type="chunk",
            situation="parenting",
            cefr_level="A1",
            target_structure="present",
            content_json={"fr": "bonjour"},
        )
        item = get_content_item(self.conn, cid)
        self.assertIsNotNone(item)
        self.assertEqual(item["type"], "chunk")
        self.assertIn("bonjour", item["content_json"])

    def test_get_all_content_items(self) -> None:
        create_content_item(self.conn, type="a", situation="s", cefr_level="A1", target_structure="t")
        create_content_item(self.conn, type="b", situation="s", cefr_level="A2", target_structure="t")
        self.assertEqual(len(get_all_content_items(self.conn)), 2)

    # -- Cards --

    def test_create_and_get_card(self) -> None:
        lid = create_learner(self.conn, "L")
        cid = create_content_item(self.conn, type="t", situation="s", cefr_level="A1", target_structure="t")
        kid = create_card(self.conn, lid, cid)
        card = get_card(self.conn, kid)
        self.assertIsNotNone(card)
        self.assertEqual(card["state"], "new")
        self.assertEqual(card["learner_id"], lid)

    def test_get_cards_for_learner(self) -> None:
        lid = create_learner(self.conn, "L")
        cid = create_content_item(self.conn, type="t", situation="s", cefr_level="A1", target_structure="t")
        create_card(self.conn, lid, cid)
        create_card(self.conn, lid, cid)
        cards = get_cards_for_learner(self.conn, lid)
        self.assertEqual(len(cards), 2)

    def test_update_card(self) -> None:
        lid = create_learner(self.conn, "L")
        cid = create_content_item(self.conn, type="t", situation="s", cefr_level="A1", target_structure="t")
        kid = create_card(self.conn, lid, cid)
        update_card(self.conn, kid, {"state": "learning", "reps": 1})
        card = get_card(self.conn, kid)
        self.assertEqual(card["state"], "learning")
        self.assertEqual(card["reps"], 1)

    # -- Reviews --

    def test_create_and_get_reviews(self) -> None:
        lid = create_learner(self.conn, "L")
        cid = create_content_item(self.conn, type="t", situation="s", cefr_level="A1", target_structure="t")
        kid = create_card(self.conn, lid, cid)
        create_review(self.conn, kid, lid, 3)
        create_review(self.conn, kid, lid, 4)
        reviews = get_reviews_for_card(self.conn, kid)
        self.assertEqual(len(reviews), 2)

    # -- Sessions --

    def test_create_and_end_session(self) -> None:
        lid = create_learner(self.conn, "L")
        sid = create_session(self.conn, lid, "conversation", scenario="cafe")
        session = get_session(self.conn, sid)
        self.assertIsNotNone(session)
        self.assertIsNone(session["ended_at"])

        end_session(self.conn, sid, feedback_summary="Good work")
        session = get_session(self.conn, sid)
        self.assertIsNotNone(session["ended_at"])
        self.assertEqual(session["feedback_summary"], "Good work")

    # -- Error Patterns --

    def test_error_patterns(self) -> None:
        lid = create_learner(self.conn, "L")
        eid = create_error_pattern(self.conn, lid, "gender_agreement")
        patterns = get_error_patterns_for_learner(self.conn, lid)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["occurrence_count"], 1)

        increment_error_pattern(self.conn, eid)
        patterns = get_error_patterns_for_learner(self.conn, lid)
        self.assertEqual(patterns[0]["occurrence_count"], 2)

        resolve_error_pattern(self.conn, eid)
        patterns = get_error_patterns_for_learner(self.conn, lid)
        self.assertEqual(patterns[0]["resolved"], 1)

    # -- Seed Data --

    def test_seed_data(self) -> None:
        ids = seed_test_data(self.conn)
        self.assertEqual(len(ids["learners"]), 2)
        self.assertEqual(len(ids["content_items"]), 2)
        self.assertEqual(len(ids["cards"]), 2)
        self.assertEqual(len(ids["reviews"]), 1)
        self.assertEqual(len(ids["sessions"]), 1)
        self.assertEqual(len(ids["error_patterns"]), 1)


if __name__ == "__main__":
    unittest.main()
