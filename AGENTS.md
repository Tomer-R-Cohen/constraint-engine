# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this is

A general constraint optimization engine for assignment problems — employee
shift rostering, teacher timetabling, student class placement, and the rest
of that family — built on Google OR-Tools CP-SAT. It is exposed as an MCP
server usable by **any** MCP client and any model (no vendor is assumed
anywhere): the user gives a spreadsheet and describes rules in chat, the
agent translates those into tool calls, and the engine solves. The logic
lives in `workspace.py`, so other front ends (HTTP API, UI) can sit on it
the same way.

It is a fork of **Shibutzit** (`D:\projects\shibutzit`), a Hebrew web app
for placing 7th-grade students into classes. That app keeps living
separately; this repo is a new product, not a branch of it.

## Principles (non-negotiable)

1. **The solver computes, the agent translates.** The agent fills rules from
   a fixed, typed rule catalog through tool calls. It never writes solver
   code and never invents numbers — every number it shows comes from a tool
   result. Research behind this choice: LLM-written solver models are right
   only ~50–75% of the time and fail silently; template/catalog filling
   reaches ~90%. See `docs/research/landscape-report.md`.
2. **Every rule is read back in plain English**, from a template owned by
   code (not LLM prose), so the user can confirm what will be enforced.
3. **Rules belong to the user.** The engine and agent never propose, stage
   or auto-apply a rule change, and never suggest relaxing or dropping one.
   When rules can't all hold, explain which rules conflict and why, and show
   where each option's exceptions land. A rule changes only on the user's
   explicit request.
4. **Options, not a single answer.** A solve returns a round of 3 genuinely
   different options (or 3 least-bad compromises when the rules can't all
   be met), each verified by an independent checker. Target ~30 s per round.
5. **English first.** All user-facing text (rule read-backs, explanations,
   tool descriptions) lives in one place so a locale can be added later.
   No Hebrew/RTL work unless asked.
6. **General, never specific.** The engine stays general: no features,
   rule types, wording or displays shaped around one domain or one sample
   problem. Only mechanisms that work the same for any assignment problem.
   A test run is not a reason to add a special case.
7. **Reproducible.** Fixed seed; store solutions rather than relying on
   re-solving to get the same answer.

## Architecture (target)

**General core, closed set of building blocks.** The engine aims to cover
the whole assignment/scheduling family, but never by letting the agent
write free-form models (see principle 1). Generality comes from a small,
fixed catalog of general constraints that combine, not from a growing list
of domain-specific rule types.

Vocabulary: **items** (what is placed: students, employees, lessons) are the
rows of the user's sheet; **resources** (where they go: classes, shifts,
time+room cells) are named, with attributes (day, shift, room...).

**Decisions** — three kinds, built in this order:

1. **assign**: which resources each item holds (a true/false per item ×
   resource pair). Covers placement, partitioning, rostering, timetabling
   (resources = time × room). *Built.*
2. **when**: a start time and duration per item (CP-SAT interval
   variables). Covers machine/project scheduling, appointments. *Later, on
   a real use case.*
3. **order**: a sequence or route (CP-SAT circuits). Covers routing,
   sequencing. *Later, on a real use case.*

The spec and core must be shaped so 2 and 3 can be added without a rewrite.

**Constraints** — every one is: a selector (which items, which resources),
a grouping (per resource, per item, per item per day, per value of a
column...), parameters, mode (hard, or soft with priority low/medium/high),
a plain-English read-back, and an independent checker.

| Block | Means | For decision |
|---|---|---|
| **Count / Sum** | count placements (or sum a numeric column: hours, size, cost) per group, within a range or as even as possible | assign |
| **Share** | item A shares a resource with between X and Y of a list (together, apart, at least one of) | assign |
| **Stretch / Transition** | along an ordered attribute (day, period): lengths of worked/off stretches; B may not follow A | assign |
| **No-overlap / Cumulative** | intervals don't clash / stay under capacity | when |
| **Precedence** | A before B (with optional gap) | when, order |
| **Circuit** | a route visits each stop once | order |

Preferences are not a separate kind: any block in soft mode is a
preference. "How many resources per item" is an ordinary Count rule.

Known gaps, deliberately out of scope: continuous/nonlinear quantities
(CP-SAT is integer-only), very large routing (use OR-Tools routing), stable
matching. A last-resort escape hatch, only if real use demands it: a small
checked expression language over selectors, marked unconfirmed until the
user approves its read-back.

## Current state

The *assign* decision is built, with the first three building blocks.
Items are the rows of a DataFrame (identified by its index), slots are
numbered 0..k-1, and an assignment maps each item to the sorted list of
slots it holds; `SolverConfig.slots_per_entity` sets how many — `(1, 1)` is
placement, a wider band is rostering. `slots_interchangeable` (auto: on only
for one slot each) decides whether renaming slots gives the same answer.
All user-facing text is English in `text.py`.

A problem is described by a **spec** (`spec.py`): named slots with
attributes, the item id column, rules, and settings. `compiler.py` checks it
against the data and turns each spec rule into exactly one engine
`Constraint` with the same id; `readback.py` renders each rule in plain
English. Soft rules carry a priority level (low/medium/high), never a raw
weight.

| Module | Role |
|---|---|
| `constraints.py` | `Constraint` and the four engine rule types: `count` (item groups × slot groups grid, optional weights, range or even), `share` (cases: item shares with min..max of a list), `stretch` (sequences of time units; worked/off stretch lengths; ignore_edges), `transition` (forbidden slot pairs). Item selectors, item/slot grouping helpers. |
| `rules.py` | Python shortcuts building those rules (`per_slot`, `per_item`, `spread`, `fixed`, `together`, `apart`, `with_one_of`, `stretch`, `transition`). |
| `optimizer.py` | CP-SAT model. One assumption literal per hard rule → infeasibility traced to rule ids (note: `SufficientAssumptionsForInfeasibility` returns variable indices, not list positions). Every block compiles hard / soft / flexible through one `finish()`. Fractional weights counted in hundredths. Option diversity incl. slot-renaming symmetry; anchor/hints. |
| `decision_support.py` | `verify_assignment` (independent checker for every block, per-rule `shortfall`), `PortfolioSearch` (rounds of 3: perfect vs compromise), `rank_tradeoffs` (compares options by each soft rule's shortfall). |
| `feasibility.py` | Pre-solve arithmetic checks for plain hard counts (per slot / per item). |
| `dataset_schema.py`, `excel_loader.py` | Spreadsheet loading, column-kind detection (flag/category/number), id column, item table. |
| `spec.py` | `ProblemSpec` (Pydantic, versioned JSON): slots, vocabulary, item source, settings, rules (`count`, `share`, `stretch`, `transition`); item/slot selectors; `spec_hash`, `data_hash`. |
| `compiler.py` | `compile_spec` (checks every column/value/item/slot/attribute reference, reports all problems at once as `SpecError`; priority → weight), `entity_table`, `solve_spec` (a round in slot ids, stamped with hashes, engine version, seed). |
| `readback.py` | `describe_rule` / `describe_spec`: read-backs assembled from templates in `text.py`. |
| `workspace.py` | `Workspace`: problems built step by step (load data → slots → rules → solve rounds → look up / export), every round stored with its fingerprints. Client-neutral; all tools call into it. |
| `server.py` | MCP server (`MCPServer` from `mcp` 2.x) exposing the workspace as 12 tools; stdio or streamable HTTP; `constraint-engine-mcp` entry point. Tool descriptions and server instructions come from `text.py` and must stay vendor-neutral (a test checks). |
| `text.py` | Every user-facing string, including read-back templates, spec errors, tool descriptions and server instructions. |

## Plan

1. ~~Copy core + tests from Shibutzit, get tests green.~~ Done.
2. Generalize under the tests, keeping them green at every step:
   ~~student → entity, class → slot, fixed `FIELD_*` columns → column names
   from the data, Hebrew labels → English, several slots per entity~~
   (done). Slots are still bare numbers; named slots with attributes
   (day, shift) come with the spec.
3. ~~Define the problem spec: a versioned JSON document. Each rule: type,
   which entities and slots it applies to, parameters, hard/soft, priority
   level.~~ Done (`spec.py`, `compiler.py`, `readback.py`). Not yet: rule
   bundles (named rule sets shared by many entities, like nurse contracts),
   several entity types per problem (timetabling events), storing results.
4. ~~Consolidate the rule types into the building blocks for the *assign*
   decision: Count/Sum, Share, Stretch/Transition.~~ Done. Still open:
   counting "days worked" rather than slots (weekends worked), rule
   bundles (contracts). `slots_per_entity` stays a setting: it is
   structural (decides one-slot placement and slot interchangeability).
5. ~~MCP server~~ Done: `load_data`, `describe_data`, `set_slots`,
   `add_rule` (returns read-back), `remove_rule`, `set_rule_active`,
   `list_rules`, `solve` (3 options; conflicts and exceptions with
   read-backs; refine), `get_option` (whole / one item and its rules / one
   slot), `export_option`, `get_spec`/`set_spec`. Problems and rounds are saved in a store
   folder (`--store`, default `data/problems`) and survive a restart.
6. Test with three examples: a shift roster, a teacher timetable, and the
   Shibutzit class-placement sample data.

## Commands

```
py -3.14 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
```

Windows; Python 3.14. Real user data goes in `data/` (git-ignored), never in
the repo.
