from __future__ import annotations

import openai


def test_openai_version_guard():
    version_str = getattr(openai, "__version__", "0")
    major_component = version_str.split(".")[0]
    major = int(major_component) if major_component.isdigit() else 0
    assert major < 2, "OpenAI Python >=2.0 is not supported; pin to <2.0"
