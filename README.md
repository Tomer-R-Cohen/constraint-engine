# constraint-engine

A general engine for "assign X to Y" problems — employee shift rostering,
teacher timetabling, student class placement — built on Google OR-Tools
CP-SAT and exposed to AI agents (e.g. Claude) as MCP tools.

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

The solver core from Shibutzit is generalized: entities and slots instead
of students and classes, rules over any spreadsheet column, English text in
one module. An entity can hold one slot (class placement) or several
(shift rostering).

A problem is described by a versioned JSON **spec**: named slots with
attributes (day, shift, ...), typed rules with entity and slot selectors,
hard/soft mode and a priority level, and solve settings. The spec is checked
against the data before solving, every rule has a plain-English read-back,
and results come back in slot names, stamped with spec and data hashes.

Rule types today: `capacity` (how many per slot), `load` (how many slots per
entity, optionally per day/week/...), `balance`, `together` / `separate` /
`at_least_one_of`, `fixed`, `partner_requests`.

Next: a growing rule catalog (consecutive runs, rest between shifts, ...),
then the MCP tools.

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
    {"id": "nights", "type": "capacity", "slots": {"where": {"shift": "night"}}, "min": 1, "max": 1},
    {"id": "daily", "type": "load", "per": "day", "max": 1},
    {"id": "pair", "type": "together", "entity_a": "Ana", "entity_b": "Ben", "mode": "soft", "priority": "high"}
  ]
}
```

Read back as:

- Every shift where shift is night has exactly 1 employee. Mandatory.
- Each employee has at most 1 shift per day. Mandatory.
- Ana and Ben share at least one shift. Preference, high priority.

## Setup

```
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Background research: [`docs/research/landscape-report.md`](docs/research/landscape-report.md).
Origin: generalized from Shibutzit (`D:\projects\shibutzit`), a Hebrew
student class-placement app.
