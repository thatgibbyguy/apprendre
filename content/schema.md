# Content Data Model

This document defines the JSON schema for all content types in the Apprendre French learning tool. Content is organized by **functional situation**, not grammar category, following EPI methodology: patterns first, rules later.

---

## Design Principles

- **Chunks as whole units** — "il y a", not "il" + "y" + "a"
- **Always with the article** — "le chat", never "chat"
- **Spoken register first** — "on" not "nous", "je sais pas" not "je ne sais pas"
- **Organized by situation** — what the learner needs to *do*, not what grammar rule applies
- **Grammar after exposure** — rules appear only after the learner has encountered the pattern through chunks and scenarios

---

## Content Types

### 1. Chunks

Vocabulary and grammar taught together as formulaic sequences (lexicogrammar). Each chunk is a high-frequency phrase learned as a whole unit.

```json
{
  "id": "string — unique identifier (e.g. 'a1-chunk-001')",
  "chunk": "string — the French phrase as a whole unit",
  "translation": "string — English translation",
  "example_sentence": "string — a natural French sentence using the chunk",
  "example_translation": "string — English translation of the example sentence",
  "situation": "string — functional situation: 'parenting', 'social', 'reactive', 'errands', 'narrating', 'opinions'",
  "cefr_level": "string — 'A1' | 'A2' | 'B1' | 'B2' | 'C1'",
  "register": "string — 'spoken' | 'written' | 'both'",
  "notes": "string | null — pronunciation, spoken vs. written forms, usage notes"
}
```

**Required fields:** id, chunk, translation, example_sentence, example_translation, situation, cefr_level, register

**Naming convention:** `{level}-chunk-{number}` (e.g. `a1-chunk-001`)

---

### 2. Scenarios

Conversation practice situations for the primary learning mode. Each scenario defines a real-life context, the AI's role, and which chunks/structures the learner should practice.

```json
{
  "id": "string — unique identifier (e.g. 'a1-scenario-001')",
  "title": "string — scenario title in English",
  "title_fr": "string — scenario title in French",
  "situation": "string — functional situation category",
  "cefr_level": "string — CEFR level",
  "description": "string — what the learner will do in this scenario",
  "ai_role": "string — who the AI plays in the conversation",
  "target_chunks": ["array of chunk IDs the scenario exercises"],
  "target_structures": ["array of grammar structures practiced"],
  "starter_prompt": "string — the AI's opening line (in French, level-appropriate)",
  "expected_output_type": "string — matched to CEFR text-type capacity (e.g. 'isolated phrases and simple sentences' for A1)",
  "feedback_focus": ["array of error types to prioritize in feedback"]
}
```

**Required fields:** all fields are required

**Naming convention:** `{level}-scenario-{number}` (e.g. `a1-scenario-001`)

---

### 3. Exercises

Structured practice activities for drilling specific chunks and grammar structures. Exercises are always contextualized — never isolated word lists.

```json
{
  "id": "string — unique identifier (e.g. 'a1-exercise-001')",
  "type": "string — 'gap_fill' | 'translation_en_fr' | 'translation_fr_en' | 'sentence_completion'",
  "situation": "string — functional situation category",
  "cefr_level": "string — CEFR level",
  "instruction": "string — what the learner should do",
  "prompt": "string — the question or sentence with gap",
  "answer": "string — the correct answer",
  "alternatives": ["array of plausible wrong answers (for gap_fill) or acceptable alternate answers (for translation)"],
  "target_structure": "string — the grammar point or chunk being practiced",
  "chunk_reference": "string | null — ID of the related chunk"
}
```

**Required fields:** id, type, situation, cefr_level, instruction, prompt, answer, target_structure

**Optional fields:** alternatives, chunk_reference

**Naming convention:** `{level}-exercise-{number}` (e.g. `a1-exercise-001`)

---

### 4. Grammar Points

Explicit grammar rules that appear AFTER the learner has encountered the pattern through chunks and scenarios. Grammar is sequenced by functional need ("you need this to say X"), not textbook order.

```json
{
  "id": "string — unique identifier (e.g. 'a1-grammar-001')",
  "title": "string — grammar point title in English",
  "cefr_level": "string — CEFR level",
  "situations": ["array of functional situations where this grammar appears"],
  "explanation_en": "string — clear English explanation",
  "explanation_fr": "string | null — French explanation (null at A1, increasingly used at higher levels)",
  "key_forms": "object — paradigm table as key-value pairs (e.g. {'je': 'suis', 'tu': 'es'})",
  "spoken_note": "string | null — how this works in spoken French vs. written",
  "related_chunks": ["array of chunk IDs that use this grammar point"],
  "common_errors": [
    {
      "error": "string — the mistake anglophones typically make",
      "correction": "string — the correct form",
      "explanation": "string — why this error happens and how to avoid it"
    }
  ]
}
```

**Required fields:** id, title, cefr_level, situations, explanation_en, key_forms, related_chunks, common_errors

**Optional fields:** explanation_fr, spoken_note

**Naming convention:** `{level}-grammar-{number}` (e.g. `a1-grammar-001`)

---

## Situation Taxonomy

Content is tagged with one of these functional situation categories:

| Situation | Description | Example contexts |
|-----------|-------------|-----------------|
| `parenting` | Parenting & family life | Playing with a child, reacting, narrating, giving instructions |
| `social` | Daily social exchanges | Greetings, small talk, making plans, catching up |
| `reactive` | Reactive language | Surprise, frustration, agreement, filler phrases |
| `errands` | Basic needs & errands | Ordering, shopping, asking for things, finding places |
| `narrating` | Narrating & reacting | Telling what happened, describing what's going on |
| `opinions` | Opinions & discussion | Giving your take, agreeing/disagreeing (B1+) |
| `written` | Written French | Email, messages, formal writing (treated as its own register) |

---

## CEFR Level Guidelines for Content

| Level | Chunk complexity | Scenario output | Exercise difficulty |
|-------|-----------------|-----------------|-------------------|
| A1 | Single phrases, formulaic sequences | Isolated phrases, simple sentences | Gap fill, simple translation |
| A2 | Short connected phrases, common irregulars | Short connected sentences, simple descriptions | Multi-word gaps, paragraph translation |
| B1 | Complex phrases, discourse connectors | Connected paragraphs, narration | Transformation, error correction |
| B2 | Register-specific, idiomatic | Detailed argumentation, register switching | Nuanced translation, style editing |

---

## File Organization

```
content/
  schema.md              — this file
  a1/
    chunks.json          — A1 vocabulary chunks
    scenarios.json       — A1 conversation scenarios
    exercises.json       — A1 exercise templates
    grammar_points.json  — A1 grammar points
  a2/
    ...
  b1/
    ...
  b2/
    ...
```

Each level directory contains the same four JSON files. All JSON files contain a top-level array of objects conforming to the schemas above.
