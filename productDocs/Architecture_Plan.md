# Architecture Plan: Apprendre — French Learning Tool

**Date:** March 20, 2026
**Status:** Draft

---

## 1. Tech Stack

| Component | Choice | Notes |
|---|---|---|
| **Frontend** | HTML/CSS (ply-css) + minimal vanilla JS | ply-css framework. Mobile via WebView wrapper (Capacitor/Tauri Mobile) |
| **Backend** | Python (FastAPI) | Serves pages, orchestrates AI/audio services |
| **AI Engine** | Ollama (Mistral/Llama locally) | Swappable provider interface for future Claude API upgrade |
| **Speech-to-Text** | faster-whisper (Python) | Local, free, good French accuracy |
| **Text-to-Speech** | Piper TTS (Python) | Local, free, French voices available |
| **SRS Algorithm** | py-fsrs | FSRS algorithm, 20-30% more efficient than SM-2 |
| **Database** | SQLite | Single file, no server, works offline |
| **Mobile** | WebView wrapper (Capacitor or Tauri Mobile) | Same web app, native shell |

**Cost: $0**

All components are open source and run locally. The architecture includes a provider abstraction for the AI engine so a paid API (Claude, etc.) can be swapped in later without changing application code.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────┐
│                  Browser / WebView           │
│  ┌──────────────────────────────────────┐   │
│  │   HTML/CSS Pages                      │   │
│  │   - Conversation UI                   │   │
│  │   - Lesson viewer                     │   │
│  │   - Drill/exercise interfaces         │   │
│  │   - Dashboard/progress                │   │
│  │   + Minimal JS (fetch, audio, DOM)    │   │
│  └──────────────┬───────────────────────┘   │
│                 │ fetch / WebSocket          │
└─────────────────┼───────────────────────────┘
                  │
┌─────────────────┼───────────────────────────┐
│  FastAPI Server │                            │
│  ┌──────────────┴───────────────────────┐   │
│  │   Routes & Session Management         │   │
│  │   - /api/conversation                 │   │
│  │   - /api/lessons                      │   │
│  │   - /api/drills                       │   │
│  │   - /api/exercises                    │   │
│  │   - /api/assessment                   │   │
│  │   - /api/audio (STT/TTS)             │   │
│  └──┬────────┬────────┬────────┬────────┘   │
│     │        │        │        │             │
│  ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──────────┐  │
│  │Ollama│ │FSRS │ │CEFR │ │Audio Engine │  │
│  │ LLM  │ │     │ │Level│ │Whisper+Piper│  │
│  └──────┘ └──┬──┘ └──┬──┘ └─────────────┘  │
│              │       │                       │
│           ┌──┴───────┴──┐                    │
│           │   SQLite     │                    │
│           │  - learners  │                    │
│           │  - cards     │                    │
│           │  - reviews   │                    │
│           │  - content   │                    │
│           │  - sessions  │                    │
│           │  - errors    │                    │
│           └──────────────┘                    │
└──────────────────────────────────────────────┘
```

---

## 3. Database Schema (Core Tables)

```sql
-- Learner profile with per-skill CEFR levels
learners (
    id, name,
    level_listening, level_reading, level_speaking, level_writing,
    instruction_language,  -- en/mixed/fr based on level
    created_at, updated_at
)

-- Content organized by functional situation
content_items (
    id, type,  -- chunk | grammar_point | scenario | exercise
    situation,  -- parenting | social | errands | narrating | opinions | written
    cefr_level, -- A1 | A2 | B1 | B2 | C1
    target_structure,  -- grammar/vocab being taught
    content_json,  -- flexible: sentences, dialogues, exercise data
    register  -- spoken | written | both
)

-- FSRS review cards
cards (
    id, learner_id, content_item_id,
    difficulty, stability, retrievability,  -- FSRS parameters
    due_date, last_review, reps, lapses,
    state  -- new | learning | review | relearning
)

-- Review history for analytics
review_history (
    id, card_id, learner_id,
    rating,  -- again | hard | good | easy
    review_date, elapsed_days, scheduled_days
)

-- Conversation sessions
sessions (
    id, learner_id, mode,  -- conversation | lesson | drill | exercise
    scenario, cefr_level,
    transcript_json,  -- full conversation log
    feedback_summary,
    started_at, ended_at
)

-- Anglophone error tracking
error_patterns (
    id, learner_id, error_type,
    -- e.g. "etre_vs_avoir_age", "pc_vs_imparfait", "gender"
    occurrence_count, last_seen,
    resolved  -- boolean: has learner stopped making this error?
)
```

---

## 4. AI Provider Abstraction

```python
# Swappable AI backend
class AIProvider(Protocol):
    def chat(self, messages: list[dict], system: str) -> str: ...
    def stream(self, messages: list[dict], system: str) -> Iterator[str]: ...

class OllamaProvider(AIProvider):
    """Free, local. Uses Mistral or Llama via Ollama."""
    ...

class ClaudeProvider(AIProvider):
    """Paid upgrade path. Better conversation quality."""
    ...
```

To mitigate local model quality limitations:
- **Rule-based feedback selection** — application logic determines feedback type (recast/prompt/metalinguistic), model just generates within that constraint
- **Heavily structured system prompts** — narrow the model's role per interaction type
- **Template-assisted generation** — provide sentence frames the model fills in rather than open-ended generation
- **Conversation scaffolding** — pre-built scenario structures with branching paths, model handles transitions

---

## 5. Execution Plan

### Phase 1: Foundation (Parallel) — All agents

| Task | Effort | Agent | Description | Done When |
|---|---|---|---|---|
| 1A: Project scaffolding | S | BE | FastAPI project, folder structure, dev tooling | Server starts, serves a test page |
| 1B: Database schema | M | BE | SQLite schema, migrations, data access layer | Can CRUD all core tables |
| 1C: Design system | M | Designer | Color palette, typography, spacing, component library, core page wireframes | Design tokens defined, key pages wireframed |
| 1D: Frontend shell | M | FE | Implement design system in ply-css, nav, page templates, conversation UI skeleton | Pages render, responsive, match designs |
| 1E: Content data model + A1 seed | M | PM | Define content structure, curate initial A1 chunks/scenarios/exercises | A1 content queryable by situation and level |

### Phase 2: Core Engine (Sequential after Phase 1)

| Task | Effort | Agent | Depends On | Description | Done When |
|---|---|---|---|---|---|
| 2A: FSRS engine | M | BE | 1B, 1E | Integrate py-fsrs, card scheduling, review session logic | Cards schedule correctly across sessions |
| 2B: CEFR level system | M | BE | 1B | Initial assessment flow, per-skill tracking, reassessment | Can assess and track uneven profiles |
| 2C: Conversation engine | L | BE | 1B, 1E, 2B | Ollama integration, system prompts, scenario selection, feedback logic | Text conversation works with calibrated feedback |
| 2D: Conversation UI design | M | Designer | 1C | Detailed conversation screen designs, feedback type visual treatments | Conversation UI fully designed |
| 2E: Conversation UI | M | FE | 1D, 2C, 2D | Chat interface, message rendering, feedback display | Can have a conversation in the browser |

### Phase 3: Audio (Sequential after Phase 2)

| Task | Effort | Agent | Depends On | Description | Done When |
|---|---|---|---|---|---|
| 3A: TTS integration | M | BE | 2C | Piper TTS, accent selection, audio endpoint | AI responses play as audio |
| 3B: STT integration | M | BE | 2C | faster-whisper, recording endpoint, transcription pipeline | Spoken input transcribed correctly |
| 3C: Audio UI | M | FE | 2E, 3A, 3B | Record button, audio playback, accent selector | Can speak and hear in conversation |

### Phase 4: Learning Modes (Parallel after Phase 2)

| Task | Effort | Agent | Depends On | Description | Done When |
|---|---|---|---|---|---|
| 4A: Structured lessons | L | BE+FE | 2A, 2B, 2C | EPI lesson flow: input flood → noticing → pushed output → feedback | Full lesson cycle works |
| 4B: Vocabulary drilling | M | BE+FE | 2A | Review UI, multiple task types, both directions, always in context | Review session with varied tasks |
| 4C: Interactive exercises | M | BE+FE | 1E, 2B | Conjugation trainer, gender practice, sentence builders | Exercises matched to CEFR level |

### Phase 5: Polish

| Task | Effort | Agent | Depends On | Description | Done When |
|---|---|---|---|---|---|
| 5A: Session structure | S | BE | 2C | Opening greeting/recall, closing summary/suggestions | Consistent session arc |
| 5B: Error analytics | S | BE+FE+Designer | 2C | Track anglophone errors, surface trends, adapt content | Error dashboard visible |
| 5C: Mobile WebView | M | FE | All | Capacitor/Tauri wrapper, test on device | Installable app works |
| 5D: Content expansion | L | PM | 1E | Expand content to A2, B1, B2. Curate authentic materials | Full A1-B2 content library |

### Dependency Map

```
1A (scaffold) ──────────────────────────────────────────┐
1B (database) ──┬──> 2A (SRS) ──┬──> 4B (drills)       │
                │               │                       │
1C (design) ──> 1D (frontend) ──┼──> 2E (conv UI) ──> 3C (audio UI) ──> 5C (mobile)
                │               │                       │
1E (content) ──┤   2B (level) ─┤──> 4C (exercises)     │
                │               │                       │
                └──> 2C (conversation) ──┬──> 3A (TTS) ──┐
                     2D (conv design) ──>├──> 3B (STT) ──┤
                                        ├──> 4A (lessons)│
                                        ├──> 5A (session)│
                                        └──> 5B (errors) │
                                                         └──> 3C (audio UI)
```

---

## 6. Worker Agent Roles

### BE (Backend Engineer)
**Scope:** Python/FastAPI, database, AI integration, audio processing

Core responsibilities:
- FastAPI server, routing, session management
- SQLite schema, migrations, data access
- Ollama integration + AI provider abstraction
- FSRS engine (py-fsrs) for spaced retrieval
- CEFR assessment and level tracking
- System prompt engineering for conversation quality
- faster-whisper (STT) and Piper TTS integration
- Rule-based feedback type selection logic
- Error pattern tracking and analytics
- API endpoints for all learning modes

### Designer (UX/UI Designer)
**Scope:** Visual design, interaction design, design system, user experience

Core responsibilities:
- Design system: color palette, typography, spacing scale, component library
- Page-level layouts and wireframes for all learning modes
- Conversation UI design: chat bubbles, feedback indicators, typing states
- Drill/exercise interaction patterns: how gap-fills, sentence builders, conjugation grids look and feel
- Progress visualization design: level indicators, review stats, error dashboards
- Responsive design specs: desktop, tablet, mobile breakpoints
- Audio interaction design: record states, playback controls, accent selector
- Accessibility: contrast, font sizing, focus states, screen reader considerations
- Onboarding and assessment flow design
- Visual hierarchy for feedback types (recasts vs. prompts vs. metalinguistic cues)

### FE (Frontend Engineer)
**Scope:** HTML, CSS (ply-css), minimal JS, browser audio APIs, mobile wrapper

Core responsibilities:
- Implement designs using ply-css framework
- Page layouts: conversation, lessons, drills, exercises, dashboard
- Responsive implementation (works on phone browsers and WebView)
- Conversation UI: chat bubbles, feedback display, typing indicators
- Audio UI: record button, playback controls, accent selector
- Drill/exercise interfaces: gap-fills, multiple choice, sentence builders, conjugation grids
- Progress visualization (level indicators, review stats)
- Capacitor/Tauri WebView wrapper for mobile
- Minimal JS: fetch calls, DOM manipulation, MediaRecorder API for audio capture

### PM (Product Manager / Content Architect)
**Scope:** Content curation, pedagogy alignment, quality assurance

Core responsibilities:
- Define and organize content by functional situation and CEFR level
- Curate A1-B2 vocabulary chunks, grammar points, scenarios, exercises
- Ensure content follows EPI methodology (patterns first, rules later)
- Write/validate conversation scenarios grounded in real-life situations
- Define error taxonomy for anglophone learners
- Map grammar sequencing to functional need (not textbook order)
- Quality-check AI conversation output against pedagogical goals
- Curate authentic materials (YouTube, Reddit, news) for B1+ input
- Tag Louisiana French content appropriately
- Define DELF-aligned benchmark assessments
- Write session opening/closing templates by level
- Validate language of instruction transitions (English → French by level)

---

## 7. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Local LLM conversation quality | High | Rule-based feedback selection, structured prompts, template-assisted generation. Architect for swappable provider. |
| Hardware requirements for local models | Medium | Start with smaller models (Mistral 7B); test quality floor. Recommend minimum specs. |
| Piper TTS accent variety limited | Medium | Test available French voices early. Worst case: Metropolitan only for MVP. |
| Content creation volume (A1-B2) | High | PM agent prioritizes A1-A2 first. Use AI to draft, human to validate. |
| Pronunciation scoring without paid API | Medium | Defer to Phase 5+. Start with phonetic guidance only. |
| WebView performance on older phones | Low | HTML/CSS is lightweight. Test early on low-end device. |

---

## 8. MVP Definition

The MVP is **Phase 1 + Phase 2** — a working web app where you can:

1. Get assessed at a CEFR level
2. Have a text-based French conversation with AI feedback
3. Review vocabulary/chunks via spaced retrieval
4. See your error patterns

Audio (Phase 3), additional learning modes (Phase 4), and mobile wrapper (Phase 5) follow. Content starts at A1 and expands progressively.

---

## 9. Project Management: GitHub Issues

All tickets live in **GitHub Issues** at `thatgibbyguy/apprendre`.

### Label Structure

| Category | Labels | Purpose |
|---|---|---|
| **Agent** | `agent:BE`, `agent:FE`, `agent:Designer`, `agent:PM` | Who owns the work |
| **Phase** | `phase:1-foundation` through `phase:5-polish` | When it happens |
| **CEFR Level** | `level:A1`, `level:A2`, `level:B1`, `level:B2` | Content-level tagging |
| **Mode** | `mode:conversation`, `mode:lessons`, `mode:drills`, `mode:exercises` | Which learning mode |
| **Size** | `size:S`, `size:M`, `size:L` | Effort estimate |

### Conventions

- PM creates content tickets with CEFR level + situation labels
- Each execution plan task maps to one or more GitHub Issues
- Use GitHub Milestones for phases
- Issues reference architecture plan task IDs (e.g. "Task 2C: Conversation engine")
