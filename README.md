# constraint-engine

A general engine for "assign X to Y" problems — employee shift rostering,
teacher timetabling, student class placement — built on Google OR-Tools
CP-SAT and exposed as an MCP server that works with any MCP client and any
model.

## Principles

- **The solver computes, the agent translates.** The agent turns what the
  user says into rules from a fixed, typed catalog. It never writes solver
  code and never invents numbers; every number comes from a tool result.
- **Every rule is read back** in plain English before it is used.
- **Rules belong to the user.** When rules conflict, the engine explains
  which ones conflict and what each option leaves unmet. It never suggests
  changing or dropping a rule.
- **English first.** All user-facing text lives in one place so a locale
  can be added later.

## Status

A general constraint optimization engine for assignment problems. Items
(the rows of your sheet: students, employees, lessons) are placed into
named slots (classes, shifts, time+room cells) with attributes such as day
and shift. An item can hold one slot (placement) or several (rostering).

Every rule is one of four building blocks, each mandatory or a preference
(low/medium/high priority), each read back in plain English:

| Block | Means | Examples |
|---|---|---|
| `count` | count placements (or sum hours, sizes...) per slot, per item, per day, per column value; keep within a range or as even as possible | class size 25-28; 2 nurses per morning; 3-6 shifts each; at most 1 shift a day; at most 40 hours; Ana fixed to Monday; no teacher in two places at once; spread schools evenly; fair weekends |
| `share` | an item shares a slot with between X and Y of a list | together; apart; at least one friend from a list |
| `stretch` | lengths of worked / off stretches along time | at most 5 days in a row; days off in pairs; at most 1 free period between lessons |
| `transition` | a slot may not follow another | no morning shift after a night |

A problem is a versioned JSON **spec**, checked against the data before
solving. A solve returns 3 genuinely different options, each verified by an
independent checker, in slot names, stamped with spec and data hashes.

Next: persisting problems across server restarts, and three worked
examples (a shift roster, a teacher timetable, a class placement).

## Example spec

```json
{
  "vocabulary": {"entity": "employee", "entities": "employees", "slot": "shift", "slots": "shifts"},
  "entities": {"source": "staff.xlsx#Sheet1", "id_column": "Name"},
  "slots": [
    {"id": "mon-am", "attributes": {"day": "Mon", "shift": "morning"}},
    {"id": "mon-pm", "attributes": {"day": "Mon", "shift": "night"}}
  ],
  "settings": {"slots_per_entity": [0, 14], "seed": 42, "time_limit_seconds": 30},
  "rules": [
    {"id": "nights", "type": "count", "per_item": "all", "per_slot": "each",
     "slots": {"where": {"shift": "night"}}, "min": 1, "max": 1},
    {"id": "daily", "type": "count", "per_item": "each", "per_slot": {"attribute": "day"}, "max": 1},
    {"id": "pair", "type": "share", "item": "Ana", "with": ["Ben"], "min": 1, "mode": "soft", "priority": "high"}
  ]
}
```

Read back as:

- Every shift where shift is night has exactly 1 employee. Mandatory.
- Each employee has at most 1 shift per day. Mandatory.
- Ana and Ben share at least one shift. Preference, high priority.

## Running the MCP server

```
constraint-engine-mcp                                         # stdio, for local clients
constraint-engine-mcp --transport streamable-http --port 8000  # HTTP, at /mcp
```

Most MCP hosts take a server entry like this (adjust the path to your venv):

```json
{"mcpServers": {"constraint-engine": {"command": "D:/projects/constraint-engine/.venv/Scripts/constraint-engine-mcp.exe"}}}
```

Tools: `load_data`, `describe_data`, `set_slots`, `add_rule`, `remove_rule`,
`set_rule_active`, `list_rules`, `solve`, `get_option`, `export_option`,
`get_spec`, `set_spec`. The server's instructions tell any agent to read
each rule back to the user, to quote numbers only from tool results, and
never to change or relax a rule on its own.

## Setup

```
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Background research: [`docs/research/landscape-report.md`](docs/research/landscape-report.md).
Origin: generalized from Shibutzit (`D:\projects\shibutzit`), a Hebrew
student class-placement app.
