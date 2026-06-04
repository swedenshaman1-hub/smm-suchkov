# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**SMM-команда Дмитрия Сучкова** — a multi-agent AI system for generating social media content (Telegram + Instagram) for psychologist Dmitry Suchkov (GREM method, "Танец Души" practice). The target audience is burned-out women leaders aged 28–50.

## Commands

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Run the app:**
```bash
streamlit run app.py
```
Accessible at http://localhost:8501

**Windows shortcut:** `ЗАПУСК.bat`

**No test suite or linter is configured** — there are no test files or linting configs in this project.

## Environment Setup

Create a `.env` file in the project root:
```
GROQ_API_KEY=your_key_here
```

The `memory/` directory is created automatically at runtime and is git-ignored. Clearing agent memory is available via the sidebar button in the UI.

## Architecture

### Agent Pipeline (`app.py` → `agents/`)

The app orchestrates 8 agents in a fixed sequential pipeline. Each agent is a standalone module in `agents/` with a `run()` function. The pipeline in order:

1. **Нина** (`analyst.py`) — analyzes target audience pain points for the given topic
2. **Артём** (`strategist.py`) — builds content strategy and conversion angle
3. **Олег** (`marketer.py`) — evaluates marketing/conversion potential
4. **Маша** (`copywriter.py`) — writes Telegram, Instagram, and YouTube texts
5. **Катя** (`instagram_writer.py`) — specialized Instagram content (visual hooks, brevity)
6. **Игорь** (`editor.py`) — reviews both texts against 7 criteria; returns `accepted: bool`
7. Steps 4–6 repeat up to **2 iterations** if the editor rejects; on the 2nd rejection the best text is published anyway
8. **Рита** — publication scheduling (implemented inline in `app.py`, not a separate module)
9. **Соня** (`publisher.py`) — final formatting with hashtags and timing

### Agent Memory System

Every agent maintains a JSON file in `memory/` (e.g. `memory/analyst_memory.json`). The pattern is identical across all agents:

- `load_memory()` / `save_memory()` — read/write JSON
- After each run, the agent makes a second "reflection" LLM call to extract 1–2 lessons
- Lessons are prepended to the system prompt on the next run (last 5 lessons)
- Memory arrays are capped (analyses: 10, lessons: 20, etc.) to avoid unbounded growth

### Agent Module Interface

Every agent module follows this contract:
```python
def run(topic: str, ..., api_key: str, ...) -> dict:
    # Returns a dict with at minimum: "agent", "topic", and the primary output key
    # e.g. analyst returns {"agent": ..., "topic": ..., "analysis": ..., "new_lessons": ...}
```

All agents use model `llama-3.3-70b-versatile` via Groq API. The system prompt is the personality + role definition; it never changes between agents — only the injected memory context changes at runtime.

### Editor Decision Logic

The editor (`editor.py`) is the only agent that gates the pipeline. Its output text must contain `"РЕШЕНИЕ: ПРИНЯТО"` (and not `"РЕШЕНИЕ: ОТКЛОНЕНО"`) for `accepted` to be `True`. The `app.py` loop uses this to decide whether to iterate or finalize.

**Editor stop-words** (auto-reject triggers): «вибрации высокие/низкие», «Вселенная хочет», «100% результат», «гарантированно», «уникальная методика» без объяснения, «в современном мире», «как никогда раньше».

### Content Rules (enforced in agent prompts)

- Telegram posts: 800–1500 characters
- Instagram posts: 300–800 characters; first 90 characters are critical
- Esoteric language: max 20% of content
- No categorical guarantees
- Voice: direct, grounded, scientific but alive — never guru-like

## Key Conventions

- All LLM output and UI text is in **Russian only**
- The Groq client is instantiated fresh in each `run()` call — no shared client instance
- `app.py` uses `st.session_state` to persist topic and running state across Streamlit reruns
- Rita's agent (step 8) is not a module — it is implemented directly in `app.py` with an inline `Groq()` call
- `agents/__init__.py` is empty; imports in `app.py` are explicit per-module
