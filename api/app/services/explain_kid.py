"""
Kid-Mode Storybook Service.

Generates grade-3 reading level storyboards with required alt-text.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from ..config.llm import agent_defaults, get_client, traced_run
from ..schemas.storybook import GlossaryEntry, Scoreboard, StoryPage

logger = logging.getLogger(__name__)

KID_MODE_SYSTEM_PROMPT = """You are a friendly science storyteller for kids (grade 3 reading level).

Your job is to explain a research paper and a reproduction experiment in simple words that an 8-year-old can understand.

Rules:
- Use short sentences (max 15 words)
- Use simple, everyday words
- Explain science concepts with comparisons to familiar things
- Be encouraging and positive
- ALWAYS include alt-text (visual description) for every page
- Create 5-7 pages total
- Include a glossary for any tricky words

Page structure:
1. Title page - What the paper is about
2-3. Background pages - Why this matters (use everyday examples)
4-5. Experiment pages - What the scientists did and what we tried
6. Results page - What happened (will be updated with actual results later)
7. (Optional) What's next page

For each page, provide:
- page_number: (1, 2, 3...)
- title: Short, fun title
- body: 2-4 short sentences explaining one idea
- alt_text: Describe what a picture would show (required!)
- visual_hint: What kind of picture would help (optional)

Return valid JSON with this structure:
{
  "pages": [...],
  "glossary": [{"term": "...", "definition": "..."}]
}
"""


def _extract_json_from_response(text: str) -> Dict[str, Any]:
    """Extract JSON from response, handling markdown code blocks."""
    text = text.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```)
        lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    return json.loads(text)


async def generate_storyboard(
    paper_id: str,
    paper_title: str,
    plan_summary: str,
) -> Dict[str, Any]:
    """
    Generate a kid-friendly storyboard for a paper.

    Args:
        paper_id: Paper identifier
        paper_title: Title of the paper
        plan_summary: Brief summary of the reproduction plan

    Returns:
        Dictionary with pages and glossary

    Raises:
        ValueError: If response is invalid or missing required fields
    """
    prompt = f"""Create a fun science storybook about this research paper:

Title: {paper_title}

What we're testing: {plan_summary}

Remember:
- 5-7 pages
- Grade 3 reading level (short, simple sentences)
- Every page MUST have alt_text
- Include a glossary for tricky words
- Be encouraging and explain why science is cool!

Return JSON only."""

    client = get_client()

    with traced_run("kid-mode-storyboard"):
        response = client.responses.create(
            model=agent_defaults.model,
            input=prompt,
            system=[{"text": KID_MODE_SYSTEM_PROMPT}],
            max_output_tokens=4000,
            temperature=0.7,  # Slightly higher for creative storytelling
        )

    output_text = getattr(response, "output_text", "")
    if not output_text:
        # Fallback assembly
        parts = []
        for item in getattr(response, "output", []) or []:
            for block in getattr(item, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
        output_text = "\n".join(parts) if parts else ""

    if not output_text:
        raise ValueError("Empty response from kid-mode agent")

    try:
        storyboard_data = _extract_json_from_response(output_text)
    except json.JSONDecodeError as exc:
        logger.error("kid.storyboard.invalid_json response=%s", output_text[:500])
        raise ValueError(f"Invalid JSON in storyboard response: {exc}")

    # Validate required fields
    if "pages" not in storyboard_data:
        raise ValueError("Storyboard missing 'pages' field")

    pages = storyboard_data.get("pages", [])
    if len(pages) < 5:
        raise ValueError(f"Storyboard has only {len(pages)} pages, need at least 5")
    if len(pages) > 7:
        raise ValueError(f"Storyboard has {len(pages)} pages, maximum is 7")

    # Validate each page has required fields
    for i, page in enumerate(pages, 1):
        if "alt_text" not in page or not page["alt_text"]:
            raise ValueError(f"Page {i} missing required alt_text")
        if "title" not in page or "body" not in page:
            raise ValueError(f"Page {i} missing title or body")

    logger.info(
        "kid.storyboard.generated paper_id=%s pages=%d glossary=%d",
        paper_id,
        len(pages),
        len(storyboard_data.get("glossary", [])),
    )

    return storyboard_data


def update_final_page_with_scoreboard(
    storyboard_json: Dict[str, Any],
    metric_name: str,
    claimed_value: float,
    observed_value: float,
    gap_percent: float,
) -> Dict[str, Any]:
    """
    Update the final page of a storyboard with actual run results.

    Args:
        storyboard_json: Original storyboard JSON
        metric_name: Name of the metric
        claimed_value: Claimed value from paper
        observed_value: Observed value from run
        gap_percent: Gap percentage

    Returns:
        Updated storyboard JSON with scoreboard
    """
    pages = storyboard_json.get("pages", [])
    if not pages:
        raise ValueError("Storyboard has no pages")

    # Update the last page with results
    final_page = pages[-1]

    # Determine if result is close or far
    if abs(gap_percent) < 5:
        verdict = "almost the same"
    elif abs(gap_percent) < 10:
        verdict = "pretty close"
    else:
        verdict = "different"

    # Create kid-friendly scoreboard text
    scoreboard_text = f"\n\nOur Scoreboard:\n"
    scoreboard_text += f"Paper's {metric_name}: {claimed_value:.2f}\n"
    scoreboard_text += f"Our {metric_name}: {observed_value:.2f}\n"
    scoreboard_text += f"How close? They're {verdict}!"

    # Append to body
    final_page["body"] = final_page.get("body", "") + scoreboard_text

    # Add scoreboard data structure
    storyboard_json["scoreboard"] = {
        "metric_name": metric_name,
        "claimed_value": claimed_value,
        "observed_value": observed_value,
        "gap_percent": gap_percent,
    }

    logger.info(
        "kid.scoreboard.updated metric=%s claimed=%.4f observed=%.4f gap=%.2f%%",
        metric_name,
        claimed_value,
        observed_value,
        gap_percent,
    )

    return storyboard_json
