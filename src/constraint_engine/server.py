"""MCP server: the engine as tools any MCP client can call.

Nothing here assumes a particular client, model or vendor: the tools are
plain JSON in and out, their descriptions and the server instructions live
in text.py, and the logic is in workspace.py. Runs over stdio (local
clients) or streamable HTTP (remote clients).

    constraint-engine-mcp                                  # stdio
    constraint-engine-mcp --transport streamable-http --port 8000
"""

from __future__ import annotations

import argparse
from typing import Literal, Optional, Union

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from constraint_engine import text
from constraint_engine.spec import Rule, Slot, Vocabulary
from constraint_engine.workspace import Workspace, WorkspaceError

Scalar = Union[str, int, float, bool]


def build_server(workspace: Optional[Workspace] = None) -> MCPServer:
    ws = workspace or Workspace()
    server = MCPServer(text.SERVER_NAME, instructions=text.SERVER_INSTRUCTIONS)

    def run(call, *args, **kwargs):
        try:
            return call(*args, **kwargs)
        except WorkspaceError as error:
            raise ToolError(str(error)) from error

    @server.tool(description=text.TOOL_LOAD_DATA)
    def load_data(path: str, sheet: Optional[str] = None, header_row: int = 1, id_column: Optional[str] = None,
                  name: str = "") -> dict:
        return run(ws.load_data, path, sheet, header_row, id_column, name)

    @server.tool(description=text.TOOL_DESCRIBE_DATA)
    def describe_data(problem_id: str) -> dict:
        return run(ws.describe_data, problem_id)

    @server.tool(description=text.TOOL_SET_SLOTS)
    def set_slots(problem_id: str, slots: Optional[list[Slot]] = None, grid: Optional[dict[str, list[Scalar]]] = None,
                  vocabulary: Optional[Vocabulary] = None, slots_per_item: Optional[tuple[int, int]] = None,
                  slots_interchangeable: Optional[bool] = None) -> dict:
        return run(ws.set_slots, problem_id, slots, grid, vocabulary, slots_per_item, slots_interchangeable)

    @server.tool(description=text.TOOL_ADD_RULE)
    def add_rule(problem_id: str, rule: Rule) -> dict:
        return run(ws.add_rule, problem_id, rule)

    @server.tool(description=text.TOOL_REMOVE_RULE)
    def remove_rule(problem_id: str, rule_id: str) -> dict:
        return run(ws.remove_rule, problem_id, rule_id)

    @server.tool(description=text.TOOL_SET_RULE_ACTIVE)
    def set_rule_active(problem_id: str, rule_id: str, active: bool) -> dict:
        return run(ws.set_rule_active, problem_id, rule_id, active)

    @server.tool(description=text.TOOL_LIST_RULES)
    def list_rules(problem_id: str) -> dict:
        return run(ws.list_rules, problem_id)

    @server.tool(description=text.TOOL_SOLVE)
    def solve(problem_id: str, time_budget_seconds: Optional[float] = None, refine_option: Optional[str] = None,
              emphasis: Literal["balanced", "preferences", "balance"] = "balanced") -> dict:
        return run(ws.solve, problem_id, time_budget_seconds, refine_option, emphasis)

    @server.tool(description=text.TOOL_GET_OPTION)
    def get_option(problem_id: str, option_id: str, item: Optional[str] = None, slot: Optional[str] = None) -> dict:
        return run(ws.get_option, problem_id, option_id, item, slot)

    @server.tool(description=text.TOOL_EXPORT_OPTION)
    def export_option(problem_id: str, option_id: str, path: str) -> dict:
        return run(ws.export_option, problem_id, option_id, path)

    @server.tool(description=text.TOOL_GET_SPEC)
    def get_spec(problem_id: str) -> str:
        return run(ws.get_spec, problem_id)

    @server.tool(description=text.TOOL_SET_SPEC)
    def set_spec(problem_id: str, spec_json: str) -> dict:
        return run(ws.set_spec, problem_id, spec_json)

    return server


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="constraint-engine-mcp", description="Run the constraint engine as an MCP server.")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    server = build_server()
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
