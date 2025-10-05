# Claude Test Suite Add‑Ons (vNext)
_Last updated: 2025-10-04_

This pack outlines additional tests to harden the system for the next milestones. These are **descriptions + example snippets** you can convert into `api/tests/*.py` files.

---

## 1) Redaction Edge Cases

**Goal:** Ensure no secrets or signed URL tokens leak.

**Cases**
- Doctor redacts query strings for all artifact URLs.
- Redaction when the URL has multiple query params and fragments.
- API key redaction for `sk-` and `sk-proj-` patterns inside nested objects.

**Example assertion**
```python
from app.utils.redaction import redact_signed_url, redact_api_key

def test_redact_signed_url_multikeys():
    raw = "https://x.com/a?token=abc&sig=xyz#frag"
    out = redact_signed_url(raw)
    assert out.endswith("?#<redacted>")

def test_redact_api_key_variants():
    assert "sk-***" in redact_api_key("sk-abc123")
    assert "sk-proj-***" in redact_api_key("sk-proj-xyz543")
```

---

## 2) Kid‑Mode Validation Edges

**Goal:** Storybook is always accessible and age‑appropriate.

**Cases**
- Reject page set with <5 or >7 pages.
- Reject missing alt‑text anywhere.
- Glossary must be present and non‑empty.

**Snippets**
```python
def test_story_too_few_pages(client):
    # build request with 4 pages -> expect E_STORY_TOO_FEW_PAGES
    ...

def test_story_missing_alt_text(client):
    # one page missing altText -> expect E_STORY_MISSING_ALT_TEXT
    ...
```

---

## 3) Report Artifacts Contract

**Goal:** Report endpoint always provides usable artifacts.

**Cases**
- Metrics URL present and valid.
- Logs URL present; events URL optional.
- gap_percent sign and rounding stable.

**Snippet**
```python
def test_report_artifacts_contract(client):
    data = client.get(f"/api/v1/papers/{{paper}}/report").json()
    assert "metrics_url" in data["artifacts"]
    assert data["artifacts"]["metrics_url"].startswith("https://")
    assert abs(data["gap_percent"] - round(data["gap_percent"], 2)) < 1e-6
```

---

## 4) SSE Close Semantics

**Goal:** Streams always terminate and replay history once.

**Cases**
- Manager replays history to late subscribers then switches to live‑only.
- Close signal is sent exactly once.

**Snippet**
```python
def test_sse_replay_then_live(client):
    # start run -> attach -> detach -> reattach -> ensure history length constant and new events appended
    ...
```

---

## 5) Prep Tests for Cache/Retry/Leaderboard

**Cache**
- Record hit/miss counters; doctor shows totals.
- Runner emits `cache_probe` stage.

**Retry**
- `POST /api/v1/runs/{run_id}/retry` creates a new run referencing previous artifacts.

**Leaderboard**
- Sorting adheres to metric direction; stable across ties.

---

## Execution Notes

- Keep SSE integration tests **skipped** in CI if they require wall time.
- Use async monkeypatch at import site (`app.routers.runs.execute_notebook`) to avoid kernel start.
- Provide dummy env in `conftest.py` for sealed test envs.
