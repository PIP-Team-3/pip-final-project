"""
Drift sentinel test: Extractor must use forced tool call for structured output.
"""
from pathlib import Path


def test_extractor_uses_forced_tool_call():
    """Verify extractor system prompt enforces tool call discipline."""
    p = Path("api/app/agents/definitions.py")
    text = p.read_text(encoding="utf-8")

    assert (
        "emit_extractor_output" in text
    ), "Extractor prompt must reference emit_extractor_output tool"

    assert (
        "CALL the function tool" in text and "EXACTLY ONCE" in text
    ), "Extractor prompt must explicitly instruct single tool call"

    assert (
        "Do NOT output any prose" in text
    ), "Extractor prompt must forbid prose"


def test_extractor_tool_definition_uses_pydantic():
    """Verify EMIT_EXTRACTOR_OUTPUT_TOOL uses pydantic_function_tool."""
    p = Path("api/app/routers/papers.py")
    text = p.read_text(encoding="utf-8")

    assert (
        "from ..agents.schemas import ExtractorOutputModel" in text
    ), "papers.py must import unified Pydantic schema"

    assert (
        "pydantic_function_tool" in text and "ExtractorOutputModel" in text
    ), "Tool must be created with pydantic_function_tool(ExtractorOutputModel, ...)"

    assert (
        'tool_choice = {"type": "function", "name":' in text
    ), "tool_choice must use Responses API format"


def test_extractor_prompt_cites_file_search_discipline():
    """Verify extractor prompt instructs File Search citation requirements."""
    p = Path("api/app/agents/definitions.py")
    text = p.read_text(encoding="utf-8")

    assert "File Search" in text, "Extractor prompt must reference File Search tool"
    assert (
        "source_citation" in text
    ), "Extractor prompt must require source_citation field"
