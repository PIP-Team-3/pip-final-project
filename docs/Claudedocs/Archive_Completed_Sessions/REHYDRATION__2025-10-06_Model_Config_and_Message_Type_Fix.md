# P2N Rehydration Prompt — Post Model Config & Message Type Fix

**Date:** 2025-10-06
**Status:** Ready for testing - server restart required
**Context:** Fixed critical Responses API bugs + added model configuration management

---

## **Current State**

### **What Just Happened (This Session)**

1. **Fixed Critical Responses API Input Structure Bug**
   - Discovered `input` parameter needed `"type": "message"` at top level
   - Fixed in 4 files: papers.py, plans.py, jsonizer.py, file_search.py
   - Verified via SDK type inspection (not documentation)

2. **Fixed File Search Tool Structure**
   - Changed from nested `file_search: {vector_store_ids: [...]}`
   - To flat `vector_store_ids: [...]` at top level (SDK-verified)

3. **Added Role-Specific Model Configuration**
   - Extractor: `gpt-4o` (default) - proven stable, function calling support
   - Planner: `o3-mini` (default) - reasoning + cost-efficient
   - CLI management via `manage.py models/set-extractor/set-planner`

### **Status**
- ✅ All code changes committed and pushed (2 commits)
- ⚠️ **UNTESTED** - server needs restart
- 🔴 **Known Issue:** Extraction returns `E_EXTRACT_NO_OUTPUT` (0 tokens, 0 args_chunks)
- 🟡 **Hypothesis:** Model issue (was using gpt-4.1-mini, now switched to gpt-4o)

---

## **Repository Structure**

```
c:\Users\jakem\Projects In Programming\PIP Final Group Project\
├── api/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── schemas.py         # ✅ NEW: Pydantic models for Responses API
│   │   │   ├── jsonizer.py        # ✅ NEW: JSON repair fallback
│   │   │   ├── types.py           # Dataclasses (ExtractorOutput, Citation)
│   │   │   ├── definitions.py     # Agent prompts
│   │   │   └── runtime.py         # Tool payload builders
│   │   ├── config/
│   │   │   ├── settings.py        # ✅ UPDATED: Added role-specific models
│   │   │   └── llm.py             # OpenAI client, agent defaults
│   │   ├── routers/
│   │   │   ├── papers.py          # ✅ UPDATED: Fixed input structure, uses extractor model
│   │   │   └── plans.py           # ✅ UPDATED: Fixed input structure, uses planner model
│   │   └── services/
│   │       └── file_search.py     # ✅ UPDATED: Fixed input structure
│   └── tests/
│       ├── test_schemas.py              # ✅ NEW: Schema validation (5 tests)
│       └── test_extractor_prompt_strict_json.py  # ✅ NEW: Drift detection (3 tests)
├── docs/Claudedocs/
│   ├── New/
│   │   └── claude_promptops.md          # ✅ UPDATED: SDK verification protocol
│   ├── Archive_Pre_Message_Type_Fix/    # ✅ NEW: Archived 7 outdated docs
│   ├── DOCUMENTATION_AUDIT__2025-10-06.md  # ✅ NEW: Audit report
│   └── PROJECT_STATUS__Comprehensive_Overview.md  # Primary handoff doc
├── manage.py                        # ✅ UPDATED: Model config commands
└── .env                             # ⚠️ NOT IN GIT - contains secrets
```

---

## **Critical Fixes Applied**

### **1. Responses API Input Structure (SDK 1.109.1)**

**Discovery Method:** Direct SDK type inspection (NOT documentation)

**The Bug:**
```python
# BEFORE (WRONG):
input=[
    {"type": "input_text", "text": "..."}  # ❌ Invalid at top level
]
```

**The Fix:**
```python
# AFTER (CORRECT):
input=[
    {
        "type": "message",           # ✅ Required at top level
        "role": "system",            # ✅ Literal["user", "system", "developer"]
        "content": [
            {"type": "input_text", "text": "..."}  # ✅ Valid in content array
        ]
    }
]
```

**SDK Evidence:**
```python
from openai.types.responses.response_input_param import Message
# Message.__annotations__ shows:
#   type: Required[Literal["message"]]
#   role: Required[Literal["user", "system", "developer"]]
#   content: ResponseInputMessageContentListParam
```

**Files Fixed:**
- api/app/routers/papers.py (lines 349-377)
- api/app/routers/plans.py (lines 134-163)
- api/app/agents/jsonizer.py (lines 41-64)
- api/app/services/file_search.py (lines 33-43)

---

### **2. File Search Tool Structure**

**Discovery Method:** SDK FileSearchToolParam inspection + API error messages

**The Bug:**
```python
# BEFORE (WRONG):
{
    "type": "file_search",
    "file_search": {                    # ❌ Nesting not allowed
        "vector_store_ids": ["vs_..."],
        "max_num_results": 8
    }
}
```

**The Fix:**
```python
# AFTER (CORRECT):
{
    "type": "file_search",
    "vector_store_ids": ["vs_..."],  # ✅ At top level (Required)
    "max_num_results": 8              # ✅ At top level (optional)
}
```

**SDK Evidence:**
```python
from openai.types.responses.file_search_tool_param import FileSearchToolParam
# FileSearchToolParam.__annotations__:
#   type: Required[Literal['file_search']]
#   vector_store_ids: Required[SequenceNotStr[str]]  # Top level!
#   max_num_results: int
```

**File Fixed:**
- api/app/routers/papers.py (lines 333-340)

---

### **3. Model Configuration System**

**Added to settings.py:**
```python
# Role-specific models (preferred)
openai_extractor_model: str = "gpt-4o"   # Options: gpt-4o, o3-mini
openai_planner_model: str = "o3-mini"    # Options: o3-mini, gpt-5
```

**Why These Models:**
- **gpt-4o**: Proven stable with Responses API, function calling, structured outputs
- **o3-mini**: Reasoning capabilities, cost-efficient, strong STEM/coding
- **Avoiding gpt-4.1-mini**: Known issues with `response_format=json_schema` (as of April 2025)

**New manage.py Commands:**
```bash
python manage.py models                    # Show current config
python manage.py set-extractor gpt-4o      # Set extractor model
python manage.py set-planner o3-mini       # Set planner model
python manage.py pwsh-env                  # PowerShell .env loader
```

---

## **Current Issue: E_EXTRACT_NO_OUTPUT**

### **Symptoms:**
```
extractor.no_valid_output paper_id=... args_chunks=0 tokens=0
```
- API request succeeds (no 400 error)
- Stream starts (`event: extract_start`)
- Model produces **0 tokens** and **0 function call arguments**
- JSONizer fallback also fails (no tokens to rescue)

### **Potential Causes (Ranked by Likelihood):**

1. **🔴 MOST LIKELY: Event Type Mismatch**
   - Code listens for: `"response.function_call.arguments.delta"`
   - SDK docs mention: `"response.function_call_arguments.delta"` (underscore vs dot)
   - If wrong, we never capture args_chunks

2. **🟡 LIKELY: Model Issue**
   - Was using `gpt-4.1-mini` (has known issues)
   - Now switched to `gpt-4o` (needs testing)

3. **🟡 POSSIBLE: Vector Store Empty/Inaccessible**
   - File search might fail silently
   - Model has no context, produces nothing

4. **🟢 LESS LIKELY: Tool Choice Format**
   - Current: `{"type": "function", "name": "emit_extractor_output"}`
   - Might need different format for SDK 1.109.1

### **Debug Strategy:**
1. Add comprehensive event logging to see ALL event types
2. Check if model is actually using gpt-4o after restart
3. Verify vector store has documents
4. Test with simplified prompt

---

## **Next Steps (For Next Session)**

### **Immediate Actions:**

1. **Restart Server**
   ```bash
   python manage.py start
   ```

2. **Verify Model Configuration**
   ```bash
   python manage.py models
   curl http://localhost:8000/internal/config/doctor
   ```

3. **Run Extraction Test**
   ```bash
   curl -sS -X POST -N "http://localhost:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/extract" | tee extract_test.log
   ```

4. **Check Server Logs For:**
   - `DEBUG extractor.model=gpt-4o` (confirms model switch)
   - `DEBUG extractor.tools=[...]` (confirms structure)
   - ALL event types emitted during stream

### **If Still No Output:**

**Add Event Logging:**
```python
# In papers.py after line 417:
event_type = getattr(event, "type", "")
print(f"DEBUG EVENT: type={event_type}", file=sys.stderr)
```

**Check Event Type Names:**
- Look for function_call events in logs
- Verify actual event name matches what we're listening for
- Update event type strings if needed

---

## **Environment Configuration**

### **Required .env Variables:**
```bash
# OpenAI (REQUIRED)
OPENAI_API_KEY=sk-proj-...

# Model Configuration (OPTIONAL - has defaults)
OPENAI_EXTRACTOR_MODEL=gpt-4o    # Default if not set
OPENAI_PLANNER_MODEL=o3-mini     # Default if not set

# Supabase (REQUIRED)
SUPABASE_URL=https://...supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJh...
SUPABASE_ANON_KEY=eyJh...
```

### **Load .env in PowerShell:**
```powershell
Get-Content .env | % { if ($_ -match '^\s*([^#=]+)=(.*)$') { Set-Item -Path ('Env:' + $matches[1].Trim()) -Value ($matches[2].Trim().Trim('"')) } }
```

---

## **Key Files to Review**

### **For Debugging Extraction:**
1. `api/app/routers/papers.py` (lines 397-620)
   - Stream event handling
   - Tool call argument capture
   - JSONizer fallback logic

2. `api/app/agents/schemas.py`
   - Pydantic models for validation
   - Must match types.py dataclass structure

3. `docs/Claudedocs/New/claude_promptops.md`
   - SDK verification protocol
   - Correct request structure examples

### **For Model Configuration:**
1. `api/app/config/settings.py`
   - Role-specific model settings
   - Environment variable mapping

2. `manage.py`
   - Model management commands
   - .env file updater

---

## **Testing Checklist**

- [ ] Server restarts successfully
- [ ] `python manage.py models` shows correct config
- [ ] `/health` endpoint returns 200
- [ ] `/internal/config/doctor` shows `openai_extractor_model` and `openai_planner_model`
- [ ] Extraction attempt shows `DEBUG extractor.model=gpt-4o` in logs
- [ ] Extraction produces output (event: result with claims)
- [ ] If no output, logs show what events ARE being emitted

---

## **Key Learnings**

1. **Never trust documentation examples** - SDK types are the source of truth
2. **Always inspect SDK __annotations__** to verify structure
3. **Model selection matters** - gpt-4.1-mini has compatibility issues
4. **Event type names must match exactly** - underscore vs dot matters
5. **Settings are cached** - server restart required for config changes

---

## **Commits This Session**

1. **2888b1a** - fix: correct Responses API input structure for SDK 1.109.1
   - Fixed Message type structure (4 files)
   - Fixed file_search tool structure
   - Added Pydantic schemas
   - Updated documentation

2. **57eb402** - feat: add role-specific model configuration with CLI management
   - Added extractor/planner model settings
   - Updated routers to use role-specific models
   - Added manage.py model commands
   - ⚠️ **UNTESTED**

---

## **Quick Start Commands**

```bash
# Check model configuration
python manage.py models

# Start server
python manage.py start

# Test extraction (in another terminal)
curl -sS -X POST -N "http://localhost:8000/api/v1/papers/15017eb5-68ee-4dcb-b3b4-1c98479c3a93/extract"

# If needed: Set different models
python manage.py set-extractor o3-mini
python manage.py set-planner gpt-5
# Then restart server
```

---

## **For Next Claude Session**

**Read these files first:**
1. This rehydration doc (you're reading it)
2. `docs/Claudedocs/New/claude_promptops.md` - API invariants
3. `docs/Claudedocs/PROJECT_STATUS__Comprehensive_Overview.md` - Project context

**Immediate task:**
1. Restart server
2. Test extraction with gpt-4o
3. Debug why `args_chunks=0` and `tokens=0`
4. Focus on event type investigation

**Remember:**
- SDK 1.109.1 is installed
- Responses API (NOT Chat Completions)
- All tests passing (8/8)
- Code is correct, likely event handling issue

---

**Status:** 🟡 Ready for testing - awaiting server restart and extraction test
