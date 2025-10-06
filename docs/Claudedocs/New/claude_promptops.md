# Claude PromptOps — Drift Recovery & Structured Output Guardrails
**Project:** Paper‑to‑Notebook (P2N)  
**Scope:** Keep Claude aligned with SDK 1.109.1 + Responses API + File Search  
**Status:** Authoritative prompt + invariants to eliminate AJPR drift

---

## 0) Why this file exists
We saw **extractor drift**: narrative text instead of JSON, “attachments” in the input, and reliance on deprecated `text_format`. This doc codifies the *prompt rules + API invariants* Claude must follow so extraction/planning stay deterministic and parseable.

---

## 1) Non‑negotiable invariants (copy these into any new prompt brief)
1. **Responses API** is the interface. No Chat Completions.  
2. **Structured output is enforced** via `response_format = { "type": "json_schema", "json_schema": { "name": "...", "schema": <Pydantic JSON Schema>, "strict": true } }`.  
3. **No `attachments` in `input`**.  
4. **File Search configured in the tool**: the `file_search` tool must carry the **correct vector store id(s)**.  
5. **No deprecated fields**: never use `text_format` (deprecated) or any unknown top‑level parameters.  
6. **SSE discipline**: emit `stage_update`, `token`, and a final `result` that conforms to schema.  
7. **Enum discipline** (DB): `papers.status ∈ {'ready','processing','failed'}`; `runs.env_hash` required before running; storage writes specify the **correct MIME** (e.g. `application/pdf`).  
8. **Idempotency**: every step is safe to re‑run; detect duplicates through DB constraints (e.g., `pdf_sha256`, `vector_store_id`).

> If you must deviate for any reason, stop and propose a change in writing first.

---

## 2) "Golden" request shapes (for *validation*, not for copy‑pasting blindly)

> ⚠️ **CRITICAL**: These examples are **illustrative only**. SDK types evolve.
> **ALWAYS verify the actual structure** by inspecting the installed SDK types:
> ```python
> from openai.types.responses import ResponseInputParam
> from openai.types.responses.response_input_param import Message
> # Check __annotations__ to see required fields
> ```

### 2.1 Extractor — **must** return `ExtractorOutput` JSON (strict mode)
- **tools**: include `file_search` with the paper's vector store id.
- **response_format**: JSON schema for `ExtractorOutput` with `strict: true`.
- **input**: List of Message objects (see structure below).

**Expected high‑level JSON (shape, verified against SDK 1.109.1):**
```jsonc
{
  "model": "<gpt-4o or 4o-mini>",
  "tools": [
    { "type": "file_search", "file_search": { "vector_store_ids": ["vs_..."] } }
  ],
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "extractor_output",
      "schema": { /* Pydantic ExtractorOutput JSON schema */ },
      "strict": true
    }
  },
  "input": [
    {
      "type": "message",  // ← REQUIRED at top level (from Message TypedDict)
      "role": "system",   // ← role: Literal["user", "system", "developer"]
      "content": [
        {
          "type": "input_text",  // ← REQUIRED at content block level (from ResponseInputTextParam)
          "text": "You are a claims extractor..."
        }
      ]
    },
    {
      "type": "message",
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "Extract claims with citations..."
        }
      ]
    }
  ]
}
```

**How to verify this structure:**
```python
# In Python with SDK 1.109.1 installed:
from openai.types.responses.response_input_param import Message
# Message.__annotations__ shows:
#   type: Literal["message"]
#   role: Literal["user", "system", "developer"]
#   content: ResponseInputMessageContentListParam

from openai.types.responses.response_input_text_param import ResponseInputTextParam
# ResponseInputTextParam.__annotations__ shows:
#   type: Literal["input_text"]
#   text: str
```

### 2.2 Planner — **must** return Plan v1.1 JSON (strict mode)
Same structure as extractor but schema is `PlanDocumentV11`. Ensure `estimated_runtime_minutes ≤ policy.budget_minutes` in the returned JSON.

---

## 2.3) SDK Type Verification Protocol

**When debugging OpenAI API errors or implementing new features:**

1. **Never trust documentation examples alone** — they lag behind SDK releases
2. **Always inspect the installed SDK types first:**

```python
# Check what input parameter accepts:
from openai.types.responses import ResponseInputParam
print(ResponseInputParam)  # Shows Union of all valid input item types

# Check Message structure:
from openai.types.responses.response_input_param import Message
if hasattr(Message, '__annotations__'):
    for key, val in Message.__annotations__.items():
        print(f'{key}: {val}')

# Check content block types:
from openai.types.responses.response_input_text_param import ResponseInputTextParam
print(ResponseInputTextParam.__annotations__)
```

3. **Common SDK inspection commands:**
```bash
# Find type definitions in your venv:
grep -r "class Message" .venv/Lib/site-packages/openai/types/responses/

# Check SDK version:
python -c "import openai; print(openai.__version__)"

# Inspect function signature:
python -c "from openai import OpenAI; import inspect; print(inspect.signature(OpenAI().responses.create))"
```

4. **Error diagnosis pattern:**
   - OpenAI returns `400 BadRequest` with `"Invalid value: 'X'"` → Check the type at that path
   - Example: `"Invalid value: 'input_text'" at input[0]` → Top-level input item needs `"type": "message"`, not `"type": "input_text"`
   - SDK types are the **source of truth**, not blog posts or old docs

---

## 3) SSE contract (server ↔ client)
- `stage_update`: `{ "stage": "<extraction|planning|...>", "status": "running|done|error" }`
- `token`: `{ "delta": "<partial text>" }` (streaming is fine but **final** event must be JSON result)
- `result`: **strict JSON** conforming to schema
- `error`: typed code + remediation (e.g., `E_EXTRACT_NO_OUTPUT`, `E_EXTRACT_OPENAI_ERROR`)

> If the model streamed only text and never emitted a **schema‑conforming** `result`, treat as `E_EXTRACT_NO_OUTPUT` and retry at most once with a shorter, stricter instruction (“return JSON only, no prose”).

---

## 4) Prompt skeletons (drop‑ins for Claude)

### 4.1 Extractor (with File Search)
```
ROLE: system
You are P2N's extractor. You return JSON that **exactly** matches the provided schema (strict mode).
Rules:
- Use File Search only to quote and cite relevant passages.
- Do not produce prose; output must be valid JSON for ExtractorOutput.

ROLE: user
Task: Extract quantitative performance claims from the paper.
Requirements:
- Each claim includes: dataset_name, split, metric_name, metric_value, units, method_snippet, source_citation, confidence (0..1).
- Cite the paper section/table in `source_citation`.
- Exclude ambiguous statements (“better”, “state of the art”) unless quantified.
- Return ONLY JSON that matches the schema. No additional text.
```

### 4.2 Planner
```
ROLE: system
You are P2N's planner. Produce Plan v1.1 JSON (strict mode).

ROLE: user
Given the extracted claims and the paper’s content, produce a feasible plan under policy.budget_minutes.
- Include dataset + model details, training config (epochs, batch_size, lr, optimizer), metrics, visualizations, and grounded `justifications` with quotes + citations.
- `estimated_runtime_minutes` ≤ `policy.budget_minutes`.
- Return ONLY valid Plan v1.1 JSON (strict schema).
```

---

## 5) Drift sentinels (what to test automatically)
- **Payload linter** (unit test): assert request JSON has **no** `attachments`; has **response_format.json_schema.strict=true**; `tools` includes `file_search` with valid vector store id; no `text_format` key.  
- **End‑to‑end extractor test**: feed a small PDF and assert final SSE `result` parses into `ExtractorOutput` with ≥1 claim.  
- **Planner test**: given a minimal `claims` list, assert Plan v1.1 JSON validates and `estimated_runtime_minutes ≤ budget_minutes`.

---

## 6) Operational tips
- Prefer **gpt‑4o‑mini** for extraction (cost/speed), **gpt‑4o** for planner if quality dips.
- Use **idempotent** retries with clear limits (max 1) to avoid snowballing cost/time.
- Log the **exact payload** (with secrets redacted) when you see OpenAI 400/422 errors.

---

## 7) “Claude bootstrap” (paste this once per new session)
```
Load and follow docs in docs/Claudedocs/new/:
- claude_promptops.md (this file)
- ROADMAP_Claude_Drift.md
- PLAYBOOK_Verification.md
- papers_to_ingest.md

Verify shell access:
- Run: bash --version || echo no-bash
Default to Bash; mirror PowerShell only when commands differ.

Adhere to invariants:
- Responses API
- response_format.json_schema.strict = true
- No attachments
- file_search tool carries vector_store_ids
- Emit final schema-conforming result event

First actions:
1) Summarize the four docs in ≤10 bullets.
2) Run the PLAYBOOK health checks.
3) Ingest 1 local PDF and perform extractor → planner → materialize smoke (stop before run unless instructed).
4) Propose any gap you see vs invariants as a tiny PRD with acceptance tests.
```