# AgentPlant Frontend — Take-Home Exercise

**Project:** AgentPlant (conversational plant modeling)  
**Time we expect:** about 1–2 weeks (part-time) for 1–2 people  
**Stack:** React (or equivalent modern SPA) · TypeScript preferred · FastAPI backend provided in this repo  

---

## Why this exercise

AgentPlant turns natural-language descriptions of physical systems into runnable
plant models (`dynamics(t, x, u)`). Users clarify the system in chat, review a
draft, optionally run an open-loop simulation, and accept the model.

This repo already has a working agent + API and a Streamlit reference flow.
Your job is a **production-grade frontend** that feels like a modern AI
assistant (ChatGPT / Claude / Grok) while adding control-engineering
interactions that pure chat UIs lack.

Focus on **product and interaction design**. Backend and agent logic are
provided; stubs are fine where full RAG/search infrastructure would dominate
the schedule.

---

## What you have in this repo

```
.
├── backend_api/AgentPlant/     # FastAPI: conversations, drafts, artifacts
├── backend_core/AgentPlant/    # PlantModelAgent + prompts + CLI
├── frontend_streamlit/         # Reference flow (plant → pre-launch)
├── frontend_mockup/
│   └── labcd_chat.html         # Visual / interaction target
├── packages/labcd_agents/      # Shared LLM stack
└── README.md                   # Setup and how to run the API
```

**Orientation**

1. Install and run the API (see README).
2. Skim `frontend_streamlit/unified_app.py` for plant → pre-launch stages.
3. Open `frontend_mockup/labcd_chat.html` in a browser — tone, density, HITL
   cards, simulation pad, and onboarding are the reference, not pixel-perfect
   production code.

---

## What to build

A **modern, minimal assistant-style frontend** for AgentPlant. Chat is primary.
Control-specific elements appear in context when the agent produces a draft.

### Required capabilities

| Feature | Intent |
|---------|--------|
| **Assistant chat UX** | Clean thread, thinking/streaming states, message actions, model/settings — comparable to ChatGPT / Claude / Grok. |
| **Human-in-the-loop** | Agent may ask clarifying questions. Show interactive cards (options, free text, optional timeout). Answers return to the conversation; answered cards collapse so the thread stays readable. |
| **PDF upload + RAG** | User can attach a paper or textbook PDF. Agent answers can cite retrieved passages. |
| **Web search** | Optional tool for systems that need external research. Surface results clearly in the thread. |
| **Draft → simulation pad** | When a **draft** includes executable `python_code`, offer an interactive pad: knobs for open-loop inputs (step, pulse, sine, …), run the code, plot the response. This is the main control-specific interaction. |
| **Pre-launch / control knobs** | Simulation settings (horizon, sample time, trajectory style) should feel native in chat (panel, card, or side controls), not a disconnected wizard. |
| **Onboarding** | First visit / new account: short guided tour (highlights, brief copy, skip) covering composer tools and the simulation pad. |

### Design direction

- Modern and minimal; dark theme preferred (see mockup).
- Chat first; control UI appears in context.
- Desktop-first is fine; keep mobile usable.
- Mockup is a strong reference for behaviour — not a hard visual lock.

---

## What we look for

| Area | Priority |
|------|----------|
| Interaction quality | Chat + simulation pad feel natural for an engineer describing a plant |
| HITL clarity | Easy answers; thread remains readable after cards collapse |
| Draft → sim path | Obvious path from “here is a draft” to “run a step/pulse and see the plot” |
| RAG / search affordances | Discoverable without cluttering the main chat |
| Onboarding | New users learn the unique controls quickly; others can skip |
| Judgment | Sensible defaults; note assumptions in the README |

Prefer a **working vertical slice** (new chat → clarify → draft → sim pad → accept, plus PDF attach and onboarding) over thin coverage of every feature.

You do **not** need production-grade RAG or search backends. Wire the UI and
show the flow with mocks or light stubs where the full pipeline is heavy.

---

## Optional extras

- Save accepted plants into a simple local library list.
- Light theme toggle.
- Export of accepted `dynamics.py` + metadata.
- Keyboard shortcuts for power users.

Not required for a solid handoff.

---

## How to deliver

Push to a GitHub repo and share access. Keep the provided backend and agent
behaviour intact unless you fix a clear bug (call it out).

Deliver:

- Runnable frontend that talks to the AgentPlant API where possible.
- README: install, run, what is mocked vs wired.
- Short notes on assumptions and known gaps.

Review path: API + your UI → new chat → clarify → draft → simulation pad →
accept, plus PDF upload and onboarding.

---

Thanks for taking this on. Looking forward to the AgentPlant experience you shape.
