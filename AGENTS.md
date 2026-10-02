# AGENTS.md

Guidance for AI coding agents working in this repository.

## What this is

A general engine for "assign X to Y" problems — employee shift rostering,
teacher timetabling, student class placement, and similar — built on Google
OR-Tools CP-SAT. It will be exposed to AI agents (e.g. Claude Desktop) as
MCP tools: the user uploads a spreadsheet and describes rules in chat, the
agent translates those into tool calls, and the engine solves.

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
6. **Reproducible.** Fixed seed; store solutions rather than relying on
   re-solving to get the same answer.

## Current state

The solver core came from Shibutzit and is now domain-neutral: entities are
the rows of a DataFrame (identified by its index), slots are numbered
0..k-1, rules address spreadsheet columns by their header, and all
user-facing text is English in `text.py`. An assignment maps each entity to
the sorted list of slots it holds; `SolverConfig.slots_per_entity` sets how
many — `(1, 1)` is placement (one slot each), a wider band is rostering.
`slots_interchangeable` (auto: on only for one slot each) decides whether
renaming slots gives the same answer.

A whole problem is described by a **spec** (`spec.py`): named slots with
attributes, the entity id column, typed rules, and settings. `compiler.py`
checks it against the data and turns each spec rule into exactly one engine
`Constraint` with the same id; `readback.py` renders each rule in plain
English. Soft rules carry a priority level (low/medium/high), never a raw
weight.

| Module | Role |
|---|---|
| `constraints.py` | `Constraint` (type + args + hard/soft + label), group selectors, default weights. Rule types: `capacity` (per-slot band, optional slot subset), `load` (per-entity band of slots held, optional subset), `balance`, `together`/`separate`/`at_least_one_of` (share / never share a slot), `fixed`, `partner_requests`. |
| `optimizer.py` | CP-SAT model. One assumption literal per hard rule → infeasibility traced to rule ids (note: `SufficientAssumptionsForInfeasibility` returns variable indices, not list positions). Flexible rules bent via slack; option diversity incl. slot-renaming symmetry; anchor/hints. |
| `decision_support.py` | `verify_assignment` (independent rule checker, per-rule `shortfall`), `PortfolioSearch` (rounds of 3: perfect vs compromise), `rank_tradeoffs` (compares options by each soft rule's shortfall). |
| `feasibility.py` | Pre-solve arithmetic checks for hard capacity and load rules (counts slot places, using the load bands). |
| `dataset_schema.py`, `excel_loader.py` | Spreadsheet loading, column-kind detection (flag/category/number), id column, entity table. |
| `spec.py` | `ProblemSpec` (Pydantic, versioned JSON): slots, vocabulary, entity source, settings, rules as a discriminated union per type; entity/slot selectors; `spec_hash`, `data_hash`. |
| `compiler.py` | `compile_spec` (checks every column/value/entity/slot reference, reports all problems at once as `SpecError`; priority → weight), `entity_table`, `solve_spec` (a round in slot ids, stamped with hashes, engine version, seed). |
| `readback.py` | `describe_rule` / `describe_spec`: read-backs assembled from templates in `text.py`. |
| `text.py` | Every user-facing string, including read-back templates and spec errors. |

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
4. Grow the rule catalog toward the 11 shapes in the research report:
   coverage/count limits, no double-booking, eligibility/availability/fixed,
   counts over a time window, consecutive runs, transitions/rest, gaps,
   spread across days, same/different/together/apart/order,
   balance/fairness, preferences.
5. MCP server on top: `load_data`, `add_rule` (returns read-back),
   `list_rules`/`remove_rule`, `solve` (3 options), `explain_conflict`,
   `why(entity)`, `export`.
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
