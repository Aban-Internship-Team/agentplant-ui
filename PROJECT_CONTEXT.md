# AgentPlant — Project Context

This document is the durable context for implementation. It describes what the repository is today, what we are building, and the constraints that must not be reopened during coding.

The companion document is [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). That plan is authoritative for task order, ownership, and Definition of Done.

Do not start implementation until both documents exist. Once they exist, follow the plan strictly.

---

## 1. Project purpose

AgentPlant turns a natural-language description of a physical system into a runnable plant model: `dynamics(t, x, u)`.

Users clarify the system in chat, review a draft, optionally run an open-loop simulation, and accept the model. The assignment is to build a **modern React/TypeScript SPA** around the existing backend and agent, with a production-quality assistant experience (ChatGPT / Claude / Grok class), plus lightweight/stubbed capabilities such as RAG and web search.

This is **not** a rewrite of the agent. Existing agent behavior must remain stable.

---

## 2. Repositories and team

| Item | Value |
|------|--------|
| Local repository | `agentplant-ui` |
| Original repository | https://github.com/mnarimani/agentplant-ui |
| Team repository | https://github.com/Aban-Internship-Team/agentplant-ui |
| Team size | 2 developers |
| Development model | **Strict sequential development** |

Developer A completes Phase 1 entirely.

Developer B starts Phase 2 only after **A12** and the **handoff checklist** are fully verified.

After handoff:

- Backend is protected.
- Developer B must not modify backend contracts, schemas, services, stores, mock implementations, simulation implementation, or API client/types.
- If a backend contract is missing, that is a **handoff failure**. It goes through Shared QA. Developer B must not patch it casually.

There is no parallel development between A and B.

---

## 3. Current architecture

The existing project is a Python / FastAPI application. Streamlit and a static HTML mockup are reference surfaces, not the product frontend.

```
Browser / CLI / Streamlit
        │
        ▼
FastAPI  (backend_api/AgentPlant)
        │
        ▼
PlantModelAgent  (backend_core/AgentPlant)
        │
        ▼
labcd_agents.BaseAgent
        │
        ▼
LLMFactory
        │
        ▼
LangChain Chat client
```

`PlantModelAgent.step()` is the turn engine. It must **not** be rewritten into a new agent framework.

The current LLM call is **blocking**. There is no streaming, SSE, or WebSocket path.

---

## 4. Current repository reality

### 4.1 What exists

- FastAPI chat, conversation, validation, and artifact APIs
- `PlantModelAgent` with statuses `continue` / `draft` / `complete`
- Shared LLM package `packages/labcd_agents`
- Streamlit reference UI (`frontend_streamlit/`)
- HTML interaction mockup (`frontend_mockup/labcd_chat.html`)
- Agent CLI

### 4.2 What does not exist

- No production React / TypeScript frontend
- No proper tool registry
- No RAG infrastructure
- No web-search infrastructure
- No streaming / SSE / WebSocket implementation
- No simulation endpoint
- No complete mock mode

### 4.3 Existing HTTP surface

| Method | Path |
|--------|------|
| GET | `/health` |
| POST | `/api/plant-model/chat` |
| GET | `/api/plant-model/conversations` |
| GET | `/api/plant-model/conversations/{id}` |
| DELETE | `/api/plant-model/conversations/{id}` |
| POST | `/api/plant-model/artifacts` |
| GET | `/api/plant-model/artifacts` |
| GET | `/api/plant-model/artifacts/{id}` |
| GET | `/api/plant-model/artifacts/{id}/plugin` |
| GET | `/api/plant-model/artifacts/{id}/adaptive-spec` |
| POST | `/api/plant-model/validate` |

### 4.4 Existing chat contract

**Request:** `messages`, `user_message`, `model`, `session_state`, `conversation_id`, `max_drafts`, `min_user_turns_before_completion`

**Response:** `reply`, `status`, `final_result`, `session_state`, `usage`, `conversation_id`

**Statuses:** `continue` | `draft` | `complete`

Conversation messages today are `{role, content}` only. Structured extras required by the new UI (HITL, tool results) must be added in Phase 1 and persisted.

### 4.5 Reference UIs (not the product)

- `frontend_mockup/` is an **interaction inventory / reference**. It is **not** the final visual specification.
- `frontend_streamlit/` is a working reference flow. It is **not** the final frontend.
- Mockup-only product ideas (module routing, case library, profile) are out of scope.

---

## 5. Scope

### In scope

- Stable, backward-compatible extensions to the existing FastAPI contracts
- Mock mode so development works without an API key
- File upload + stub RAG results
- Stub web search results
- Simulation API (mock trajectories + restricted sandbox)
- Typed React/Vite/TypeScript client and a development-only Contract Probe (Phase A)
- Production assistant SPA (Phase B): chat, HITL, draft/sim pad, tool cards, pre-launch, accept/download, onboarding, polish

### Out of scope

See [Section 10](#10-out-of-scope).

---

## 6. Locked decisions (Phase 0)

These decisions are frozen and must not be reopened during implementation:

1. **HITL** is a clarifier mechanism associated with `continue` responses, not a fake PID / MPC / Adaptive questionnaire.
2. **RAG and web search** are initially stub/mock implementations. No vector database or heavy retrieval infrastructure is required.
3. **Real streaming** is out of scope. Developer B may implement a client-side thinking / loading state.
4. **Pre-launch** is limited to the existing four fields. Trajectory configuration belongs to `/simulate`, not pre-launch.
5. **Accept / finish** follows existing agent logic (user finish detection / draft limits). Artifact generation remains a separate existing endpoint.
6. **Module routing, case library, profile**, and unrelated product features are out of scope.
7. **`PlantModelAgent.step()` must not be modified** as part of this implementation.
8. After Developer A completes the handoff, **backend code and API contracts are protected**.

---

## 7. Architecture boundary

The boundary is **contract-based**, not merely backend-versus-frontend.

Every field the production UI needs must exist, be tested, and be demonstrated by **A12** before handoff.

If Developer B needs a new backend field, the handoff was incomplete.

### Phase A — Developer A

**Backend**

- schemas
- persistence
- mock agent
- chat orchestrator
- files
- RAG stub
- web search stub
- simulation
- sandbox
- error handling
- tests

**Frontend (non-production)**

- React / Vite / TypeScript scaffold
- typed API client
- typed API models
- development-only Contract Probe

Developer A must **not** build production UI components.

### Handoff

A12 Contract Probe must demonstrate every contract required by the frontend.

Only then may Developer B begin.

### Phase B — Developer B

**Frontend only**

- production shell
- theme
- landing
- conversation list
- chat thread
- composer
- HITL cards
- draft / code rendering
- plant panel
- simulation pad
- RAG / search cards
- pre-launch controls
- artifact / accept UI
- errors / empty states
- onboarding
- polish

Developer B must **not** modify:

- `backend_api/**`
- `backend_core/**`
- `packages/labcd_agents/**`
- `frontend/src/types/**`
- `frontend/src/api/**`
- `frontend/src/dev/**`

Developer B **may** add UI dependencies to `frontend/package.json` after handoff.

---

## 8. Ownership rules

| Path | Owner | Notes |
|------|--------|--------|
| `backend_api/AgentPlant/schemas.py` | A | Frozen after handoff |
| `backend_api/AgentPlant/router.py` | A | Frozen after handoff |
| `backend_api/AgentPlant/service.py` | A | Frozen after handoff |
| `backend_api/AgentPlant/conversation_store.py` | A | Frozen after handoff |
| `backend_api/AgentPlant/app.py` | A | Frozen after handoff |
| `backend_api/AgentPlant/mock_*.py` | A | Frozen after handoff |
| `backend_api/AgentPlant/simulate*.py` | A | Frozen after handoff |
| `backend_api/AgentPlant/files*.py` | A | Frozen after handoff |
| `backend_api/AgentPlant/tests/**` | A | Frozen after handoff |
| `backend_core/**` | A (protected) | Do not modify `PlantModelAgent.step()` |
| `packages/labcd_agents/**` | A (protected) | Do not rewrite the LLM stack |
| `frontend/src/types/**` | A | B imports only |
| `frontend/src/api/**` | A | B must not use raw `fetch` |
| `frontend/src/dev/**` | A | Contract Probe |
| `frontend/src/components/**` | B after handoff | Does not exist until Phase 2 |
| `frontend/src/features/**` | B after handoff | |
| `frontend/src/pages/**` | B after handoff | Except `dev/` |
| `frontend/src/styles/**` | B after handoff | |
| `frontend/src/main.tsx`, `frontend/src/App.tsx` | A scaffold, then B | B-owned after handoff |
| `frontend/package.json` | A then B | A creates scaffold/scripts; B may add UI deps |
| `frontend_streamlit/**` | Neither | Reference only |
| `frontend_mockup/**` | Neither | Reference only |

If the Contract Probe shows a field and the UI does not, that is a Phase B problem.

If the Contract Probe does not show a field the UI needs, that is a handoff failure (Shared QA), not a license for B to change the backend.

---

## 9. Important technical constraints

- Keep existing chat / conversation / artifact / validate behavior compatible. New fields must be **optional**.
- Route mock vs live **around** `PlantModelAgent`, do not replace `step()`.
- Mock mode: `LABCD_MOCK_MODE=1`. Full flows must work without an API key.
- Live mode: existing `PlantModelAgent`. Structured `hitl` may be null; UI falls back to `reply` + `status=continue`.
- Persist structured assistant extras (`status`, `hitl`, `tool_results`, and other frozen contract fields) so refresh restores cards from `GET /conversations/{id}`.
- Render drafts from `session_state.latest_draft`, not by regex-parsing markdown.
- Pre-launch knobs are only the existing four fields. Do not invent `trajectory_mode` on the backend.
- Simulation request/response is a separate stable contract. Frontend must not depend on sandbox internals.
- One stable JSON error envelope for 400 / 404 / 503, including LLM failure. No raw traceback or HTML to the frontend.
- Do not introduce LangGraph, LlamaIndex / vector databases, Pyodide / Jupyter execution, MCP / browser-use, or other large frameworks unless a verified blocker later requires it.
- Do not skip tasks. Do not combine multiple tasks unless explicitly approved.
- No backend work by Developer B after handoff.

---

## 10. Out of scope

Do not add:

- LangGraph
- LlamaIndex
- vector databases
- unrestricted Python execution
- Pyodide / Jupyter
- MCP / browser-use
- real-time streaming
- module routing
- case library
- profile system
- unrelated product features
- unnecessary backend rewrites

---

## 11. Execution rule

Implementation proceeds strictly:

```
P0 → A1 → A2 → A3 → A4 → A5 → A6 → A7 → A8 → A9 → A10 → A11 → A12
 → HANDOFF
 → B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8 → B9 → B10 → B11 → B12
 → Q1
```

Task details, checklists, and per-task Definition of Done live in [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md).
