# Claudedocs - P2N Documentation Archive
> **Heads-up (2025-10-19):** The authoritative docs now live under
> `docs/current/`. Treat everything in `docs/Claudedocs/` as historical context
> and cross-check `../current/README.md` before relying on details here.
**Purpose:** Context documents for Claude Code sessions
**Last Organized:** 2025-10-07

---

## 📂 Folder Structure

### **Root Level - Start Here**
- **[CURRENT_STATUS__2025-10-07.md](CURRENT_STATUS__2025-10-07.md)** ⭐ **READ FIRST**
  - Complete system status as of Session 4
  - What's working, what's not, how to test
  - Database schema, models, configuration
  - Quick start guide for new sessions

- **[ROADMAP__Future_Work.md](ROADMAP__Future_Work.md)** 🚀 **NEXT STEPS**
  - Immediate priorities (integration, testing)
  - Near-term features (sandbox executor, gap analysis)
  - Long-term vision (multi-tenancy, web UI)
  - Proposed future prompts (C-RUN-01, C-REPORT-01, etc.)

---

### **Current_Reference/**
Active documentation used across sessions:

- **`openai-agents-and-responses-docs-compiled.md`**
  - OpenAI Responses API reference
  - SDK 1.109.1 event types and structures
  - Critical for debugging streaming issues

---

### **Archive_Completed_Sessions/**
Successful debugging sessions (for historical reference):

- **`REHYDRATION__2025-10-06_Model_Config_and_Message_Type_Fix.md`** (Session 2)
  - Fixed Responses API input structure bug
  - Fixed File Search tool structure
  - Added role-specific model configuration
  - **Key Fixes:** Message type wrapper, flat `vector_store_ids`

- **`REHYDRATION__2025-10-07_Event_Type_Debug_Session.md`** (Session 3)
  - Fixed SDK event type names (underscores vs. dots)
  - Fixed event attribute access (`event.delta` not `event.arguments`)
  - Fixed error event type (`error` not `response.error`)
  - **Key Fixes:** `response.function_call_arguments.delta`, attribute access

- **`SCHEMA_V1_NUCLEAR__Tracking_Doc.md`**
  - Schema v1 deployment (2025-10-04)
  - Full referential integrity, foreign keys, constraints
  - Team feedback integration
  - RLS permission fixes

---

### **Archive_Pre_Message_Type_Fix/**
State before Session 2 fixes (2025-10-06):

- `ROADMAP_COMPAT__Responses_Agents_v1091.md`
- `PROMPTS__Claude_Master_Pack_PostPlannerFix.md`
- `PLAYBOOK__Manual_EndToEnd_AfterPlannerFix.md`
- `SESSION_SUMMARY__Planner_Fix_Complete.md`
- `CRITICAL_ISSUE__Zombie_Servers.md`
- `CRITICAL_POSTGREST_CACHE_ISSUE.md`
- `CONTEXT_REHYDRATION__Fresh_Start.md`

**Why Archived:** These docs describe issues **before** the Message Type fix. Reference only if investigating historical context.

---

### **Archive_Pre_Event_Type_Fix/**
State before Session 3 fixes (2025-10-07):

- `PROJECT_STATUS__Comprehensive_Overview.md`
- `ROADMAP_Claude_Drift.md`

**Why Archived:** Pre-dates the event type name fixes. Superseded by Session 3 rehydration doc.

---

### **Archive_Obsolete/**
Documents no longer relevant:

- **`DB_UPGRADE_PLAN__v1_FKs_RLS.md`**
  - **Status:** Superseded by deployed `schema_v1_nuclear_with_grants.sql`
  - **Why Obsolete:** Schema v1 already deployed (2025-10-04)

- **`DOCUMENTATION_AUDIT__2025-10-06.md`**
  - **Status:** Historical audit of docs folder
  - **Why Obsolete:** Folder reorganized on 2025-10-07 (this session)

---

### **New/**
Older roadmaps and playbooks (may need review):

- `ROADMAP.md` - Early roadmap (may be outdated)
- `PLAYBOOK.md` - Manual testing procedures
- `PLAYBOOK_Verification.md` - Verification steps
- `papers_to_ingest.md` - List of papers for testing
- `claude_promptops.md` - Prompt engineering notes

**Status:** Not yet reviewed in Session 4 reorganization. May contain useful historical context or be superseded by newer docs.

---

## 🔍 How to Use This Archive

### **Starting a New Session?**
1. Read **`CURRENT_STATUS__2025-10-07.md`** for system state
2. Check **`ROADMAP__Future_Work.md`** for next priorities
3. Reference **`Current_Reference/openai-agents-and-responses-docs-compiled.md`** for SDK details

### **Debugging an Issue?**
1. Check if similar issue was fixed in **`Archive_Completed_Sessions/`**
2. Use completed session docs to understand past solutions
3. Reference SDK docs in **`Current_Reference/`**

### **Understanding Historical Context?**
1. **Pre-Message-Type:** See `Archive_Pre_Message_Type_Fix/`
2. **Pre-Event-Type:** See `Archive_Pre_Event_Type_Fix/`
3. **Obsolete Plans:** See `Archive_Obsolete/`

---

## 📊 Session Timeline

| Session | Date | Focus | Key Fixes | Doc |
|---------|------|-------|-----------|-----|
| Session 1 | 2025-10-04 | Schema deployment | Pydantic schema, tool definition | (not rehydrated) |
| Session 2 | 2025-10-06 | Message type fix | Input structure, File Search tool | `REHYDRATION__2025-10-06_...` |
| Session 3 | 2025-10-07 | Event type debug | Event names, attribute access | `REHYDRATION__2025-10-07_...` |
| Session 4 | 2025-10-07 | File Search fix | tool_choice, prompt workflow, max_tokens | `CURRENT_STATUS__2025-10-07.md` |

---

## 🗂️ Document Naming Convention

**Active Docs:**
- `CURRENT_STATUS__YYYY-MM-DD.md` - System state snapshot
- `ROADMAP__*.md` - Future plans

**Session Rehydration:**
- `REHYDRATION__YYYY-MM-DD_ShortDescription.md`

**Tracking Docs:**
- `SCHEMA_V1_NUCLEAR__Tracking_Doc.md`
- `DOCUMENTATION_AUDIT__YYYY-MM-DD.md`

**Archive Folders:**
- `Archive_Pre_{FixName}/` - State before major fix
- `Archive_Completed_Sessions/` - Successful debugging sessions
- `Archive_Obsolete/` - No longer relevant

---

## ✅ Organization Principles

1. **Start with current state** - Always update `CURRENT_STATUS` first
2. **Archive completed work** - Move session docs to `Archive_Completed_Sessions/` when fixed
3. **Mark obsolete clearly** - Move superseded docs to `Archive_Obsolete/`
4. **Preserve history** - Never delete, only archive
5. **Update this README** - When adding new folders or major docs

---

## 🧹 Maintenance Guidelines

### **When to Archive a Session Doc:**
- Issue is fully resolved
- Fixes are deployed and tested
- Session is referenced in newer `CURRENT_STATUS`

### **When to Mark Obsolete:**
- Plan is superseded by deployment
- Schema is replaced by newer version
- Roadmap is replaced by newer roadmap

### **When to Update CURRENT_STATUS:**
- Major feature completed
- System state changes significantly
- New session concludes with successful fixes

---

## 📝 Quick Reference

**Latest Status:** [CURRENT_STATUS__2025-10-07.md](CURRENT_STATUS__2025-10-07.md)
**Next Steps:** [ROADMAP__Future_Work.md](ROADMAP__Future_Work.md)
**SDK Docs:** [Current_Reference/openai-agents-and-responses-docs-compiled.md](Current_Reference/openai-agents-and-responses-docs-compiled.md)

**Last Session:** Session 4 (File Search fix) - 2025-10-07
**Last Organizer:** Claude Code (Session 4)
**Next Review:** When Session 5 begins
