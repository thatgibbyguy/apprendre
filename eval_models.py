"""Model evaluation harness for conversation engine.

Runs each candidate model through the neighbor scenario test protocol
from Model_Evaluation.md, using a simplified system prompt (no guard,
no anti-assistant directives). Scores each response and prints a
comparison table.

Usage:
    python eval_models.py
"""

import asyncio
import json
import re
import time

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_BASE = "http://localhost:11434"
TIMEOUT = 120.0

MODELS = [
    "mistral-small:latest",
    "llama3.1:8b",
    "gemma2:9b",
    "phi3:14b",
]

# Simplified system prompt — no guard, no banned phrases, no anti-assistant rants
SYSTEM_PROMPT_MINIMAL = """Tu es le voisin sympa d'à côté. Tu croises l'autre dans le couloir de l'immeuble.

Parle en français oral, niveau A1.
A1 : présent seulement, 1-2 phrases max, mots très simples.
Parle comme à l'oral : "on" pas "nous", pas de "ne" en négation, contractions (y'a, t'as, j'suis). Tutoie.

Tu es une vraie personne — réagis à ce que l'autre dit, pose des questions sur sa vie, partage des trucs sur toi."""

# Same prompt but with few-shot examples pre-seeded in conversation history
FEW_SHOT_EXAMPLES = [
    {"role": "assistant", "content": "Eh, salut ! Quoi de neuf ?"},
    {"role": "user", "content": "salut ! bah, pas grand-chose, et toi ?"},
    {"role": "assistant", "content": "Tranquille. J'ai fait les courses, là j'suis crevé."},
    {"role": "user", "content": "ah ouais, moi aussi j'dois y aller bientôt"},
    {"role": "assistant", "content": "Bon courage ! Y'a du monde le samedi."},
]

# Test protocol from Model_Evaluation.md
TEST_EXCHANGES = [
    # (starter is from AI, then user replies)
    {"role": "assistant", "content": "Eh, salut ! Quoi de neuf ?"},
    {"role": "user", "content": "pas trop. et toi, ça va?"},
    # AI responds → scored
    {"role": "user", "content": "il fait beau, non?"},
    # AI responds → scored
    {"role": "user", "content": "non, et toi?"},
    # AI responds → scored
]

# Assistant-brain detection patterns (same as production, for scoring)
ASSISTANT_BRAIN_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"comment\s+puis-je\s+t'aider",
        r"comment\s+puis-je\s+vous\s+aider",
        r"qu'est-ce\s+que\s+je\s+peux\s+faire\s+pour",
        r"en\s+quoi\s+puis-je",
        r"je\s+suis\s+là\s+pour\s+t'aider",
        r"je\s+suis\s+là\s+pour\s+vous\s+aider",
        r"n'hésite\s+pas\s+à\s+me",
        r"n'hésitez?\s+pas\s+à",
        r"si\s+tu\s+as\s+besoin\s+de\s+quelque\s+chose",
        r"si\s+vous\s+avez\s+besoin",
        r"je\s+peux\s+t'aider",
        r"je\s+peux\s+vous\s+aider",
        r"pour\s+t'aider",
        r"pour\s+vous\s+aider",
        r"faire\s+savoir",
        r"assistant",
        r"intelligence\s+artificielle",
        r"modèle\s+de\s+langage",
        r"IA",
    ]
]

# Complexity markers that shouldn't appear at A1
A1_COMPLEXITY_MARKERS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\baurais\b", r"\baurait\b", r"\bserais\b", r"\bserait\b",  # conditional
        r"\bavais\b", r"\bavait\b", r"\bétais\b", r"\bétait\b",      # imparfait
        r"\bpourrait\b", r"\bdevrait\b", r"\bvoudrait\b",            # conditional
        r"\bbien\s+que\b", r"\bafin\s+de\b", r"\btandis\s+que\b",    # complex connectors
        r"\bnéanmoins\b", r"\btoutefois\b", r"\bcependant\b",        # literary connectors
        r"\bnous\b",                                                   # should use "on"
    ]
]


# ---------------------------------------------------------------------------
# Ollama API
# ---------------------------------------------------------------------------

async def ollama_chat(
    model: str,
    messages: list[dict],
    system: str = "",
    temperature: float = 0.7,
) -> tuple[str, float]:
    """Send a chat request, return (response_text, latency_seconds)."""
    # Separate system messages out (same workaround as production)
    chat_msgs = [m for m in messages if m["role"] != "system"]
    if not chat_msgs:
        chat_msgs = [{"role": "user", "content": "Continue."}]

    body = {
        "model": model,
        "messages": chat_msgs,
        "stream": False,
    }
    if system:
        body["system"] = system

    start = time.monotonic()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{OLLAMA_BASE}/api/chat", json=body)
        resp.raise_for_status()
    elapsed = time.monotonic() - start

    return resp.json()["message"]["content"], elapsed


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_response(text: str) -> dict:
    """Score a single AI response on the 5 evaluation criteria."""
    scores = {}

    # 1. Character adherence — any assistant-brain phrase = 0
    has_assistant = any(p.search(text) for p in ASSISTANT_BRAIN_PATTERNS)
    scores["character"] = 0 if has_assistant else 1
    scores["assistant_brain_match"] = has_assistant

    # 2. Level calibration — check for complexity markers
    complexity_hits = sum(1 for p in A1_COMPLEXITY_MARKERS if p.search(text))
    # Also check sentence count (A1 should be 1-2 sentences max)
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    sentence_count = len(sentences)
    # Score: 1 if no complexity markers and ≤2 sentences, 0.5 if minor issues, 0 if bad
    if complexity_hits == 0 and sentence_count <= 2:
        scores["level"] = 1.0
    elif complexity_hits <= 1 and sentence_count <= 3:
        scores["level"] = 0.5
    else:
        scores["level"] = 0.0
    scores["complexity_hits"] = complexity_hits
    scores["sentence_count"] = sentence_count

    # 3. Conversational naturalness — heuristic: does it ask a question or
    #    share something personal? (not just a flat statement)
    has_question = "?" in text
    has_personal = any(
        w in text.lower()
        for w in ["moi", "j'", "je ", "mon ", "ma ", "mes "]
    )
    scores["natural"] = 1.0 if (has_question or has_personal) else 0.5

    # 4. Word count (proxy for conciseness at A1)
    word_count = len(text.split())
    scores["word_count"] = word_count
    scores["concise"] = 1.0 if word_count <= 20 else (0.5 if word_count <= 35 else 0.0)

    return scores


# ---------------------------------------------------------------------------
# Run evaluation for one model
# ---------------------------------------------------------------------------

async def evaluate_model(model: str, use_few_shot: bool = False) -> dict:
    """Run the test protocol against a model, return results."""
    print(f"\n{'='*60}")
    label = f"{model} ({'few-shot' if use_few_shot else 'zero-shot'})"
    print(f"  Evaluating: {label}")
    print(f"{'='*60}")

    # Build initial conversation
    conversation: list[dict] = []
    if use_few_shot:
        conversation.extend(FEW_SHOT_EXAMPLES)

    # Add the starter message
    conversation.append(TEST_EXCHANGES[0])  # assistant starter

    responses = []
    total_latency = 0.0

    # Walk through user messages and collect AI responses
    user_turns = [t for t in TEST_EXCHANGES if t["role"] == "user"]

    for i, user_turn in enumerate(user_turns):
        conversation.append(user_turn)

        try:
            ai_text, latency = await ollama_chat(
                model,
                conversation,
                system=SYSTEM_PROMPT_MINIMAL,
                temperature=0.7,
            )
        except Exception as e:
            print(f"  ERROR on turn {i+1}: {e}")
            responses.append({
                "turn": i + 1,
                "user": user_turn["content"],
                "ai": f"[ERROR: {e}]",
                "latency": 0,
                "scores": {"character": 0, "level": 0, "natural": 0, "concise": 0},
            })
            continue

        total_latency += latency
        scores = score_response(ai_text)

        conversation.append({"role": "assistant", "content": ai_text})

        print(f"\n  Turn {i+1}:")
        print(f"    User: {user_turn['content']}")
        print(f"    AI:   {ai_text}")
        print(f"    Time: {latency:.1f}s")
        print(f"    Scores: char={scores['character']} level={scores['level']} "
              f"natural={scores['natural']} concise={scores['concise']} "
              f"({scores['word_count']} words, {scores['sentence_count']} sentences)")
        if scores.get("assistant_brain_match"):
            print(f"    ⚠ ASSISTANT BRAIN DETECTED")
        if scores.get("complexity_hits", 0) > 0:
            print(f"    ⚠ Complexity markers: {scores['complexity_hits']}")

        responses.append({
            "turn": i + 1,
            "user": user_turn["content"],
            "ai": ai_text,
            "latency": latency,
            "scores": scores,
        })

    # Aggregate scores
    n = len(responses)
    if n == 0:
        return {"model": label, "responses": [], "avg_scores": {}, "total_latency": 0}

    avg = {
        "character": sum(r["scores"]["character"] for r in responses) / n,
        "level": sum(r["scores"]["level"] for r in responses) / n,
        "natural": sum(r["scores"]["natural"] for r in responses) / n,
        "concise": sum(r["scores"]["concise"] for r in responses) / n,
    }
    avg["overall"] = sum(avg.values()) / len(avg)
    avg["avg_latency"] = total_latency / n

    return {
        "model": label,
        "responses": responses,
        "avg_scores": avg,
        "total_latency": total_latency,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    # Check which models are available
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(f"{OLLAMA_BASE}/api/tags")
        resp.raise_for_status()
    installed = {m["name"] for m in resp.json()["models"]}
    print(f"Installed models: {', '.join(sorted(installed))}")

    available_models = []
    for m in MODELS:
        if m in installed:
            available_models.append(m)
        else:
            # Try without tag
            base = m.split(":")[0]
            matches = [i for i in installed if i.startswith(base)]
            if matches:
                available_models.append(matches[0])
                print(f"  Using {matches[0]} for {m}")
            else:
                print(f"  SKIPPING {m} — not installed")

    if not available_models:
        print("No models available to test!")
        return

    # Run evaluations: each model in both zero-shot and few-shot modes
    all_results = []
    for model in available_models:
        result_zero = await evaluate_model(model, use_few_shot=False)
        all_results.append(result_zero)

        result_few = await evaluate_model(model, use_few_shot=True)
        all_results.append(result_few)

    # Print comparison table
    print(f"\n\n{'='*80}")
    print("  COMPARISON TABLE")
    print(f"{'='*80}")
    print(f"{'Model':<35} {'Char':>5} {'Level':>6} {'Natur':>6} {'Conc':>6} {'Overall':>8} {'Lat(s)':>7}")
    print(f"{'-'*35} {'-'*5} {'-'*6} {'-'*6} {'-'*6} {'-'*8} {'-'*7}")

    for r in sorted(all_results, key=lambda x: x["avg_scores"].get("overall", 0), reverse=True):
        a = r["avg_scores"]
        if not a:
            continue
        print(
            f"{r['model']:<35} "
            f"{a['character']:>5.2f} "
            f"{a['level']:>6.2f} "
            f"{a['natural']:>6.2f} "
            f"{a['concise']:>6.2f} "
            f"{a['overall']:>8.2f} "
            f"{a['avg_latency']:>7.1f}"
        )

    # Disqualification check
    print(f"\n{'='*80}")
    print("  DISQUALIFICATION CHECK (assistant-brain on any turn = disqualified)")
    print(f"{'='*80}")
    for r in all_results:
        disqualified = any(
            resp["scores"].get("assistant_brain_match", False)
            for resp in r["responses"]
        )
        status = "DISQUALIFIED" if disqualified else "PASSED"
        print(f"  {r['model']:<35} {status}")

    # Save raw results
    output_path = "eval_results.json"
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nRaw results saved to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
