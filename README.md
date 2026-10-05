# constraint-engine

A general engine for "who goes where" problems: placing students into
classes, putting employees on shifts, building a weekly timetable, and
anything else of that shape. You give it a spreadsheet and describe your
rules in a chat; it returns three different, checked options.

It runs on Google OR-Tools CP-SAT (an open-source constraint solver) and is
exposed as an **MCP server**, so any MCP-capable chat client and any model
can drive it. Nothing in it is tied to one industry: a business is set up
by its data and its rules, not by code changes.

## The idea in one minute

Every problem is three things:

- **Items** — the things being placed. One row of your spreadsheet each
  (a student, an employee, a lesson).
- **Slots** — the places they can go. A list you define, each with a name
  and attributes (`{"day": "Mon", "shift": "night"}`, a class, a room-hour).
- **Rules** — what makes an assignment acceptable or better
  ("each class has 25–28 students", "nobody works nights twice in a row",
  "Ana and Ben together if possible").

The solver decides which items take which slots so the rules hold.

The chat model never writes solver code and never makes up numbers. It
only translates what you say into rules from a fixed catalog; the engine
checks each rule against your data and **reads it back in plain English**
so you can confirm it means what you meant. Rules are yours: the engine
never changes or drops one on its own. When rules can't all be met, it
tells you which ones clash and shows where each option breaks them.

## The rule catalog

Every rule is one of four building blocks. Each can be **mandatory** or a
**preference** (low / medium / high priority).

| Block | What it does | Examples |
|---|---|---|
| `count` | Count placements (or add up a number such as hours) per slot, per item, per day, per group; keep it in a range or as even as possible | class size 25–28; 2 nurses per night; 3–6 shifts each; at most 40 hours; no teacher in two places at once; spread schools evenly |
| `share` | An item shares a slot with between X and Y items from a list | keep together; keep apart; at least one friend |
| `stretch` | Lengths of runs of worked / free time units | at most 5 days in a row; days off in pairs; no gaps between lessons |
| `transition` | One slot may not be followed by another | no morning shift right after a night |

## What a solve gives you

- **Three genuinely different options**, or the three least-bad
  compromises when the rules can't all be met.
- Each option is checked by an **independent checker**, rule by rule.
- A plain-English list of what each option leaves unmet, and how the
  options compare.
- **Refine**: pick an option and get three variations of it: a small
  change, a medium change and a free change.
- Export to `.xlsx` / `.csv`, or view as a table by slot or by item.

## Quick start

Requires Python 3.12+ (developed on 3.14, Windows).

```
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Run the server:

```
constraint-engine-mcp                                          # stdio, for local chat clients
constraint-engine-mcp --transport streamable-http --port 8000  # HTTP, at /mcp
```

Most MCP clients take an entry like this (adjust the path):

```json
{"mcpServers": {"constraint-engine": {"command": "D:/projects/constraint-engine/.venv/Scripts/constraint-engine-mcp.exe"}}}
```

Then, in the chat, try one of the sample files, for example:
*"Load samples/staff.csv. Days Mon–Sun, shifts morning and night. Two
nurses every morning, one night-qualified person every night, at most one
shift a day each, no morning after a night. Solve."*

| Sample | Shape of problem |
|---|---|
| `samples/students.csv` | 24 students into classes, with schools, levels and friend requests |
| `samples/staff.csv` | a one-week roster for 8 staff |
| `samples/staff_4weeks.csv` | a four-week roster for 25 staff, with contracts, vacations and requests |
| `samples/lessons.csv` | a weekly timetable: 66 lessons, 3 classes, 7 teachers |

All sample data is fictional. Put real data in `data/`, which git ignores.

## Saving work

Every problem (its data, slots, rules and every solved round) is saved to
disk after each change and loaded back when the server starts, so nothing
is lost on a restart. The folder is `data/problems` by default; change it
with `--store <folder>` or the `CONSTRAINT_ENGINE_STORE` environment
variable. Each problem is one folder: a copy of the data file plus
`problem.json`.

## The tools

| Tool | What it does |
|---|---|
| `load_data` | Read a `.csv` / `.xlsx` and start a problem; reports the columns it found |
| `describe_data` | The columns and their kinds again |
| `set_slots` | Define the slots: a list, or a grid of attribute values (days × shifts) |
| `add_rule` / `remove_rule` / `set_rule_active` | Manage rules; every change returns the read-back |
| `list_rules` | All rules, read back |
| `solve` | A round of 3 options (or refine an earlier option) |
| `get_option` | An option as tables, one item and the rules touching it, or one slot |
| `export_option` | Write an option to `.xlsx` / `.csv` |
| `get_spec` / `set_spec` | The whole problem setup as JSON, to save or reuse |

## The problem spec

Behind the tools, a problem is a versioned JSON document. Example:

```json
{
  "vocabulary": {"entity": "employee", "entities": "employees", "slot": "shift", "slots": "shifts"},
  "entities": {"id_column": "Name"},
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

In the code, items are called **entities** (`slots_per_entity`,
`"entities"` in the spec) — same thing.

## Project layout

```
src/constraint_engine/
  spec.py              the problem spec (JSON schema, Pydantic)
  compiler.py          checks a spec against the data, turns it into solver rules
  constraints.py       the engine's rule objects and grouping helpers
  optimizer.py         builds and runs the CP-SAT model
  decision_support.py  independent checker, rounds of 3 options, comparisons
  feasibility.py       quick arithmetic checks before solving
  readback.py          plain-English read-backs of rules
  workspace.py         problems step by step, saved to disk (all tools call this)
  server.py            the MCP server
  text.py              every user-facing sentence, in one place
  dataset_schema.py, excel_loader.py   reading spreadsheets
  rules.py             Python shortcuts for building rules (used by tests)
samples/               fictional example data
tests/                 pytest suite
deploy/railway/        hosting the server with a chat front end
docs/research/         background research behind the design
AGENTS.md              design principles, architecture and plan (for developers and AI agents)
```

## Status and what's next

Working: placement, rostering and timetabling where each placement fills
one slot; the four rule blocks; 3 checked options per round; refine;
export; saving to disk; MCP server.

Known gaps, in order:

1. **Large problems**: around 1,000 items the first option is fast, but the
   second and third (which must differ) may not be found in time.
2. **Consecutive blocks**: an item that must take N slots in a row
   (along an ordered attribute such as period or hour).
3. **Items in several groups**: a cell holding a list, counted in each
   group. Today this needs one yes/no column per group.
4. **Rules from a second table**: limits that differ per group, read from a
   sheet instead of written one rule at a time.
5. **Checking an edited option**: take a hand-modified assignment, report
   what it breaks, lock parts and re-solve the rest.
6. Later, on a real need: jobs with real start times and durations
   (scheduling with time intervals), then routing.

Details and design reasoning: [AGENTS.md](AGENTS.md). Research behind the
design: [docs/research/landscape-report.md](docs/research/landscape-report.md).

Origin: forked from Shibutzit, a Hebrew class-placement app; this repo is a
separate, general product.
