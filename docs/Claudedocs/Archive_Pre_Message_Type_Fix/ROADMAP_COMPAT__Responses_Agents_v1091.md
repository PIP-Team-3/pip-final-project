# Compatibility Roadmap — OpenAI **Responses API** + **Agents SDK 0.3.3** (Pinned to `openai==1.109.1`)

_Last updated: now_

## Executive Summary

- Your **planner v1.1** 502 arises from passing a **typed/structured output model** (`text=PlannerOutput` or similar) to `client.responses.stream(...)`.  
- That pattern requires **newer SDKs**. With the current baseline (**`openai==1.109.1`**, required by **`openai‑agents==0.3.3`**), **do not** pass a Pydantic type in `text=` / `text_format=`.  
- Use **JSON mode** instead: `response_format={"type": "json_object"}` and then **parse → validate** with your Pydantic schema.  
- For **File Search**, attach your **vector store** via **top‑level tool configuration**:  
  `tools=[{"type":"file_search","max_num_results":8}]` **and** `tool_resources={"file_search":{"vector_store_ids":[vs_id]}}`.

> Why this works: the current Responses API supports `response_format=json_object` and **top‑level** file_search configuration (including `vector_store_ids`). Message‑level “attachments” and typed `text=<Model>` are **not** available in this pinned SDK line.

### Canonical call shape (Python, `openai==1.109.1`)

```py
from openai import OpenAI
client = OpenAI()

stream = client.responses.stream(
    model="gpt-4.1-mini",
    input=planner_prompt,                       # your assembled prompt string
    system=[{"text": PLANNER_SYSTEM_PROMPT}],   # optional system message for role
    tools=[{"type": "file_search", "max_num_results": 8}],   # enable file_search
    tool_resources={"file_search": {"vector_store_ids": [vector_store_id]}},
    response_format={"type": "json_object"}     # force JSON output
)

chunks = []
for event in stream:
    if event.type == "response.output_text.delta":
        chunks.append(event.delta)
plan_text = "".join(chunks).strip()

# Validate with your Pydantic schema (PlanDocumentV11)
plan = PlanDocumentV11.model_validate_json(plan_text)
```

> **Where this comes from:** Azure OpenAI’s Responses docs show `tool_resources.file_search.vector_store_ids` and JSON response formats, which mirror OpenAI’s Responses API. See: “Use the file search tool” and “Responses API structured outputs / response_format”. citeturn8search10turn12search8

---

## Compatibility Matrix (what is safe to use together)

| Piece | Safe Baseline | Notes |
|---|---|---|
| **OpenAI Python** | **`1.109.1`** | Required by `openai‑agents==0.3.3`. |
| **Agents SDK** | **`0.3.3`** | Keep if you want the agents helpers you already use. |
| **Responses API features** | ✅ `response_format={"type":"json_object"}`; ✅ `tools=[{"type":"file_search"}]`; ✅ `tool_resources.file_search.vector_store_ids` | **Do not** use message‑level attachments or `text=<PydanticModel>`. |
| **Structured outputs** | ✅ via `json_object` + Pydantic validation in app | **Typed `text=`** needs newer SDKs; not available here. |
| **Vector search** | ✅ Pass vector store **ids** via `tool_resources` | Pairs with your ingest-created vector store. |

**Alternative tracks (future):**  
- If you **upgrade** `openai>=1.111` or `2.x`, you can enable typed structured output or message attachments — but expect to **drop or upgrade** the Agents SDK and touch many call sites. Do not do this until you consciously schedule a migration.

---

## What to change in this repo (Planner & Extractor)

### 1) Planner (`api/app/routers/plans.py`)

- **Remove** any `text=PlannerOutput` / `text_format=...` / `attachments=...` / `vector_store_ids=...` **arguments** to `.stream(...)`.
- **Add** `response_format={"type": "json_object"}`
- **Add** `tool_resources={"file_search": {"vector_store_ids":[vector_store_id]}}`
- **Keep** `tools=[{"type": "file_search", "max_num_results": 8}]`
- **Collect** output_text via streaming and `json.loads(...)` → **validate** with `PlanDocumentV11`.
- **Propagate** typed errors: `E_PLAN_SCHEMA_INVALID`, `E_POLICY_CAP_EXCEEDED`, etc.

### 2) Extractor (`api/app/routers/papers.py`)

- Mirror the same **Responses** call structure: top‑level `tools` + `tool_resources`, `json_object` format.
- Parse final JSON → guardrails enforce **citations** + **confidence**; emit SSE `stage_update` / `log_line` consistently.

---

## Event Handling (SSE)

- Keep your SSE vocabulary stable: `stage_update`, `log_line`, and a final JSON payload with either `plan` (planner) or `claims[]` (extractor).
- When streaming Responses, forward deltas as needed (but **don’t** leak secrets/tool payloads).

---

## Testing & Observability

**Unit/Contract tests to keep green:**

- Planner: schema validation happy path + low confidence/guardrail + policy cap trips.
- Extractor: SSE emits stage transitions; citations present; cap enforcement.
- Doctor: confirms **Responses mode on**, `openai` version logged, and tools enabled.
- Redaction: signed URL query params and API keys redacted.

**Manual checks (PowerShell)** are included in the playbook file (`PLAYBOOK__Manual_EndToEnd_AfterPlannerFix.md`).

---

## Known pitfalls

- **Message attachments** and `text=<Model>`: not supported with this pinned SDK; use **top‑level** `tool_resources` + `json_object` instead.
- **Supabase auth `__del__` warning**: harmless log noise in current `supabase-py`; ignore or upgrade later.
- **Windows SSE**: prefer `--http1.1` and avoid `--reload` when watching streams from PowerShell.

---

## References

- **Responses + File Search**: Attach vector stores via `tool_resources.file_search.vector_store_ids`. Azure OpenAI mirrors OpenAI Responses for this; example request and parameters are documented there. citeturn8search10  
- **Structured output (JSON/JSON Schema)**: Response format options for structured JSON. (Azure OpenAI docs describe `json_object` & `json_schema` for Responses.) citeturn12search8
