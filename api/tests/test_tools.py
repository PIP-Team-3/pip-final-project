import pytest

from app.agents.base import AgentRole
from app.agents.tooling import HOSTED_TOOLS, ToolUsageTracker
from app.tools import ToolUsagePolicyError, ToolValidationError, function_tools


def test_tool_usage_tracker_enforces_limits():
    tracker = ToolUsageTracker()
    spec = HOSTED_TOOLS["file_search"]
    for _ in range(spec.max_calls):
        tracker.record_call("file_search")
    with pytest.raises(ToolUsagePolicyError):
        tracker.record_call("file_search")


def test_env_lock_builder_disallows_unsupported_packages():
    with pytest.raises(ToolValidationError):
        function_tools.call(
            "env_lock_builder",
            {"python_version": "3.11.9", "packages": ["cuda==12.0"]},
        )


def test_agent_role_tool_mappings():
    planner_tools = function_tools.get("dataset_resolver")
    assert planner_tools.openai_tool is not None
    assert AgentRole.PLANNER in HOSTED_TOOLS["file_search"].allowed_roles
