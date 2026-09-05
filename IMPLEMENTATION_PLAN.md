# AgentPlant — Implementation Plan

This is the **authoritative project plan**. Task order, ownership, and Definition of Done in this file override informal discussion.

Context, constraints, and locked decisions: [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).

**Rules**

- Do not start implementation until `PROJECT_CONTEXT.md` and this file exist.
- No skipping tasks.
- No combining multiple tasks unless explicitly approved.
- No parallel development between Developer A and Developer B.
- No backend work by Developer B after handoff.

---

## Execution order

```
P0
A1 → A2 → A3 → A4 → A5 → A6 → A7 → A8 → A9 → A10 → A11 → A12
HANDOFF
B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8 → B9 → B10 → B11 → B12
Q1
```

Developer A completes Phase 1 entirely.

Developer B starts Phase 2 only after **A12** and the **handoff checklist** are fully verified.

---

## Dependency graph

```
P0  alignment
 │
 A1  schemas
 │
 A2  persistence
 │
 A3  mock agent
 │
 A4  chat orchestrator
 │
 A5  files + RAG + search stubs
 │
 A6  simulation mock
 │
 A7  simulation sandbox
 │
 A8  error handling
 │
 A9  backend tests
 │
 A10 SPA scaffold
 │
 A11 typed API client
 │
 A12 Contract Probe
 │
 HANDOFF
 │
 B1  shell
 │
 B2  landing / conversations
 │
 B3  thread / thinking
 │
 B4  composer
 │
 B5  HITL UI
 │
 B6  draft / plant panel
 │
 B7  simulation UI
 │
 B8  tool cards
 │
 B9  pre-launch
 │
 B10 accept / download / errors
 │
 B11 onboarding
 │
 B12 polish / README
 │
 Q1  Shared QA
```

This is a DAG. There is no hidden edge from Phase B back into backend code.

---

## File ownership matrix

| Path | Owner | Other developer allowed to modify? | Notes |
|------|--------|--------------------------------------|--------|
| `backend_api/AgentPlant/schemas.py` | A | No after handoff | All contract extras freeze here |
| `backend_api/AgentPlant/router.py` | A | No | New routes only in Phase 1 |
| `backend_api/AgentPlant/service.py` | A | No | Orchestrator |
| `backend_api/AgentPlant/conversation_store.py` | A | No | Persist structured turns |
| `backend_api/AgentPlant/app.py` | A | No | Mock flag, error handlers |
| `backend_api/AgentPlant/mock_*.py` | A | No | Full mock script |
| `backend_api/AgentPlant/simulate*.py` | A | No | Mock + sandbox |
| `backend_api/AgentPlant/files*.py` | A | No | Upload + FileRef |
| `backend_api/AgentPlant/tests/**` | A | No | B does not add backend tests |
| `backend_core/**` | A (protected) | No | Do not modify `PlantModelAgent.step()` |
| `packages/labcd_agents/**` | A (protected) | No | Do not rewrite the LLM stack |
| `frontend/src/types/**` | A | No | B imports only |
| `frontend/src/api/**` | A | No | Only way B talks to the backend |
| `frontend/src/dev/**` | A | No | Contract Probe |
| `frontend/package.json` | A, then B | B may add UI deps after handoff | A creates scaffold/scripts |
| `frontend/src/main.tsx`, `frontend/src/App.tsx` | A scaffold → B | Yes after handoff | B-owned after scaffold/handoff |
| `frontend/src/components/**` | B | A no | Does not exist until Phase 2 |
| `frontend/src/features/**` | B | A no | |
| `frontend/src/pages/**` | B | A no | Except `dev/` |
| `frontend/src/styles/**` | B | A no | |
| `frontend_streamlit/**` | Neither | No | Reference only |
| `frontend_mockup/**` | Neither | No | Reference only |
| `requirements.txt` | A | No | B does not add Python deps |

---

## Phase 0 — Shared alignment

### P0 — Lock decisions

| Field | Value |
|--------|--------|
| **ID** | P0 |
| **Owner** | Shared |
| **Dependencies** | None |
| **Complexity** | Low |
| **Files** | None (no code) |

Confirm and do not reopen:

1. HITL is a clarifier on `continue`, not a PID/MPC/Adaptive questionnaire.
2. RAG and web search start as stub/mock. No vector database.
3. Real streaming is out of scope. Client-side thinking is allowed.
4. Pre-launch stays the existing four fields. Trajectory belongs to `/simulate`.
5. Accept/finish follows existing agent logic. Artifacts stay a separate endpoint.
6. Module routing, case library, and profile are out of scope.
7. `PlantModelAgent.step()` is not modified.
8. After handoff, backend and API contracts are protected.

**Definition of Done**

- Both developers accept the eight locked decisions in `PROJECT_CONTEXT.md`.
- Both developers accept this execution order and ownership matrix.

---

## Phase 1 — Developer A

Developer A must **not** build production UI components.

### A1 — Freeze schemas

| Field | Value |
|--------|--------|
| **ID** | A1 |
| **Owner** | Developer A |
| **Dependencies** | P0 |
| **Complexity** | Medium |
| **Files** | `backend_api/AgentPlant/schemas.py` |

Implement all optional / stable contracts:

- `hitl`
- `tool_results`
- `SearchHit`
- `FileRef`
- `attachment_ids`
- `web_search`
- `SimulateRequest`
- `SimulateResponse`
- error envelope
- extended `ChatMessage`

New fields must remain backward compatible (not required on existing clients).

**Definition of Done**

- Existing API behavior remains compatible.
- New schemas have tests.

---

### A2 — Persist structured turns

| Field | Value |
|--------|--------|
| **ID** | A2 |
| **Owner** | Developer A |
| **Dependencies** | A1 |
| **Complexity** | Medium |
| **Files** | `backend_api/AgentPlant/conversation_store.py`, `router.py`, `schemas.py` |

Extend conversation persistence so assistant messages can retain:

- `status`
- `hitl`
- `tool_results`
- other structured response data required by the frozen contract

`GET /api/plant-model/conversations/{id}` must return these fields.

**Definition of Done**

- Chat with HITL / tool results followed by GET conversation returns the same structured data.

---

### A3 — Full mock agent

| Field | Value |
|--------|--------|
| **ID** | A3 |
| **Owner** | Developer A |
| **Dependencies** | A1 |
| **Complexity** | Medium |
| **Files** | `backend_api/AgentPlant/mock_*.py` |

Implement deterministic mock behavior without an LLM or API key.

Mock must cover:

- clarification / HITL
- draft
- metadata
- RAG interaction
- web-search interaction
- complete / finish

**Definition of Done**

- Unit tests prove all relevant statuses and structured payloads.
- No network / live LLM in those tests.

---

### A4 — Chat orchestrator

| Field | Value |
|--------|--------|
| **ID** | A4 |
| **Owner** | Developer A |
| **Dependencies** | A2, A3 |
| **Complexity** | Medium |
| **Files** | `backend_api/AgentPlant/service.py`, `app.py`, `router.py` |

Implement mock / live routing.

- Mock mode: `LABCD_MOCK_MODE=1`
- Live mode: existing `PlantModelAgent`

Request extras: `attachment_ids`, `web_search`  
Response extras: `hitl`, `tool_results`

Do not modify `PlantModelAgent.step()`.

**Definition of Done**

- Full chat flow works without an API key in mock mode.
- Existing chat tests that patch the agent remain green.

---

### A5 — Files + RAG + search stubs

| Field | Value |
|--------|--------|
| **ID** | A5 |
| **Owner** | Developer A |
| **Dependencies** | A4 |
| **Complexity** | Medium |
| **Files** | `backend_api/AgentPlant/files*.py`, router, service |

Implement:

- `POST /files` → `FileRef`
- `attachment_ids` on chat → mock RAG `tool_results`
- `web_search=true` → mock search `tool_results`

`SearchHit` schema must be stable.

Do not add `pypdf` or a vector database unless later explicitly required.

**Definition of Done**

- Upload + chat attachment produces a RAG tool result.
- Search flag produces a search tool result.

---

### A6 — Simulation mock API

| Field | Value |
|--------|--------|
| **ID** | A6 |
| **Owner** | Developer A |
| **Dependencies** | A1 |
| **Complexity** | Medium |
| **Files** | `backend_api/AgentPlant/schemas.py`, router, `simulate*.py` |

Implement `POST /api/plant-model/simulate` with a stable request / response contract.

Support deterministic mock trajectories such as:

- `step`
- `pulse`
- `sine`

Return a timeseries containing:

- `t`
- `x`
- `u`

**Definition of Done**

- OpenAPI and tests prove the contract.
- The simulate contract is not changed after this task except for sandbox internals hidden from the frontend.

---

### A7 — Simulation sandbox

| Field | Value |
|--------|--------|
| **ID** | A7 |
| **Owner** | Developer A |
| **Dependencies** | A6 |
| **Complexity** | High |
| **Files** | `backend_api/AgentPlant/simulate*.py` (sandbox module) |

Implement restricted execution of `dynamics(t, x, u)`.

Requirements:

- numpy-based execution
- timeout
- reject dangerous imports
- prevent obvious unrestricted system access

The frontend must not depend on sandbox implementation details. Same `/simulate` contract as A6.

**Definition of Done**

- Valid dynamics produce numerical results.
- Dangerous imports are rejected.
- Hanging execution is terminated.

---

### A8 — Error envelope

| Field | Value |
|--------|--------|
| **ID** | A8 |
| **Owner** | Developer A |
| **Dependencies** | A4 |
| **Complexity** | Low |
| **Files** | `backend_api/AgentPlant/app.py` and/or error handlers |

Implement one stable JSON error structure for:

- `400`
- `404`
- `503`

including LLM failure cases.

No raw traceback or HTML should reach the frontend.

**Definition of Done**

- Frontend can reliably parse errors.
- Live chat without a key (or LLM failure) returns the JSON envelope, not an HTML traceback.

---

### A9 — Backend test sweep

| Field | Value |
|--------|--------|
| **ID** | A9 |
| **Owner** | Developer A |
| **Dependencies** | A5, A7, A8 |
| **Complexity** | Medium |
| **Files** | `backend_api/AgentPlant/tests/**` |

Cover:

- chat
- HITL
- persistence
- files
- RAG
- search
- simulation
- sandbox
- errors
- artifact / validate existing paths

No live LLM required for tests.

**Definition of Done**

- `pytest backend_api` is green.

---

### A10 — SPA scaffold

| Field | Value |
|--------|--------|
| **ID** | A10 |
| **Owner** | Developer A |
| **Dependencies** | A9 |
| **Complexity** | Low |
| **Files** | `frontend/*` (minimal Vite + React + TypeScript) |

Create a minimal Vite + React + TypeScript application.

Only development / probe functionality is needed.

No production UI.

**Definition of Done**

- `npm run dev` works.

---

### A11 — Typed API client

| Field | Value |
|--------|--------|
| **ID** | A11 |
| **Owner** | Developer A |
| **Dependencies** | A10, A9 |
| **Complexity** | Medium |
| **Files** | `frontend/src/types/**`, `frontend/src/api/**` |

Create typed functions / models for:

- chat
- conversations
- files
- simulate
- validate
- artifacts

Developer B must not need raw `fetch` calls.

**Definition of Done**

- Every handoff contract has a typed client function.

---

### A12 — Contract Probe

| Field | Value |
|--------|--------|
| **ID** | A12 |
| **Owner** | Developer A |
| **Dependencies** | A11 |
| **Complexity** | Medium |
| **Files** | `frontend/src/dev/**` |

Create a development-only probe page that can trigger and display raw JSON for:

- chat continue / HITL
- attachment / RAG
- web search
- draft
- simulation
- finish / complete
- validate
- artifact
- conversation persistence
- errors

**Definition of Done**

- All handoff checklist items can be verified without modifying backend code.

---

## Handoff checklist

Developer A may hand off **only if all** of the following are true:

| # | Requirement |
|---|-------------|
| 1 | Chat request / response is stable. |
| 2 | Extended messages persist correctly. |
| 3 | Session state / `latest_draft` is structured. |
| 4 | HITL mock exists. |
| 5 | File / RAG mock exists. |
| 6 | Web search mock exists. |
| 7 | Simulation mock **and** sandbox both work. |
| 8 | Artifact / accept flow is proven. |
| 9 | Error envelope is stable. |
| 10 | Mock mode works without an API key. |
| 11 | Typed API client covers all contracts. |
| 12 | Contract Probe demonstrates all flows. |
| 13 | Backend regression tests are green. |
| 14 | Backend is frozen. |

If any item fails, Phase 2 does not start.

After this point, backend code and API contracts are protected.

---

## Phase 2 — Developer B

Developer B works **frontend only**, on the frozen client and contracts.

Developer B must not modify:

- `backend_api/**`
- `backend_core/**`
- `packages/labcd_agents/**`
- `frontend/src/types/**`
- `frontend/src/api/**`
- `frontend/src/dev/**`

Developer B may add UI dependencies to `frontend/package.json` after handoff.

### B1 — Production shell

| Field | Value |
|--------|--------|
| **ID** | B1 |
| **Owner** | Developer B |
| **Dependencies** | A12 (handoff complete) |
| **Complexity** | Medium |
| **Files** | `frontend/src/components/layout/**`, theme / shell |

Build a modern dark, desktop-first assistant shell.

**Definition of Done**

- Dark shell is in place with room for thread and sidebar.
- Desktop-first; mobile remains usable as later polish.

---

### B2 — Landing + conversations

| Field | Value |
|--------|--------|
| **ID** | B2 |
| **Owner** | Developer B |
| **Dependencies** | B1 |
| **Complexity** | Medium |
| **Files** | landing page, conversation sidebar / list |

Build landing page, conversation list, new chat, and delete.

**Definition of Done**

- Landing, new chat, list, and delete work through the typed client.
- No raw `fetch`.

---

### B3 — Thread + thinking

| Field | Value |
|--------|--------|
| **ID** | B3 |
| **Owner** | Developer B |
| **Dependencies** | B2 |
| **Complexity** | Medium |
| **Files** | message list, thinking / loading chip |

Render text messages and a client-side thinking state.

Real streaming is out of scope.

**Definition of Done**

- Text messages render in the thread.
- A thinking / loading state shows while `POST /chat` is in flight.

---

### B4 — Composer

| Field | Value |
|--------|--------|
| **ID** | B4 |
| **Owner** | Developer B |
| **Dependencies** | B3 |
| **Complexity** | Medium |
| **Files** | composer component |

Support:

- send
- file attachment
- web search toggle
- file chip

**Definition of Done**

- Send calls chat via the typed client.
- Attach uses `/files`.
- Toggle sends `web_search`.
- Attached file shows as a chip.

---

### B5 — HITL UI

| Field | Value |
|--------|--------|
| **ID** | B5 |
| **Owner** | Developer B |
| **Dependencies** | B4 |
| **Complexity** | Medium |
| **Files** | HITL card component |

Render:

- question
- options
- free text
- timeout
- collapse

Responses must be sent as `user_message`.

Live fallback: `reply` + `status=continue`.

**Definition of Done**

- Mock HITL supports options, timeout, and collapse.
- Live fallback works when `hitl` is null.
- Confirm / answer is a normal chat turn.

---

### B6 — Draft + plant panel

| Field | Value |
|--------|--------|
| **ID** | B6 |
| **Owner** | Developer B |
| **Dependencies** | B4 |
| **Complexity** | Medium |
| **Files** | draft / code view, plant metadata panel |

Render the structured draft from `session_state.latest_draft`.

Do **not** parse markdown using regex.

**Definition of Done**

- Code and metadata come from the structured payload.
- No regex extraction from `reply`.

---

### B7 — Simulation pad

| Field | Value |
|--------|--------|
| **ID** | B7 |
| **Owner** | Developer B |
| **Dependencies** | B6 |
| **Complexity** | Medium |
| **Files** | simulation pad, plot |

Consume **only** `/simulate`.

Support `step` / `pulse` / `sine` and display the trajectory.

Do not depend on sandbox internals.

**Definition of Done**

- Pad appears for a draft and plots `t` / `x` / `u` from the simulate API.
- Errors use the frozen error envelope.

---

### B8 — Tool cards

| Field | Value |
|--------|--------|
| **ID** | B8 |
| **Owner** | Developer B |
| **Dependencies** | B4 |
| **Complexity** | Low |
| **Files** | tool result cards |

Render:

- RAG results
- web search results

Data must also work after conversation refresh.

**Definition of Done**

- Cards render from `tool_results`.
- Refresh restores cards from `GET /conversations/{id}`.

---

### B9 — Pre-launch

| Field | Value |
|--------|--------|
| **ID** | B9 |
| **Owner** | Developer B |
| **Dependencies** | B6 |
| **Complexity** | Medium |
| **Files** | pre-launch knobs UI |

Render **only** the frozen four pre-launch fields.

Do not invent `trajectory_mode` or other backend fields.

**Definition of Done**

- Knobs map to the existing pre-launch schema.
- Validate / artifact calls use the typed client.

---

### B10 — Accept / errors / empty

| Field | Value |
|--------|--------|
| **ID** | B10 |
| **Owner** | Developer B |
| **Dependencies** | B4, B6 |
| **Complexity** | Low |
| **Files** | complete panel, error / empty views |

Implement:

- complete state
- download `dynamics.py`
- artifact interaction
- readable error states

**Definition of Done**

- Finish / complete can download `dynamics.py`.
- Artifact interaction uses existing endpoints.
- 400 / 404 / 503 are readable via the error envelope.

---

### B11 — Onboarding

| Field | Value |
|--------|--------|
| **ID** | B11 |
| **Owner** | Developer B |
| **Dependencies** | B4, B7, B8 |
| **Complexity** | Low |
| **Files** | onboarding overlay |

Four-step onboarding with skip and `localStorage` persistence.

**Definition of Done**

- First visit shows four steps.
- Skip works.
- Completed / skipped onboarding does not show again.

---

### B12 — Polish + README

| Field | Value |
|--------|--------|
| **ID** | B12 |
| **Owner** | Developer B |
| **Dependencies** | B11 |
| **Complexity** | Medium |
| **Files** | styles, product `README.md` |

Finalize visual quality, responsive behavior, interaction polish, and README.

README must distinguish **mocked vs wired** functionality.

**Definition of Done**

- UI is a modern assistant experience (mockup is reference, not a pixel lock).
- README documents install, run, mocked vs wired, and known gaps.

---

## Shared QA

After B12. This is verification, not parallel feature work.

### Q1 — Vertical slice and regression

| Field | Value |
|--------|--------|
| **ID** | Q1 |
| **Owner** | Shared |
| **Dependencies** | B12 |
| **Complexity** | Medium |
| **Files** | None required (manual + existing tests) |

**Q1 — Assignment flow on mock**

```
onboarding
  → new chat
  → HITL
  → draft
  → simulation
  → PDF / RAG
  → web search
  → finish
  → download / artifact
```

**Q2 — Persistence**

Refresh the page and verify structured cards restore from `GET /conversations/{id}`.

**Q3 — Backend tests**

Backend tests remain green (`pytest backend_api`).

**Q4 — Live smoke (optional)**

If an LLM key is available, perform a live smoke test.

Live HITL may use the free-text fallback. That is acceptable.

**Definition of Done**

- Q1–Q3 pass.
- Q4 is recorded if a key is available.
- Backend bugs go to Developer A; UI bugs go to Developer B.
- Developer B still does not casually patch contracts.

---

## Task index

| ID | Owner | Dependencies | Complexity |
|----|--------|--------------|------------|
| P0 | Shared | — | Low |
| A1 | A | P0 | Medium |
| A2 | A | A1 | Medium |
| A3 | A | A1 | Medium |
| A4 | A | A2, A3 | Medium |
| A5 | A | A4 | Medium |
| A6 | A | A1 | Medium |
| A7 | A | A6 | High |
| A8 | A | A4 | Low |
| A9 | A | A5, A7, A8 | Medium |
| A10 | A | A9 | Low |
| A11 | A | A10, A9 | Medium |
| A12 | A | A11 | Medium |
| B1 | B | A12 + handoff | Medium |
| B2 | B | B1 | Medium |
| B3 | B | B2 | Medium |
| B4 | B | B3 | Medium |
| B5 | B | B4 | Medium |
| B6 | B | B4 | Medium |
| B7 | B | B6 | Medium |
| B8 | B | B4 | Low |
| B9 | B | B6 | Medium |
| B10 | B | B4, B6 | Low |
| B11 | B | B4, B7, B8 | Low |
| B12 | B | B11 | Medium |
| Q1 | Shared | B12 | Medium |
