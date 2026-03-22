"""Tests for the CEFR adaptive level system."""

import sqlite3
import unittest

from server.models.database import create_content_item, create_learner, init_db
from server.services.level_system import (
    CEFR_ORDER,
    SESSIONS_REQUIRED_FOR_CHANGE,
    assess_initial_level,
    get_current_levels,
    get_scenarios_for_level,
    is_above,
    level_down,
    level_up,
    update_level_from_session,
)


def _make_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the full schema initialised."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    from server.models.database import SCHEMA_SQL
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


class TestCefrHelpers(unittest.TestCase):
    """Unit tests for the pure helper functions."""

    def test_cefr_order_integrity(self) -> None:
        self.assertEqual(CEFR_ORDER, ["A1", "A2", "B1", "B2"])

    def test_level_up_normal(self) -> None:
        self.assertEqual(level_up("A1"), "A2")
        self.assertEqual(level_up("A2"), "B1")
        self.assertEqual(level_up("B1"), "B2")

    def test_level_up_ceiling(self) -> None:
        self.assertEqual(level_up("B2"), "B2")

    def test_level_down_normal(self) -> None:
        self.assertEqual(level_down("B2"), "B1")
        self.assertEqual(level_down("B1"), "A2")
        self.assertEqual(level_down("A2"), "A1")

    def test_level_down_floor(self) -> None:
        self.assertEqual(level_down("A1"), "A1")

    def test_is_above_true(self) -> None:
        self.assertTrue(is_above("A2", "A1"))
        self.assertTrue(is_above("B2", "A1"))
        self.assertTrue(is_above("B1", "A2"))

    def test_is_above_false_equal(self) -> None:
        self.assertFalse(is_above("A1", "A1"))

    def test_is_above_false_lower(self) -> None:
        self.assertFalse(is_above("A1", "B1"))


class TestGetCurrentLevels(unittest.TestCase):

    def setUp(self) -> None:
        self.conn = _make_conn()
        self.learner_id = create_learner(
            self.conn, "Marie",
            level_listening="A2",
            level_reading="B1",
            level_speaking="A1",
            level_writing="A2",
        )

    def test_returns_all_four_skills(self) -> None:
        levels = get_current_levels(self.conn, self.learner_id)
        self.assertEqual(set(levels.keys()), {"listening", "reading", "speaking", "writing"})

    def test_values_match_db(self) -> None:
        levels = get_current_levels(self.conn, self.learner_id)
        self.assertEqual(levels["listening"], "A2")
        self.assertEqual(levels["reading"], "B1")
        self.assertEqual(levels["speaking"], "A1")
        self.assertEqual(levels["writing"], "A2")

    def test_raises_for_missing_learner(self) -> None:
        with self.assertRaises(ValueError):
            get_current_levels(self.conn, 9999)


class TestAssessInitialLevel(unittest.TestCase):

    def setUp(self) -> None:
        self.conn = _make_conn()
        self.learner_id = create_learner(self.conn, "Paul")

    def test_empty_responses_defaults_to_a1(self) -> None:
        levels = assess_initial_level(self.conn, self.learner_id, [])
        for skill in ["listening", "reading", "speaking", "writing"]:
            self.assertEqual(levels[skill], "A1")

    def test_minimal_responses_a1(self) -> None:
        levels = assess_initial_level(self.conn, self.learner_id, ["Oui. Non. Merci."])
        for skill in levels:
            self.assertEqual(levels[skill], "A1")

    def test_a2_detection(self) -> None:
        # passé composé, sufficient unique words, longer sentences
        responses = [
            "Hier, j'ai mangé une pomme et j'ai bu du café avec mon ami.",
            "Nous avons visité le musée parce que c'était intéressant.",
            "Ma sœur a travaillé toute la journée ensuite elle est rentrée chez elle.",
            "D'abord je suis allé au marché puis j'ai préparé le dîner pour la famille.",
            "Tu sais, pendant les vacances nous avons voyagé en Bretagne avec les enfants.",
        ]
        levels = assess_initial_level(self.conn, self.learner_id, responses)
        for skill in levels:
            self.assertIn(levels[skill], ["A2", "B1"])

    def test_persists_to_db(self) -> None:
        responses = ["Je suis. Tu es. Il est. Nous sommes. Vous êtes."]
        assess_initial_level(self.conn, self.learner_id, responses)
        db_levels = get_current_levels(self.conn, self.learner_id)
        # All four skills updated identically
        unique = set(db_levels.values())
        self.assertEqual(len(unique), 1)

    def test_raises_for_missing_learner(self) -> None:
        with self.assertRaises(ValueError):
            assess_initial_level(self.conn, 9999, ["Bonjour."])


class TestUpdateLevelFromSession(unittest.TestCase):

    def setUp(self) -> None:
        self.conn = _make_conn()
        self.learner_id = create_learner(self.conn, "Lucie", level_speaking="A1")

    def _session(self, **kwargs) -> dict:
        """Build a minimal session_data dict, allow overrides."""
        base = {
            "skill": "speaking",
            "error_count": 0,
            "exchange_count": 10,
            "structures_used": [],
            "cefr_level": "A1",
        }
        base.update(kwargs)
        return base

    def test_no_change_on_first_good_session(self) -> None:
        result = update_level_from_session(
            self.conn, self.learner_id,
            self._session(error_count=0, exchange_count=10, structures_used=["passé composé"])
        )
        self.assertFalse(result["changed"])

    def test_level_up_after_required_sessions(self) -> None:
        session = self._session(
            error_count=1,
            exchange_count=10,
            structures_used=["passé composé"],
            cefr_level="A1",
        )
        results = []
        for _ in range(SESSIONS_REQUIRED_FOR_CHANGE):
            results.append(update_level_from_session(self.conn, self.learner_id, session))

        # Last result should indicate a change
        final = results[-1]
        self.assertTrue(final["changed"])
        self.assertEqual(final["skill"], "speaking")
        self.assertEqual(final["old_level"], "A1")
        self.assertEqual(final["new_level"], "A2")

    def test_level_persisted_in_db_after_change(self) -> None:
        session = self._session(
            error_count=1,
            exchange_count=10,
            structures_used=["passé composé"],
        )
        for _ in range(SESSIONS_REQUIRED_FOR_CHANGE):
            update_level_from_session(self.conn, self.learner_id, session)

        levels = get_current_levels(self.conn, self.learner_id)
        self.assertEqual(levels["speaking"], "A2")

    def test_inconsistent_signal_resets_counter(self) -> None:
        good_session = self._session(error_count=1, exchange_count=10, structures_used=["passé composé"])
        bad_session = self._session(error_count=8, exchange_count=10, structures_used=[])

        # Two good, then one bad — should reset
        update_level_from_session(self.conn, self.learner_id, good_session)
        update_level_from_session(self.conn, self.learner_id, good_session)
        update_level_from_session(self.conn, self.learner_id, bad_session)

        # Now need another full run of good sessions
        for i in range(SESSIONS_REQUIRED_FOR_CHANGE):
            result = update_level_from_session(self.conn, self.learner_id, good_session)
        self.assertTrue(result["changed"])

    def test_level_down_after_sustained_high_errors(self) -> None:
        # Start at A2, see high errors
        learner_id = create_learner(self.conn, "Henri", level_speaking="A2")
        session = self._session(error_count=7, exchange_count=10, structures_used=[], cefr_level="A2")

        results = []
        for _ in range(SESSIONS_REQUIRED_FOR_CHANGE):
            results.append(update_level_from_session(self.conn, learner_id, session))

        final = results[-1]
        self.assertTrue(final["changed"])
        self.assertEqual(final["old_level"], "A2")
        self.assertEqual(final["new_level"], "A1")

    def test_no_change_at_ceiling(self) -> None:
        learner_id = create_learner(self.conn, "Sophie", level_speaking="B2")
        session = self._session(
            error_count=0,
            exchange_count=10,
            structures_used=["subjunctive", "conditionnel"],
            cefr_level="B2",
        )
        for _ in range(SESSIONS_REQUIRED_FOR_CHANGE + 1):
            result = update_level_from_session(self.conn, learner_id, session)
        self.assertFalse(result["changed"])

    def test_no_change_at_floor(self) -> None:
        # A1 learner with high errors — can't go lower
        session = self._session(error_count=9, exchange_count=10, structures_used=[], cefr_level="A1")
        for _ in range(SESSIONS_REQUIRED_FOR_CHANGE + 1):
            result = update_level_from_session(self.conn, self.learner_id, session)
        self.assertFalse(result["changed"])

    def test_raises_for_invalid_skill(self) -> None:
        with self.assertRaises(ValueError):
            update_level_from_session(
                self.conn, self.learner_id,
                {"skill": "dancing", "error_count": 0, "exchange_count": 5,
                 "structures_used": [], "cefr_level": "A1"},
            )

    def test_raises_for_invalid_cefr_level(self) -> None:
        with self.assertRaises(ValueError):
            update_level_from_session(
                self.conn, self.learner_id,
                {"skill": "speaking", "error_count": 0, "exchange_count": 5,
                 "structures_used": [], "cefr_level": "C2"},
            )


class TestGetScenariosForLevel(unittest.TestCase):

    def setUp(self) -> None:
        self.conn = _make_conn()
        self.learner_id = create_learner(self.conn, "Camille", level_speaking="A1")

    def test_returns_matching_scenarios(self) -> None:
        create_content_item(
            self.conn, type="scenario", situation="parenting",
            cefr_level="A1", target_structure="present_tense",
        )
        create_content_item(
            self.conn, type="scenario", situation="social",
            cefr_level="A2", target_structure="passe_compose",
        )
        scenarios = get_scenarios_for_level(self.conn, self.learner_id)
        self.assertEqual(len(scenarios), 1)
        self.assertEqual(scenarios[0]["cefr_level"], "A1")

    def test_excludes_non_scenario_types(self) -> None:
        create_content_item(
            self.conn, type="chunk", situation="parenting",
            cefr_level="A1", target_structure="present_tense",
        )
        scenarios = get_scenarios_for_level(self.conn, self.learner_id)
        self.assertEqual(len(scenarios), 0)

    def test_returns_empty_list_when_none_available(self) -> None:
        scenarios = get_scenarios_for_level(self.conn, self.learner_id)
        self.assertEqual(scenarios, [])


if __name__ == "__main__":
    unittest.main()
