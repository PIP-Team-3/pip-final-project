# Documentation Audit — Post Message Type Discovery

**Date:** 2025-10-06
**Context:** Discovered critical bug in Responses API input format (missing `"type": "message"`)
**Action:** Audit all documentation, update accurate files, archive outdated ones

---

## Executive Summary

We discovered that all Responses API calls were missing the required `"type": "message"` field at the top level of each input item. This was found by **inspecting the actual Python SDK type definitions** in `.venv/Lib/site-packages/openai/types/responses/`, not from documentation examples.

**Key Learning:** SDK types are the source of truth. Documentation examples lag behind.

---

## Files Updated ✅

### `docs/Claudedocs/New/claude_promptops.md`
**Status:** ✅ Updated with correct structure
**Changes:**
- Added warning that examples are illustrative only
- Corrected `input` structure to include `"type": "message"` at top level
- Added new section 2.3: "SDK Type Verification Protocol"
- Included Python commands to inspect SDK types
- Added error diagnosis patterns

**Keep:** ✅ **CURRENT AND AUTHORITATIVE**

---

## Files to Archive 📦

### Reason for Archiving
These files contain **outdated Responses API request examples** that omit `"type": "message"`. They were written before we discovered the correct structure via SDK inspection.

### Files to Move to `docs/Claudedocs/Archive_Pre_Message_Type_Fix/`:

1. **`CONTEXT_REHYDRATION__Fresh_Start.md`** (Oct 4)
   - Contains outdated context from earlier sessions
   - Likely has old request formats
   - **Archive:** ✅

2. **`SESSION_SUMMARY__Planner_Fix_Complete.md`** (Oct 4)
   - Historical session summary
   - May reference old patterns
   - **Archive:** ✅

3. **`PROMPTS__Claude_Master_Pack_PostPlannerFix.md`** (Oct 4)
   - Old prompt pack, superseded by `claude_promptops.md`
   - **Archive:** ✅

4. **`PLAYBOOK__Manual_EndToEnd_AfterPlannerFix.md`** (Oct 4)
   - Old manual testing playbook
   - Superseded by `New/PLAYBOOK.md` and `New/PLAYBOOK_Verification.md`
   - **Archive:** ✅

5. **`ROADMAP_COMPAT__Responses_Agents_v1091.md`** (Oct 4)
   - SDK compatibility notes, may have outdated examples
   - **Archive:** ✅

6. **`CRITICAL_ISSUE__Zombie_Servers.md`** (Oct 4)
   - Specific issue from previous session
   - Historical context only
   - **Archive:** ✅

7. **`CRITICAL_POSTGREST_CACHE_ISSUE.md`** (Oct 4)
   - Specific database issue
   - Historical context only
   - **Archive:** ✅

---

## Files to Keep Active 📌

### `docs/Claudedocs/New/` (All current)
- **`claude_promptops.md`** ✅ — Authoritative API structure guide (just updated)
- **`PLAYBOOK.md`** ✅ — Current operational playbook
- **`PLAYBOOK_Verification.md`** ✅ — Current verification steps
- **`ROADMAP.md`** ✅ — Current project roadmap
- **`ROADMAP_Claude_Drift.md`** ✅ — Drift prevention strategy
- **`papers_to_ingest.md`** ✅ — Test dataset list

### Root Level Documentation
- **`PROJECT_STATUS__Comprehensive_Overview.md`** (Oct 5, most recent) ✅
  - **KEEP AS PRIMARY REFERENCE**
  - Contains comprehensive handoff summary
  - Should be **updated** to reference the Message type fix

- **`openai-agents-and-responses-docs-compiled.md`** ✅
  - **KEEP** — Verbatim SDK documentation
  - Contains the actual examples showing `"type": "message"` structure (lines 587-594)

- **`SCHEMA_V1_NUCLEAR__Tracking_Doc.md`** ✅
  - **KEEP** — Schema versioning authority

- **`DB_UPGRADE_PLAN__v1_FKs_RLS.md`** ✅
  - **KEEP** — Database migration plan

---

## Action Items

### Immediate
- [x] Update `claude_promptops.md` with correct structure
- [x] Add SDK verification protocol
- [ ] Move 7 outdated files to `Archive_Pre_Message_Type_Fix/`
- [ ] Update `PROJECT_STATUS__Comprehensive_Overview.md` with Message type fix

### Before Next Session
- [ ] Create `docs/Claudedocs/SDK_VERIFICATION_GUIDE.md` with reusable inspection commands
- [ ] Add drift test: validate actual request payload matches SDK types
- [ ] Document this bug in postmortem: "How we fixed the Message type bug"

---

## Files to Archive (Command)

```bash
# Move outdated docs to archive
mv docs/Claudedocs/CONTEXT_REHYDRATION__Fresh_Start.md docs/Claudedocs/Archive_Pre_Message_Type_Fix/
mv docs/Claudedocs/SESSION_SUMMARY__Planner_Fix_Complete.md docs/Claudedocs/Archive_Pre_Message_Type_Fix/
mv docs/Claudedocs/PROMPTS__Claude_Master_Pack_PostPlannerFix.md docs/Claudedocs/Archive_Pre_Message_Type_Fix/
mv docs/Claudedocs/PLAYBOOK__Manual_EndToEnd_AfterPlannerFix.md docs/Claudedocs/Archive_Pre_Message_Type_Fix/
mv docs/Claudedocs/ROADMAP_COMPAT__Responses_Agents_v1091.md docs/Claudedocs/Archive_Pre_Message_Type_Fix/
mv docs/Claudedocs/CRITICAL_ISSUE__Zombie_Servers.md docs/Claudedocs/Archive_Pre_Message_Type_Fix/
mv docs/Claudedocs/CRITICAL_POSTGREST_CACHE_ISSUE.md docs/Claudedocs/Archive_Pre_Message_Type_Fix/
```

---

## Summary

**Active Documentation (10 files):**
- `docs/Claudedocs/New/` (6 files) — Current guides
- `PROJECT_STATUS__Comprehensive_Overview.md` — Primary handoff
- `openai-agents-and-responses-docs-compiled.md` — SDK reference
- `SCHEMA_V1_NUCLEAR__Tracking_Doc.md` — Schema authority
- `DB_UPGRADE_PLAN__v1_FKs_RLS.md` — DB migration

**Archived (7 files):**
- All contain outdated context from pre-fix sessions
- Moved to `Archive_Pre_Message_Type_Fix/` for historical reference

**Key Principle Going Forward:**
> **Never trust docs examples alone. Always inspect SDK types first.**
