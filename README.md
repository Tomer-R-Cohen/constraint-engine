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
(shift rostering), set by `SolverConfig.slots_per_entity`.

Rule types today: `capacity` (how many per slot), `load` (how many slots per
entity), `balance`, `together` / `separate` / `at_least_one_of`, `fixed`,
`partner_requests`. Every rule can be hard or soft.

Next: the versioned JSON problem spec (named slots with attributes such as
day and shift), a growing rule catalog, then the MCP tools.

## Setup

```
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Background research: [`docs/research/landscape-report.md`](docs/research/landscape-report.md).
Origin: generalized from Shibutzit (`D:\projects\shibutzit`), a Hebrew
student class-placement app.
