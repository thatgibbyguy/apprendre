"""Seed the database with test learners for development.

Run:  python3 -m server.seed
"""

from server.models.database import get_connection, init_db, create_learner

LEARNERS = [
    {
        "name": "Alice (Beginner)",
        "level_speaking": "A1",
        "level_listening": "A1",
        "level_reading": "A1",
        "level_writing": "A1",
        "instruction_language": "en",
    },
    {
        "name": "Bob (Elementary)",
        "level_speaking": "A2",
        "level_listening": "A2",
        "level_reading": "A2",
        "level_writing": "A1",
        "instruction_language": "en",
    },
    {
        "name": "Clara (Intermediate)",
        "level_speaking": "B1",
        "level_listening": "B1",
        "level_reading": "B2",
        "level_writing": "B1",
        "instruction_language": "en",
    },
    {
        "name": "David (Upper-Inter)",
        "level_speaking": "B2",
        "level_listening": "B2",
        "level_reading": "B2",
        "level_writing": "B2",
        "instruction_language": "en",
    },
]


def seed():
    init_db()
    conn = get_connection()

    existing = conn.execute("SELECT name FROM learners").fetchall()
    existing_names = {r["name"] for r in existing}

    created = 0
    for learner in LEARNERS:
        if learner["name"] in existing_names:
            print(f"  skip  {learner['name']} (exists)")
            continue
        lid = create_learner(
            conn,
            learner["name"],
            level_speaking=learner["level_speaking"],
            level_listening=learner["level_listening"],
            level_reading=learner["level_reading"],
            level_writing=learner["level_writing"],
            instruction_language=learner["instruction_language"],
        )
        print(f"  created  {learner['name']}  (id={lid})")
        created += 1

    conn.close()
    print(f"\nDone. {created} learner(s) created.")


if __name__ == "__main__":
    seed()
