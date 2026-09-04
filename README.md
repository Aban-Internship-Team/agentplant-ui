# AgentPlant — conversational plant modeling

Turn a natural-language description of a physical system into runnable
`dynamics(t, x, u)` Python, with human-in-the-loop clarification and an
open-loop simulation check before the model is accepted.

This repository is **self-contained**. It includes the AgentPlant agent,
FastAPI surface, shared LLM package, Streamlit reference UI, and an HTML
mockup that shows the intended chat experience.

---

## Layout

```
.
├── backend_api/AgentPlant/      # FastAPI (chat, drafts, artifacts)
├── backend_core/
│   ├── AgentPlant/              # PlantModelAgent, prompts, CLI
│   ├── plant_compiler.py        # validate plant + pre-launch → artifact
│   └── artifact_store.py        # filesystem artifact persistence
├── frontend_streamlit/          # reference UI (unified plant → pre-launch)
├── frontend_mockup/
│   └── labcd_chat.html          # interaction target (chat, HITL, sim pad)
├── packages/labcd_agents/       # shared LLM factory (editable install)
├── ASSIGNMENT.md                # frontend take-home brief
├── requirements.txt
└── .env.example
```

Imports are absolute from the repo root. Always run with `PYTHONPATH=.`.

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -e "packages/labcd_agents[all]"
pip install -r requirements.txt

cp .env.example .env
# Set at least one provider key: OPENAI_API_KEY, GROQ_API_KEY, …
```

---

## Run

**Streamlit (plant → pre-launch)**

```bash
PYTHONPATH=. streamlit run frontend_streamlit/unified_app.py
```

**Streamlit (AgentPlant only)**

```bash
PYTHONPATH=. streamlit run frontend_streamlit/agent_plant_app.py
```

**FastAPI**

```bash
PYTHONPATH=. uvicorn backend_api.AgentPlant.app:app --reload --port 8003
# OpenAPI: http://localhost:8003/docs
```

**CLI**

```bash
PYTHONPATH=. python backend_core/AgentPlant/run_cli.py
PYTHONPATH=. python backend_core/AgentPlant/run_cli.py --model gpt-4o
```

Default model: env `LABCD_DEMO_MODEL` (fallback `gpt-4o-mini`).

**Mockup (no server)**

Open `frontend_mockup/labcd_chat.html` in a browser. This is the visual and
interaction target for the React (or equivalent) frontend described in
`ASSIGNMENT.md`.

---

## AgentPlant statuses

| Status | Meaning |
|--------|---------|
| `continue` | Clarifying question |
| `draft` | Code + note; simulation pad can run |
| `complete` | User accepted; download `dynamics.py` |

See `backend_core/AgentPlant/GUIDE.md` for product rules and example dialogues.

---

## Frontend assignment

If you are implementing the assistant-style UI, start with **`ASSIGNMENT.md`**.
The mockup and FastAPI routes are the primary references; Streamlit is a
working but non-production reference flow.
