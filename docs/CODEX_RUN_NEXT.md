
# CODEX_RUN_NEXT.md
_Last updated: 2025-10-03 20:38:51_

**You are Codex acting as a senior backend engineer & doc maintainer.**  
Do **not** change database rules (Schema v0), do **not** upgrade OpenAI SDK to 2.x. Keep `openai==1.109.1`, `openai-agents==0.3.3`.

## Step 1 — Hydrate context
1. Open and read these files as ground truth (create if missing but prefer existing content):
   - `docs/FUTURE_CODEX_PROMPTS.md`
   - `docs/AGENTS.md`
   - `docs/PLAYBOOK_MA.md`
   - `docs/db-schema-v0.md`
   - `README.md`, `api/README.md` (or `docs/API.md`)

## Step 2 — Select next prompt
- From `docs/FUTURE_CODEX_PROMPTS.md`, start with the **first prompt not yet merged**, which should be **C‑RUN‑01** (sandbox runner + SSE).

## Step 3 — Implement strictly within the prompt scope
- Edit only the files listed in the prompt.  
- Maintain **Schema v0** (no FK/RLS/constraints).  
- Keep secrets out of logs; redact vector store IDs to 8 chars + `***`.  
- Enforce Responses‑mode assumptions (File Search tool, SSE).

## Step 4 — Tests & acceptance
- Add tests exactly as described (happy + negative).  
- Provide **manual verification commands** (PowerShell + bash).  
- Return: changed file list, diff summary, test results, and a 3‑item “How to verify manually” checklist.

## Step 5 — Commit & queue next
- Commit with message: `C‑<ID>: <title> (acceptance: <short>)`.  
- Then move to the next prompt in the file.

> If you detect drift between docs and code, fix the **docs** in the same PR (not the code), unless the prompt explicitly calls for a code change.
