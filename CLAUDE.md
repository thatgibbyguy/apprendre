# Apprendre — French Learning Tool

## What This Is
An AI-powered French learning tool that combines structured grammar diagnostics with conversational practice under SLA research methodology (EPI + TBLT + spaced retrieval). See `productDocs/French_Learning_Tool_Product_Brief.md` for the full product vision.

## Tech Stack
- **Backend:** Python, FastAPI
- **Frontend:** HTML, CSS (ply-css framework), minimal vanilla JS
- **AI:** Ollama (local, Mistral/Llama) with swappable provider interface
- **STT:** faster-whisper (local)
- **TTS:** Piper TTS (local)
- **SRS:** py-fsrs (FSRS algorithm)
- **Database:** SQLite
- **Mobile:** WebView wrapper (Capacitor or Tauri Mobile)

## Project Structure
```
apprendre/
├── CLAUDE.md                    # This file
├── productDocs/                 # Product brief, architecture plan
├── skills/                      # Claude Code skills (architect, project-manager)
├── .claude/agents/              # Agent definitions (BE, FE, Designer, PM)
├── server/                      # FastAPI backend (Python)
├── static/                      # Frontend assets
│   ├── design-system/           # Designer owns: tokens, component CSS, prototypes
│   ├── css/                     # FE owns: production styles built on design-system
│   ├── js/                      # FE owns: vanilla JS
│   └── pages/                   # FE owns: production pages with API calls
└── content/                     # Learning content (chunks, scenarios, exercises)
```

## Conventions

### Python (Backend)
- Python 3.11+
- FastAPI for routing
- Type hints on all function signatures
- Tests alongside code in `tests/` directories
- SQLite access through a data access layer, not raw queries scattered in routes

### Frontend
- ply-css for CSS framework
- Semantic HTML, minimal JS
- No JS frameworks — vanilla JS with fetch for API calls
- Mobile-first responsive design

### Content
- Organized by functional situation (parenting, social, errands, narrating, opinions, written)
- Tagged with CEFR level (A1-B2) and register (spoken/written/both)
- Nouns always with articles
- Chunks as whole units
- Spoken register first

## Key Architecture Decisions
- **AI provider is swappable** — OllamaProvider now, ClaudeProvider later. All AI access goes through the provider abstraction.
- **Feedback type selection is rule-based** — application logic picks recast/prompt/metalinguistic cue, the LLM generates within that constraint.
- **Everything runs locally** — $0 cost. No external API dependencies.

## Project Management
- Tickets: GitHub Issues at thatgibbyguy/apprendre
- Labels: `agent:*`, `phase:*`, `level:*`, `mode:*`, `size:*`
- Architecture plan: `productDocs/Architecture_Plan.md`

## Agent Roles
- **BE (backend-developer):** Python/FastAPI, database, AI integration, audio
- **FE (frontend-developer):** HTML/CSS (ply-css), minimal JS, WebView wrapper
- **Designer:** Design system tokens, component CSS, HTML/CSS prototypes in `static/design-system/`. Reviews FE implementation.
- **PM (product-manager):** Content curation, pedagogy alignment, GitHub Issues
