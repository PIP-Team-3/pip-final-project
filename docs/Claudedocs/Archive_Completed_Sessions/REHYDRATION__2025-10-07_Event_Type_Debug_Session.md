# P2N Rehydration Prompt — Session 3: Event Type Debug & Empty Claims Investigation

**Date:** 2025-10-07
**Status:** 🟡 Pipeline working end-to-end, but model returns empty claims array
**Context:** Third debugging session after Session 1 (schema fixes) and Session 2 (Message type fixes)

---

## **Executive Summary**

**What We Fixed This Session:**
1. ✅ Event type name mismatch (`response.function_call_arguments.delta` vs `response.function_call.arguments.delta`)
2. ✅ Event attribute access (`event.delta` vs `event.arguments`)
3. ✅ Error event type (`error` vs `response.error`)

**Current Status:**
- ✅ **Pipeline works end-to-end:** OpenAI API → Event stream → Argument capture → JSON parsing → Pydantic validation → Dataclass conversion
- ❌ **Model returns empty claims:** `{"claims": []}` triggers guardrail: "Extractor must return at least one claim"

**Root Cause Hypothesis:**
File Search not working (no `response.file_search_call.searching` events seen) OR model being overly strict with requirements.

**Next Step:**
Debug logging added to see exact JSON returned. Server restart + extraction test needed.

---

## **Session Timeline: Detailed Walkthrough**

### **Starting Point**

**Context from Previous Sessions:**
- **Session 1:** Fixed schema mismatch (Pydantic vs dataclass nesting), tool definition, all tests passing (8/8)
- **Session 2:** Fixed Responses API input structure (Message type wrapper), file search tool structure, added model config (gpt-4o/o3-mini)
- **Both sessions:** Code committed but NEVER TESTED on running server

**This Session's Mission:**
Test Session 2's fixes for the first time on a live server.

---

### **Test 1: Environment Verification**

**Objective:** Confirm server is healthy and configured correctly.

**Commands Run:**
```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/internal/config/doctor
.venv/Scripts/python.exe manage.py models
```

**Results:**
```json
// /health
{"status":"ok","tracing_enabled":true}

// /config/doctor
{
  "supabase_url_present": true,
  "supabase_service_role_present": true,
  "supabase_anon_present": true,
  "openai_api_key_present": true,
  "all_core_present": true,
  "missing_env_keys": [],
  "responses_mode_enabled": true,
  "openai_python_version": "1.109.1",
  "models": {"selected": "gpt-4o"},
  "tools": {"file_search": true, "web_search": true}
}

// manage.py models
Extractor Model:  gpt-4o (default)
Planner Model:    o3-mini (default)
```

**✅ Verdict:** Environment healthy, all credentials present, SDK correct (1.109.1), models configured properly.

---

### **Test 2: First Extraction Attempt**

**Objective:** Test extraction with Session 2's fixes.

**Command:**
```bash
curl -sS -X POST -N "http://localhost:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/extract"
```

**Result:**
```
event: stage_update
data: {"agent": "extractor", "stage": "extract_start"}

event: error
data: {"agent": "extractor", "code": "E_EXTRACT_OPENAI_ERROR", "message": "OpenAI API request failed during extraction", ...}
```

**❌ Verdict:** Still failing, but with a generic OpenAI error. Need more diagnostics.

**Action Taken:** Added debug logging to see ALL event types emitted by SDK.

**Code Change (`api/app/routers/papers.py:418`):**
```python
with stream_manager as stream:
    for event in stream:
        event_type = getattr(event, "type", "")
        # DEBUG: Log ALL event types to diagnose mismatch
        print(f"DEBUG EVENT: type={event_type}", file=sys.stderr)
```

---

### **Test 3: With Debug Event Logging**

**Objective:** See what events SDK actually emits.

**Server Logs Showed:**
```
DEBUG extractor.model=gpt-4o
DEBUG EVENT: type=response.created
DEBUG EVENT: type=response.in_progress
DEBUG EVENT: type=response.output_item.added
DEBUG EVENT: type=response.function_call_arguments.delta
DEBUG EVENT: type=response.function_call_arguments.delta
DEBUG EVENT: type=response.function_call_arguments.delta
DEBUG EVENT: type=response.function_call_arguments.delta
DEBUG EVENT: type=response.function_call_arguments.done
DEBUG EVENT: type=response.output_item.done
DEBUG EVENT: type=response.completed
extractor.no_valid_output paper_id=... args_chunks=0 tokens=0
```

**🔍 Discovery:**

**Event Type Emitted by SDK:**
```
response.function_call_arguments.delta
```

**Event Type Code Was Listening For:**
```python
if event_type in ("response.function_call.arguments.delta", "response.function_call.delta"):
```

**❌ Mismatch Found:** Code used DOTS (`.arguments.`), SDK uses UNDERSCORES (`_arguments`).

**Why This Matters:**
The model WAS calling the function (4 delta events!), but our code never captured the arguments because the event type string didn't match our conditional.

---

### **Root Cause #1: Event Type Name Mismatch**

**Verification Method:**
```bash
.venv/Scripts/python.exe -c "
from openai.types.responses.response_function_call_arguments_delta_event import ResponseFunctionCallArgumentsDeltaEvent
print(ResponseFunctionCallArgumentsDeltaEvent.__annotations__)
"
```

**Output:**
```python
{
  'delta': <class 'str'>,
  'item_id': <class 'str'>,
  'output_index': <class 'int'>,
  'sequence_number': <class 'int'>,
  'type': typing.Literal['response.function_call_arguments.delta']
}
```

**Confirmed:** SDK event type is `response.function_call_arguments.delta` (underscores).

**Fix Applied (`api/app/routers/papers.py:449-455`):**
```python
# BEFORE (WRONG):
if event_type in ("response.function_call.arguments.delta", "response.function_call.delta"):
    delta_obj = getattr(event, "delta", None)
    if delta_obj:
        args_delta = getattr(delta_obj, "arguments_delta", None) or getattr(delta_obj, "arguments", None)
        # ...

# AFTER (CORRECT):
if event_type == "response.function_call_arguments.delta":
    # The delta attribute contains the argument chunk (str)
    args_delta = getattr(event, "delta", None)
    if args_delta:
        args_chunks.append(args_delta)
    continue
```

---

### **Test 4: After Event Type Fix**

**Objective:** Verify event type fix.

**Server Logs:**
```
DEBUG EVENT: type=response.function_call_arguments.delta  # (4 times)
extractor.no_valid_output paper_id=... args_chunks=0 tokens=0
```

**❌ Still `args_chunks=0`!**

**🔍 Discovery:** Event type now matches, but we're STILL not capturing arguments.

---

### **Root Cause #2: Wrong Attribute Name**

**Verification Method:**
Checked SDK event structure (already done in Test 3):
```python
ResponseFunctionCallArgumentsDeltaEvent.__annotations__:
{
  'delta': <class 'str'>,  # <-- Arguments are HERE
  'item_id': <class 'str'>,
  'output_index': <class 'int'>,
  'sequence_number': <class 'int'>,
  'type': typing.Literal['response.function_call_arguments.delta']
}
```

**Problem:** Code was using `getattr(event, "arguments", None)` but SDK has `event.delta`.

**Fix Applied (`api/app/routers/papers.py:452`):**
```python
# BEFORE (WRONG):
args_delta = getattr(event, "arguments", None)

# AFTER (CORRECT):
args_delta = getattr(event, "delta", None)
```

---

### **Preemptive Fix: Error Event Type**

**While Fixing:** Verified all event types against SDK.

**SDK Search:**
```bash
grep -r "^    type: Literal" .venv/Lib/site-packages/openai/types/responses/ | grep error
```

**Output:**
```
response_error_event.py:    type: Literal["error"]
response_failed_event.py:    type: Literal["response.failed"]
```

**Discovery:** Error event type is `"error"`, NOT `"response.error"`.

**Fix Applied (both `papers.py:45` and `plans.py:31`):**
```python
# BEFORE (WRONG):
FAILED_EVENT_TYPES = {"response.failed", "response.error"}

# AFTER (CORRECT):
FAILED_EVENT_TYPES = {"response.failed", "error"}  # SDK 1.109.1: "error" not "response.error"
```

---

### **Commit: All Event Type Fixes**

**Commit Hash:** `74c7fc2`
**Commit Message:** "fix: correct SDK 1.109.1 event type names and attribute access"

**Files Changed:**
- `api/app/routers/papers.py`: Event type fix, attribute fix, error event fix, debug logging
- `api/app/routers/plans.py`: Error event fix
- `docs/Claudedocs/REHYDRATION__2025-10-06_Model_Config_and_Message_Type_Fix.md`: Added (from Session 2)

**Changes Summary:**
1. Event type: `response.function_call_arguments.delta` (not `response.function_call.arguments.delta`)
2. Attribute: `event.delta` (not `event.arguments`)
3. Error type: `error` (not `response.error`)

---

### **Test 5: After All Fixes**

**Objective:** Verify end-to-end pipeline.

**Command:**
```bash
curl -sS -X POST -N "http://localhost:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/extract"
```

**Result:**
```
event: stage_update
data: {"agent": "extractor", "stage": "extract_start"}

event: error
data: {
  "agent": "extractor",
  "code": "E_EXTRACT_LOW_CONFIDENCE",
  "message": "Extractor guardrail rejected the claims",
  "remediation": "Use manual claim editor to supply citations or boost confidence"
}
```

**🎉 MAJOR PROGRESS!** Different error code!

**Server Logs:**
```
DEBUG extractor.model=gpt-4o
DEBUG EVENT: type=response.created
DEBUG EVENT: type=response.in_progress
DEBUG EVENT: type=response.output_item.added
DEBUG EVENT: type=response.function_call_arguments.delta  # (4 times)
DEBUG EVENT: type=response.function_call_arguments.done
DEBUG EVENT: type=response.output_item.done
DEBUG EVENT: type=response.completed
extractor.guardrail.failed paper_id=... reason=extractor_output_guard tripwire triggered: Extractor must return at least one claim
```

**✅ What This Means:**

1. **✅ Arguments ARE being captured:** We got past `args_chunks=0`
2. **✅ JSON is being parsed:** No parse errors
3. **✅ Pydantic validation passing:** No schema errors
4. **✅ Dataclass conversion working:** No TypeError from nested Citation
5. **✅ Function tool call working end-to-end:** Full pipeline operational
6. **❌ Model returned empty claims:** `{"claims": []}` triggered guardrail

---

## **Current State: What Works and What Doesn't**

### **✅ What's Working (The Good News)**

#### **1. Server Infrastructure**
- Health endpoint: `200 OK`
- Config doctor: All env vars present
- .env loading: Works in PowerShell via `manage.py start`
- Tracing enabled: Yes

#### **2. OpenAI SDK Integration**
- SDK version: `1.109.1` ✅
- API type: Responses API (NOT Chat Completions) ✅
- Client initialization: Success
- Stream management: Working

#### **3. Model Configuration**
- Extractor model: `gpt-4o` ✅
- Planner model: `o3-mini` ✅
- Model selection: Configured via `settings.py`
- CLI management: `manage.py models` works

#### **4. Responses API Request Structure**
- Input format: Correct Message type wrapper with `role` and `content` ✅
- System message: Properly structured
- User message: Includes paper ID and task description
- No attachments: Correct (Responses API requirement)

#### **5. Tool Definition**
- Tool type: `pydantic_function_tool(ExtractorOutputModel)` ✅
- Schema: Nested `CitationModel` matching dataclass ✅
- Tool name: `emit_extractor_output`
- Description: Present
- `strict: True`: Enforced

#### **6. Tool Forcing**
- Format: `{"type": "function", "name": "emit_extractor_output"}` ✅
- NOT: `{"type": "function", "function": {"name": "..."}}` (Chat Completions format)
- Model has no choice but to call the function

#### **7. File Search Tool Configuration**
- Structure: Flat `vector_store_ids` at top level ✅
- NOT: Nested `file_search: {vector_store_ids: [...]}` (old format)
- Vector store ID: `vs_68e332805ef881919423728eb33311a8`
- Max results: 8

#### **8. Event Stream Handling**
- Event types recognized: `response.created`, `response.completed`, `response.function_call_arguments.delta` ✅
- Event attribute access: `event.delta` ✅
- Token buffering: Working (for JSONizer fallback)
- SSE emission: Correct format

#### **9. Argument Capture**
- Event detection: Correctly listens for `response.function_call_arguments.delta` ✅
- Attribute extraction: `event.delta` ✅
- Chunk accumulation: `args_chunks.append(args_delta)` ✅
- Result: `args_chunks > 0` (arguments captured!)

#### **10. JSON Parsing & Validation**
- Pydantic validation: `ExtractorOutputModel.model_validate_json()` succeeds ✅
- Schema match: Nested `CitationModel` structure correct ✅
- No parse errors: JSON is valid ✅

#### **11. Dataclass Conversion**
- Pydantic → dataclass: Manual conversion works ✅
- Nested Citation: Properly constructed from `c.citation.source_citation` / `c.citation.confidence` ✅
- No TypeError: Structure matches `types.py` dataclasses ✅

#### **12. Debug Infrastructure**
- Event logging: All events printed to stderr ✅
- JSON logging: Added (pending test)
- Model verification: Logged (`DEBUG extractor.model=gpt-4o`)
- Tool structure: Logged

---

### **❌ What's Not Working (The Problem)**

#### **The Core Issue: Empty Claims Array**

**Model Output:**
```json
{"claims": []}
```

**Guardrail Triggered:**
```
extractor.guardrail.failed ... tripwire triggered: Extractor must return at least one claim
```

**Error Returned to Client:**
```json
{
  "agent": "extractor",
  "code": "E_EXTRACT_LOW_CONFIDENCE",
  "message": "Extractor guardrail rejected the claims",
  "remediation": "Use manual claim editor to supply citations or boost confidence"
}
```

**Note:** Error code is misleading - it's not about low confidence, it's about ZERO claims.

---

## **Diagnostic Hypotheses: Why Empty Claims?**

### **Hypothesis 1: File Search Not Working (MOST LIKELY)**

**Evidence:**
- No `response.file_search_call.searching` events seen in logs
- Vector store ID present: `vs_68e332805ef881919423728eb33311a8`
- Tool configured correctly with flat `vector_store_ids`

**Possible Causes:**

#### **A. Vector Store is Empty**
- PDF upload failed during ingestion
- Vector store created but no documents added
- Check: OpenAI dashboard → Vector Stores → `vs_68e332...`

#### **B. Vector Store ID is Invalid**
- ID is outdated/deleted
- ID belongs to different OpenAI organization
- Check: API call to `GET /v1/vector_stores/vs_68e332...` returns 404

#### **C. File Search Tool Not Triggering**
- Model chooses not to use File Search tool
- Tool configuration malformed (though we verified structure)
- OpenAI API silently skipping tool

#### **D. File Search Returns No Results**
- Vector store exists but has no relevant content
- Query embeddings don't match document embeddings
- `max_num_results: 8` but actual results: 0

**How to Verify:**
```bash
# Check if vector store exists
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/vector_stores/vs_68e332805ef881919423728eb33311a8

# Check if vector store has files
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/vector_stores/vs_68e332805ef881919423728eb33311a8/files
```

**Expected Fix:**
- Re-ingest paper if vector store empty
- Update vector store ID if invalid
- Add explicit File Search triggering in prompt

---

### **Hypothesis 2: Prompt Too Strict**

**Evidence:**
- Model returning valid JSON (not erroring)
- Empty claims array is a valid response
- System prompt has strict requirements

**Current Prompt Requirements (`api/app/agents/definitions.py:51-62`):**
```python
"- CALL the function tool 'emit_extractor_output' EXACTLY ONCE with the final JSON object."
"- Do NOT output any prose or inline JSON; only the tool call."
"- If no quantitative, reproducible claims exist, call the tool with {\"claims\": []}."
"- Each claim must include: dataset_name, split, metric_name, metric_value, units, method_snippet, and a nested citation object {source_citation: str, confidence: 0..1}."
"- Cite specific sections/tables in source_citation (e.g., 'Table 1, p.3' or 'Section 3.2, p.5')."
"- Exclude vague/non-quantified statements (e.g., 'better', 'state of the art') unless explicitly quantified."
```

**Possible Issues:**

#### **A. Schema Too Restrictive**
- **Problem:** Pydantic schema has ALL fields as `required`:
```python
class ExtractedClaimModel(BaseModel):
    dataset_name: Optional[str]  # But actually required in validation?
    metric_name: Optional[str]
    metric_value: Optional[float]
    # ... ALL marked as required in tool definition
```
- **Result:** Model gives up if it can't fill all fields with confidence

#### **B. Confidence Threshold Implicit**
- **Problem:** Prompt says confidence 0-1 but doesn't give lower bound guidance
- **Result:** Model might be filtering out claims it considers <0.7 confidence even if they're valid

#### **C. Citation Format Too Specific**
- **Problem:** Requires "Table 1, p.3" or "Section 3.2, p.5" format
- **Result:** Model might skip claims if citation doesn't match exact format

**How to Verify:**
- Check actual JSON returned (debug logging added)
- Try with a different paper known to have obvious claims
- Relax prompt temporarily ("return ALL numeric claims, even if uncertain")

**Expected Fix:**
- Make some fields truly optional in Pydantic schema
- Add examples of valid claims to prompt
- Lower implicit confidence threshold
- Relax citation format requirements

---

### **Hypothesis 3: Paper Content Issue**

**Evidence:**
- Paper ID: `15017eb5-68ee-4dcb-b3b4-1c98479c3a93`
- Vector store ID: `vs_68e332805ef881919423728eb33311a8`
- Extraction called but no claims found

**Possible Causes:**

#### **A. PDF Not Uploaded**
- Paper record exists in DB but PDF never uploaded to vector store
- Check: Query Supabase `papers` table for `pdf_storage_path`

#### **B. PDF Has No Quantitative Claims**
- Paper might be theoretical/qualitative
- No tables with numeric results
- No metrics reported

#### **C. Vector Store Indexing Incomplete**
- PDF uploaded but indexing still in progress
- OpenAI vector store status: `in_progress` not `completed`

**How to Verify:**
```bash
# Check paper record
curl -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  "$SUPABASE_URL/rest/v1/papers?id=eq.15017eb5-68ee-4dcb-b3b4-1c98479c3a93&select=*"

# Check vector store status
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/vector_stores/vs_68e332805ef881919423728eb33311a8
```

**Expected Fix:**
- Re-ingest paper if PDF missing
- Wait for indexing if in progress
- Try different paper if this one has no claims

---

### **Hypothesis 4: Model Misinterpretation**

**Evidence:**
- gpt-4o is cautious with structured outputs
- Empty array is a valid response per prompt
- No error messages in stream

**Possible Causes:**

#### **A. Model Sees No Context**
- File Search returns no results (empty context)
- Model has only system prompt, no paper content
- Responds with `{"claims": []}` as instructed

#### **B. Model Over-Filters**
- Model finds claims but filters them out as "not quantitative enough"
- Applies stricter criteria than intended
- Returns empty to avoid false positives

#### **C. Model Instruction Confusion**
- Prompt says "If no quantitative, reproducible claims exist, call the tool with {"claims": []}"
- Model interprets "reproducible" too strictly
- Excludes all claims as "not reproducible without full code"

**How to Verify:**
- Check for File Search events (already confirmed: NONE)
- Try with `gpt-4o-mini` (less cautious)
- Simplify prompt temporarily ("extract ALL numeric metrics")

**Expected Fix:**
- Add explicit examples of valid claims to prompt
- Clarify what "quantitative" means
- Add intermediate logging to see if model receives context

---

## **Next Steps: Immediate Actions**

### **Step 1: View Actual JSON Returned (IN PROGRESS)**

**Debug Logging Added (`api/app/routers/papers.py:543`):**
```python
raw_json = "".join(args_chunks)
print(f"DEBUG CAPTURED JSON: {raw_json}", file=sys.stderr)
```

**Action Required:**
1. Restart server
2. Run extraction test
3. Check server logs for `DEBUG CAPTURED JSON: ...`

**What to Look For:**
- `{"claims": []}` (empty as expected)
- OR `{"claims": [...], "reasoning": "..."}` (model explaining why empty)
- OR malformed JSON (unlikely given Pydantic passed)

---

### **Step 2: Check File Search Events**

**Observation:** No `response.file_search_call.searching` events in logs.

**Actions:**
1. Verify vector store exists and has files (API calls above)
2. Check if File Search tool is actually being used
3. Add explicit File Search instruction to prompt if needed

**Code to Add (if needed):**
```python
# In definitions.py system prompt:
"- ALWAYS use the File Search tool to find evidence in the paper before extracting claims."
"- If File Search returns no results, return {\"claims\": []} and explain why in a comment."
```

---

### **Step 3: Test with Known-Good Paper**

**Current Paper:** ID `15017eb5-68ee-4dcb-b3b4-1c98479c3a93` (unknown content)

**Action:** Try extraction with a different paper that definitely has claims.

**Example Papers to Test:**
- ResNet paper (famous for ImageNet accuracy tables)
- BERT paper (many benchmark results)
- Any paper from `docs/Claudedocs/New/papers_to_ingest.md`

**Command:**
```bash
# Ingest a new paper
curl -X POST "http://localhost:8000/api/v1/papers/ingest" \
  -F "file=@uploads/resnet.pdf" \
  -F "title=ResNet (He et al., 2015)"

# Extract from new paper
curl -X POST -N "http://localhost:8000/api/v1/papers/{new_paper_id}/extract"
```

---

### **Step 4: Relax Prompt Requirements**

**If File Search is working but model still returns empty:**

**Temporary Fix to Test Hypothesis:**
```python
# In definitions.py, change prompt to:
"- Extract ALL numeric performance metrics from the paper, even if uncertain."
"- For each metric, provide your best estimate of dataset, value, and confidence."
"- If a field is unknown, use null."
"- Confidence can be as low as 0.3 if the claim is plausible."
```

**Expected Result:** Model returns SOME claims if paper has any.

---

### **Step 5: Make Schema Fields Truly Optional**

**Current Schema (`api/app/agents/schemas.py:24-36`):**
```python
class ExtractedClaimModel(BaseModel):
    dataset_name: Optional[str] = Field(None, ...)
    # ... but marked as 'required' in Pydantic tool definition
```

**Fix:** Update Pydantic schema to explicitly allow None and not require all fields:
```python
class ExtractedClaimModel(BaseModel):
    # ONLY metric_name, metric_value, citation are truly required
    metric_name: str = Field(..., description="...")
    metric_value: float = Field(..., description="...")
    citation: CitationModel = Field(..., description="...")

    # Everything else is optional
    dataset_name: Optional[str] = Field(default=None, description="...")
    split: Optional[str] = Field(default=None, description="...")
    units: Optional[str] = Field(default=None, description="...")
    method_snippet: Optional[str] = Field(default=None, max_length=1000, description="...")
```

---

## **Technical Deep Dive: What We Learned**

### **1. OpenAI SDK 1.109.1 Event Types**

**Definitive Event Names (Verified via SDK inspection):**

| Event Type | Purpose | When Emitted |
|------------|---------|--------------|
| `response.created` | Stream started | Beginning of response |
| `response.in_progress` | Stream active | During generation |
| `response.output_item.added` | New output item | When function call or text starts |
| `response.function_call_arguments.delta` | Function arg chunk | Each chunk of function arguments |
| `response.function_call_arguments.done` | Function args complete | End of argument stream |
| `response.output_item.done` | Output item finished | After function call complete |
| `response.output_text.delta` | Text chunk | If model outputs text (not used with forced tool) |
| `response.file_search_call.searching` | File Search active | When model uses File Search tool |
| `response.file_search_call.completed` | File Search done | After File Search results returned |
| `response.completed` | Stream finished | End of response |
| `response.failed` | Request failed | On API error |
| `error` | Unspecified error | Generic error |

**Key Insight:** Event types use UNDERSCORES (`_arguments`) not DOTS (`.arguments.`) in compound names.

---

### **2. Event Attribute Structure**

**`ResponseFunctionCallArgumentsDeltaEvent` Structure:**
```python
{
    'type': Literal['response.function_call_arguments.delta'],
    'delta': str,              # <-- THE ARGUMENTS ARE HERE
    'item_id': str,
    'output_index': int,
    'sequence_number': int
}
```

**Key Insight:** Arguments are in `event.delta` (str), not `event.arguments` or nested `event.delta.arguments`.

---

### **3. Tool Choice Format (Responses API vs Chat Completions)**

**WRONG (Chat Completions API):**
```python
tool_choice = {
    "type": "function",
    "function": {"name": "emit_extractor_output"}
}
```

**CORRECT (Responses API SDK 1.109.1):**
```python
tool_choice = {
    "type": "function",
    "name": "emit_extractor_output"
}
```

**Key Insight:** Responses API uses FLAT structure, not nested `function` key.

---

### **4. File Search Tool Structure**

**WRONG (Old/Documentation):**
```python
{
    "type": "file_search",
    "file_search": {
        "vector_store_ids": ["vs_..."],
        "max_num_results": 8
    }
}
```

**CORRECT (SDK 1.109.1):**
```python
{
    "type": "file_search",
    "vector_store_ids": ["vs_..."],  # <-- FLAT, at top level
    "max_num_results": 8
}
```

**Key Insight:** `vector_store_ids` is a top-level field, not nested under `file_search`.

---

### **5. Input Message Structure**

**WRONG (Attempted in Session 1):**
```python
input=[
    {"type": "input_text", "text": "System prompt..."},
    {"type": "input_text", "text": "User prompt..."}
]
```

**CORRECT (Fixed in Session 2):**
```python
input=[
    {
        "type": "message",
        "role": "system",
        "content": [
            {"type": "input_text", "text": "System prompt..."}
        ]
    },
    {
        "type": "message",
        "role": "user",
        "content": [
            {"type": "input_text", "text": "User prompt..."}
        ]
    }
]
```

**Key Insight:** Each input must be a Message object with `type`, `role`, and `content` array.

---

## **Commit History This Session**

### **Commit `74c7fc2`**

**Message:** "fix: correct SDK 1.109.1 event type names and attribute access"

**Changes:**
1. `api/app/routers/papers.py`:
   - Event type: `response.function_call_arguments.delta` (line 450)
   - Attribute: `event.delta` (line 452)
   - Error type: `error` not `response.error` (line 45)
   - Debug logging: Print all event types (line 418)
   - Debug logging: Print captured JSON (line 544)

2. `api/app/routers/plans.py`:
   - Error type: `error` not `response.error` (line 31)

3. `docs/Claudedocs/REHYDRATION__2025-10-06_Model_Config_and_Message_Type_Fix.md`:
   - Added from Session 2 (created but never committed)

**Diff Summary:**
```diff
@@ -42,7 +42,7 @@ FILE_SEARCH_STAGE_EVENT = "response.file_search_call.searching"
 TOKEN_EVENT_TYPE = "response.output_text.delta"
 REASONING_EVENT_PREFIX = "response.reasoning"
 COMPLETED_EVENT_TYPE = "response.completed"
-FAILED_EVENT_TYPES = {"response.failed", "response.error"}
+FAILED_EVENT_TYPES = {"response.failed", "error"}

@@ -414,14 +414,12 @@ async def run_extractor(
                 with stream_manager as stream:
                     for event in stream:
                         event_type = getattr(event, "type", "")
+                        print(f"DEBUG EVENT: type={event_type}", file=sys.stderr)

-                        if event_type in ("response.function_call.arguments.delta", ...):
-                            delta_obj = getattr(event, "delta", None)
-                            if delta_obj:
-                                args_delta = getattr(delta_obj, "arguments_delta", None) or ...
+                        if event_type == "response.function_call_arguments.delta":
+                            args_delta = getattr(event, "delta", None)
+                            if args_delta:
+                                args_chunks.append(args_delta)

@@ -539,8 +539,11 @@ async def run_extractor(
         parsed_output = None
         if args_chunks:
             try:
+                raw_json = "".join(args_chunks)
+                print(f"DEBUG CAPTURED JSON: {raw_json}", file=sys.stderr)
                 validated = ExtractorOutputModel.model_validate_json(raw_json)
```

---

## **Files Modified Across All 3 Sessions**

| File | Session 1 | Session 2 | Session 3 | Total Changes |
|------|-----------|-----------|-----------|---------------|
| `api/app/agents/schemas.py` | ✅ NEW | - | - | Schema definitions |
| `api/app/agents/jsonizer.py` | ✅ NEW | - | - | JSON repair |
| `api/app/routers/papers.py` | ✅ MAJOR | ✅ MAJOR | ✅ CRITICAL | 3 sessions of fixes |
| `api/app/routers/plans.py` | - | ✅ MAJOR | ✅ MINOR | Input + error fix |
| `api/app/agents/definitions.py` | ✅ UPDATED | - | - | Prompt hardening |
| `api/app/config/settings.py` | - | ✅ NEW | - | Model config |
| `manage.py` | ✅ UPDATED | ✅ UPDATED | - | .env + models |
| `api/tests/test_schemas.py` | ✅ NEW | - | - | 5 tests |
| `api/tests/test_extractor_prompt_strict_json.py` | ✅ NEW | - | - | 3 tests |
| `api/app/services/file_search.py` | - | ✅ UPDATED | - | Input structure |

---

## **Success Criteria (Updated)**

### **✅ Achieved This Session**

- [x] Server starts without errors
- [x] OpenAI API connection verified
- [x] Model configuration correct (gpt-4o)
- [x] Extraction request succeeds (no API errors)
- [x] Event stream captured
- [x] Function call arguments captured (`args_chunks > 0`)
- [x] JSON parsing succeeds
- [x] Pydantic validation passes
- [x] Dataclass conversion works
- [x] Full pipeline operational end-to-end

### **❌ Still Pending**

- [ ] Model returns non-empty claims array
- [ ] File Search events appear in logs
- [ ] At least 1 claim extracted from paper
- [ ] Confidence scores >= guardrail threshold
- [ ] Claims written to database

---

## **For Next Session (Session 4)**

### **Immediate Tasks**

1. **Restart server** with debug logging
2. **Run extraction test** to see exact JSON returned
3. **Verify File Search** via OpenAI dashboard or API
4. **Try different paper** if current one has no claims
5. **Relax prompt** if model is being too strict

### **Investigation Questions**

1. Is vector store `vs_68e332...` actually populated with content?
2. Does paper ID `15017eb5...` actually have quantitative claims?
3. Why are File Search events never emitted?
4. Is model filtering claims due to confidence concerns?
5. Should we make more Pydantic fields optional?

### **Expected Outcomes**

**If File Search is broken:**
- Re-ingest paper
- Verify vector store status
- See File Search events in logs

**If prompt is too strict:**
- Model returns claims with relaxed prompt
- Adjust requirements to be more permissive

**If paper has no claims:**
- Try different paper
- Confirm with manual PDF review

---

## **Key Learnings**

1. **Always inspect SDK types directly** - Documentation can be outdated or incomplete
2. **Event type names matter** - Underscores vs dots is critical
3. **Attribute names must match SDK exactly** - `delta` not `arguments`
4. **Debug logging is essential** - Print ALL events to diagnose mismatches
5. **Test incrementally** - Each fix requires server restart + test
6. **Empty response is valid** - Model might be correctly returning `{"claims": []}` if no claims found
7. **Guardrails can be misleading** - Error says "low confidence" but really means "zero claims"
8. **File Search is silent** - No events = tool not used or no results

---

**Status:** 🟡 Ready for Session 4 debugging (JSON inspection + File Search investigation)
**Last Updated:** 2025-10-07
**Next Claude Session:** Start here, read this doc, run extraction test with debug logging

---

For questions or to continue debugging, consult the team or check:
- OpenAI dashboard: https://platform.openai.com/vector-stores
- Supabase dashboard: https://supabase.com/dashboard/project/.../editor
- GitHub repo: https://github.com/PIP-Team-3/pip-final-project
