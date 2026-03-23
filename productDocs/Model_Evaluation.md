# Model Evaluation — Conversation Engine

## Current Model
**mistral-small:latest** (14 GB, ~24B params) via Ollama local inference.

## Problems

### 1. Assistant-brain (critical)
The model defaults to helper/service behavior regardless of system prompt. It produces phrases like:
- "Comment puis-je t'aider aujourd'hui ?"
- "N'hésite pas à me le faire savoir !"
- "Je suis là pour t'aider si tu as besoin de quelque chose"

This breaks immersion completely. The model is supposed to be a character (neighbor, café server, child's friend) but reverts to assistant mode within 1-2 turns.

**What we tried:**
- Banned phrases list in the system prompt — ignored
- Rewriting the entire system prompt in French to avoid English "assistant" framing — still happens
- Post-processing guard that detects helper phrases and retries with a correction injected (up to 2 retries at temperature 0.9) — the model produces the same pattern on retry, and the retries make response time worse

**Root cause:** mistral-small's RLHF training to be a helpful assistant overpowers any system prompt. This is a model-level limitation, not a prompt engineering problem.

### 2. Level calibration (A1 responses too complex)
At A1, the model produces B1-level French: compound sentences, low-frequency vocabulary, complex question forms. The prompt specifies "present tense only, 1-2 short sentences, top 500 words" but the model ignores these constraints.

Examples of actual A1 responses (should be simple like "Ah cool ! Tu fais quoi ?"):
- "D'accord, si tu as besoin de parler de quelque chose ou si tu as des questions, n'hésite pas à me le faire savoir !"
- "Je ne peux pas avoir de plans, mais je suis là pour t'aider si tu as besoin de quelque chose ou si tu veux discuter."

### 3. Response latency
With the assistant-brain guard retrying, responses can take 2-3x longer since each retry is a full LLM call. Even without retries, mistral-small is noticeably slower than mistral-nemo was.

## What's Working
- The curated starter prompts (no LLM call on session init) load instantly and sound natural
- The rule-based error detection for A1-A2 is fast and accurate — no false positives
- The feedback popover UI works well
- The post-processing guard correctly identifies assistant-brain phrases (the detection works, the model just can't stop producing them)

## Candidates to Evaluate

| Model | Size | Why consider |
|-------|------|-------------|
| llama3.1:8b | ~5 GB | Strong role-play, lighter, fast |
| gemma2:9b | ~5 GB | Good instruction following |
| phi3:14b | ~8 GB | Stays in character well |
| mistral-nemo:12b | ~7 GB | Previously used, faster, but had same issues to lesser degree |
| llama3.1:70b | ~40 GB | Best quality but may be too large for local inference |

## Evaluation Criteria
1. **Character adherence** — Does it stay in role without reverting to assistant behavior?
2. **Level calibration** — Can it produce genuine A1 French (simple, short, high-frequency)?
3. **Conversational naturalness** — Does it sound like a real person, not a chatbot?
4. **Latency** — Response time under 3 seconds on local hardware
5. **Size** — Must run locally on available hardware

## Test Protocol
Run each candidate through the neighbor scenario (a1-scenario-002):
1. Starter: "Eh, salut ! Quoi de neuf ?"
2. User: "pas trop. et toi, ça va?"
3. User: "il fait beau, non?"
4. User: "non, et toi?"

Score each response on the 5 criteria above. A model that says "comment puis-je t'aider" even once is disqualified.
