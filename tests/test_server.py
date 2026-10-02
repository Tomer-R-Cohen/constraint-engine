"""The MCP server: the tools as any MCP client sees them.

The last test starts the server as its own process and talks to it with
the reference MCP client over stdio -- the same way any MCP host would.
"""

import asyncio
import json
import sys

import pandas as pd
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.mcpserver.exceptions import ToolError

from constraint_engine import text
from constraint_engine.server import build_server

TOOLS = {"load_data", "describe_data", "set_slots", "add_rule", "remove_rule", "set_rule_active", "list_rules",
         "solve", "get_option", "export_option", "get_spec", "set_spec"}


@pytest.fixture
def classes_csv(tmp_path):
    path = tmp_path / "students.csv"
    pd.DataFrame({
        "Student": [f"s{i}" for i in range(1, 9)],
        "School": ["north", "south"] * 4,
        "Support": ["yes", "", "", "", "yes", "", "", ""],
        "Friends": ["s2", "s1", "", "", "", "", "", ""],
    }).to_csv(path, index=False)
    return str(path)


def run(coroutine):
    return asyncio.run(coroutine)


def payload(result):
    assert not result.is_error, result.content[0].text
    return json.loads(result.content[0].text)


def test_tools_and_instructions_are_client_neutral():
    server = build_server()
    tools = run(server.list_tools())
    assert {t.name for t in tools} == TOOLS
    add_rule = next(t for t in tools if t.name == "add_rule")
    # The rule forms reach the client as a full JSON Schema.
    schema = json.dumps(add_rule.input_schema)
    assert all(kind in schema for kind in ('"count"', '"share"', '"stretch"', '"transition"'))
    # No client, model or vendor is assumed anywhere a client reads.
    readable = " ".join([text.SERVER_INSTRUCTIONS] + [t.description for t in tools]).lower()
    assert not any(name in readable for name in ("claude", "anthropic", "openai", "chatgpt", "gpt"))


def test_a_class_placement_through_the_tools(classes_csv):
    server = build_server()

    async def flow():
        call = server.call_tool
        loaded = payload(await call("load_data", {"path": classes_csv, "id_column": "Student"}))
        pid = loaded["problem_id"]
        payload(await call("set_slots", {"problem_id": pid, "grid": {"class": ["7A", "7B"]},
                                         "vocabulary": {"entity": "student", "entities": "students",
                                                        "slot": "class", "slots": "classes"}}))
        size = payload(await call("add_rule", {"problem_id": pid, "rule": {
            "type": "count", "per_item": "all", "per_slot": "each", "min": 4, "max": 4}}))
        assert size["read_back"] == "Every class has exactly 4 students. Mandatory."
        payload(await call("add_rule", {"problem_id": pid, "rule": {
            "type": "count", "per_item": {"column": "School"}, "per_slot": "each", "even": "slots", "mode": "soft"}}))
        payload(await call("add_rule", {"problem_id": pid, "rule": {
            "type": "share", "with_column": "Friends", "min": 1, "mode": "soft", "priority": "high"}}))
        apart = payload(await call("add_rule", {"problem_id": pid, "rule": {
            "type": "count", "per_item": "all", "per_slot": "each", "items": {"column": "Support"}, "max": 1}}))
        assert apart["read_back"] == "Every class has at most 1 student marked Support. Mandatory."
        summary = payload(await call("solve", {"problem_id": pid, "time_budget_seconds": 10}))
        assert summary["mode"] == "perfect" and summary["options"]
        option = summary["options"][0]["option_id"]
        s1 = payload(await call("get_option", {"problem_id": pid, "option_id": option, "item": "s1"}))
        s2 = payload(await call("get_option", {"problem_id": pid, "option_id": option, "item": "s2"}))
        assert s1["slots"] == s2["slots"]  # friends together
        return pid

    run(flow())


def test_tool_errors_carry_readable_messages(classes_csv):
    # In process a failing tool raises; over the wire (see the stdio test)
    # the client receives it as an error result with the same message.
    server = build_server()

    async def flow():
        pid = payload(await server.call_tool("load_data", {"path": classes_csv, "id_column": "Student"}))["problem_id"]
        await server.call_tool("list_rules", {"problem_id": pid})

    with pytest.raises(ToolError, match="no slots"):
        run(flow())


def test_end_to_end_over_stdio_with_a_separate_client(classes_csv):
    params = StdioServerParameters(command=sys.executable, args=["-m", "constraint_engine.server"])

    async def flow():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert {t.name for t in listed.tools} == TOOLS
                loaded = payload(await session.call_tool("load_data", {"path": classes_csv, "id_column": "Student"}))
                pid = loaded["problem_id"]
                payload(await session.call_tool("set_slots", {"problem_id": pid, "grid": {"class": ["A", "B"]}}))
                added = payload(await session.call_tool("add_rule", {"problem_id": pid, "rule": {
                    "type": "count", "per_item": "all", "per_slot": "each", "min": 4, "max": 4}}))
                assert added["read_back"] == "Every slot has exactly 4 entities. Mandatory."
                bad = await session.call_tool("add_rule", {"problem_id": pid, "rule": {"type": "count"}})
                assert bad.is_error
                unknown = await session.call_tool("list_rules", {"problem_id": "nope"})
                assert unknown.is_error and "no problem 'nope'" in unknown.content[0].text
                summary = payload(await session.call_tool("solve", {"problem_id": pid, "time_budget_seconds": 5}))
                assert len(summary["options"]) == 3

    run(flow())
