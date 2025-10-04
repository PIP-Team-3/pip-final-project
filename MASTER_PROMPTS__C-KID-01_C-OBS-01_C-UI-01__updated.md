
# MASTER PROMPTS — Next Milestones (post C‑REP‑01)
_Last updated: 2025-10-04 03:26_

## 0) Context Hydration (paste into a fresh Codex/Claude chat)

**Project:** P2N (Paper‑to‑Notebook Reproducer)  
**Current state:** Ingest → Extractor (SSE) → Planner v1.1 → Materialize → **Run (deterministic, CPU‑only, caps)** → **Report (C‑REP‑01 done)**.  
**Tests:** **51 passed**, 2 skipped (SSE live paths).  
**SDK:** OpenAI Python **1.109.1** (Responses mode); **file_search via top‑level tools**.  
**DB posture:** schema v0 only; **no migrations**.  
**Guardrails:** redact secrets; signed URLs only; typed errors; SSE vocab fixed.

**Do next in order:**  
1) **C‑KID‑01** — Kid‑Mode Storybook (static → updates final page after run).  
2) **C‑OBS‑01** — Observability (doctor enhancements + tracing).  
3) *(optional)* **C‑UI‑01** — Minimal FE page for SSE logs + storybook view.

---

## 1) C‑KID‑01 | Kid‑Mode Storybook

**Intent**: Generate an accessible 5–7 page **storybook JSON** about the paper + reproduction, using **grade‑3 vocabulary** and required **alt‑text**. After a run finishes, refresh the final page with an **ours vs claim** scoreboard.

**Files to edit**  
- `api/app/routers/explain.py` — `POST /api/v1/explain/kid` (create), `POST /api/v1/explain/kid/{storyboard_id}/refresh` (update final page).  
- `api/app/services/explain_kid.py` — prompt/validation helpers.  
- `api/app/schemas/storybook.py` — Pydantic schema (`pages[]`, `glossary[]`, `a11y` checks).  
- `api/app/data/models.py` — v0 dataclasses for storyboards (id, paper_id, run_id nullable, created_at, json).  
- `api/app/data/supabase.py` — insert/get storyboard + storage helpers.  
- `api/tests/test_explain_kid.py` — happy path + negative tests.

**Constraints**  
- Grade‑3 reading level, short sentences; **alt‑text required**.  
- **No images generated**; suggest visuals with descriptions.  
- Storyboard saved to DB (v0) and JSON copy to Storage `storyboards/{id}.json`.  
- Final page refresh pulls latest run metrics + claim and renders a simple two‑bar scoreboard.  
- **Typed errors**: `E_STORY_MISSING_ALT_TEXT`, `E_STORY_TOO_FEW_PAGES`, `E_STORY_NO_RUN`, `E_STORY_UPDATE_NOT_POSSIBLE`.  
- **Privacy**: no personal data; redact vector store ids in logs.

**Tests**  
- `test_story_create_happy_returns_id_and_signed_url`  
- `test_story_missing_alt_text_returns_typed_error`  
- `test_story_min_pages_enforced` (>=5)  
- `test_story_refresh_updates_final_page_after_run`  
- `test_story_signed_urls_no_tokens_leak`

**Manual (PowerShell)**  
```powershell
$payload = @{{ paper_id = "<paper_id>" }} | ConvertTo-Json
curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/explain/kid -H "Content-Type: application/json" -d $payload

# After a run completes:
curl.exe -sS -X POST http://127.0.0.1:8000/api/v1/explain/kid/<storyboard_id>/refresh
```

---

## 2) C‑OBS‑01 | Observability & Doctor Enhancements

**Intent**: Make **doctor** the one‑stop status snapshot and tighten structured logging/tracing.

**Files**  
- `api/app/config/doctor.py` — add `runner`, `last_run`, `caps` detail.  
- `api/app/config/llm.py` — ensure trace labels include `p2n.report.*`, `p2n.kid.*`.  
- `api/app/utils/redaction.py` — ensure signed URL query tokens redacted.  
- `api/tests/test_config_doctor_obs.py` — new test (see suite file).

**Doctor response additions**  
```jsonc
{{
  "runner": {{
    "cpu_only": true,
    "seed_policy": "deterministic",
    "artifact_caps": {{ "logs_mib": 2, "events_mib": 5 }}
  }},
  "last_run": {{ "id": "...", "status": "succeeded", "completed_at": "...", "env_hash": "..." }}
}}
```
- Ensure no secrets/tokens leak; redact signed URL querystrings.

**Tests**  
- `test_doctor_includes_runner_posture_and_last_run_snapshot`  
- `test_redaction_removes_signed_url_tokens`

**Manual**  
```powershell
curl.exe -sS http://127.0.0.1:8000/internal/config/doctor
```

---

## 3) (Optional) C‑UI‑01 | Minimal FE (Logs + Storybook)

**Intent**: A tiny HTML/JS page to connect SSE and render storybook JSON.

**Files**  
- `web/public/index.html` (SSE pane + storybook viewer).  
- `web/server.js` (static, no auth).  
- `docs/USAGE_UI.md` (how to run).

**Tests (smoke)**  
- `test_ui_assets_exist`  
- `test_storybook_json_is_valid` (reuse backend validator)

---

## 4) Ground Rules (unchanged)
- Keep **OpenAI 1.109.1**; **top‑level** `tools=[{{"type":"file_search", "max_num_results": N}}]` only.  
- **No DB migrations** (v0).  
- **Secrets redaction** everywhere.  
- **Windows**‑friendly examples.

---

## 5) Paste‑to‑start (Codex/Claude)
> Use this single message to kick off the next milestone in a fresh chat:

```
Context hydration: We’re at “ingest → extractor → planner v1.1 → materialize → run (deterministic, CPU‑only, caps) → report”, with 51 tests passing on Windows; Responses mode on; OpenAI Python 1.109.1; schema v0 posture. Please implement **C‑KID‑01** per the MASTER PROMPTS file I’ll share next. Constraints: no schema migrations; redact secrets; signed URLs only; typed errors preserved. After KID‑01, proceed to **C‑OBS‑01** exactly as specified.

Next, open and follow this file (assume repo layout matches paths):
MASTER_PROMPTS__C-KID-01_C-OBS-01_C-UI-01__updated.md
```
