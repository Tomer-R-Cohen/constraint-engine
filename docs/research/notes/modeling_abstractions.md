# Modeling abstractions and data models for assignment, rostering and timetabling

Scope: which abstraction a general "assign X to Y" engine (target: Python + OR-Tools CP-SAT) should adopt to cover shift rostering, school timetabling, student class placement and room allocation. Research date: 2026-10-02. Note: several primary pages (Timefold GitHub quickstart source, HSEval spec at jeffreykingston.id.au, schedulingbenchmarks.org format page, UniTime and aSc docs) could not be fetched in this session (404s, connection refused, or paywalls). Those items are flagged in Gaps rather than filled from memory.

## How do established tools model these problems?

### Takeaway
Every mature tool uses the same structure: fixed **facts** (times/slots, resources typed by kind, groups of either) plus **demands/events/entities** that carry decision variables (time, resource), plus a **library of parameterized, named constraint types** with a per-instance hard/soft flag and weight. They differ mostly in syntax (Timefold: annotated classes + code streams; XHSTT/ITC2019/INRC-II: declarative files with a fixed constraint vocabulary; OR-Tools/MiniZinc: low-level primitives and global constraints).

### Cited Findings

**Timefold / OptaPlanner**
- School timetabling quickstart: the solver "changes the timeslot and room fields of the Lesson class"; both fields carry `@PlanningVariable` and `Lesson` is the `@PlanningEntity`; Timeslot and Room are problem facts. — [Timefold docs search snippet, school-timetabling quickstart](https://docs.timefold.ai/timefold-solver/latest/quickstart/shared/whatyoubuild)
- Constraints are written in a `ConstraintProvider` with the Constraint Streams API "inspired by Java Streams and SQL", using incremental score calculation. Hard: room conflict (a room has at most one lesson at a time), teacher conflict, student-group conflict. — [Timefold school timetabling constraints](https://docs.timefold.ai/timefold-solver/1.x/quickstart/shared/school-timetabling/school-timetabling-constraints)
- Soft constraints in the same quickstart: teacher room stability ("a teacher prefers to teach all lessons in the same room") and student-group subject variety ("a student dislikes sequential lessons on the same subject"). — [optapy school timetabling notebook / Timefold docs search results](https://nbviewer.org/github/optapy/optapy-quickstarts/blob/stable/school-timetabling/school-timetabling-quickstart.ipynb)
- Timefold's commercial Employee Shift Scheduling model uses a **HardMediumSoft** score: hard = non-negotiable (e.g., required skills), **medium = "assign as many mandatory shifts as possible"** (unassigned work when resources are scarce), soft = business goals (cost, fairness). Example score `0hard/-257medium/-6119520soft`. — [Timefold Employee Shift Scheduling constraints](https://docs.timefold.ai/employee-shift-scheduling/latest/user-guide/constraints)
- Weights: final score = weight x match score; soft weight default 1; max weight 1 trillion (overflow guard); weight 0 disables a constraint; weights set via reusable configuration profiles or per-dataset JSON `config.model.overrides`. — [Timefold Employee Shift Scheduling constraints](https://docs.timefold.ai/employee-shift-scheduling/latest/user-guide/constraints)
- Timefold's employee-scheduling constraint categories: employee contracts, priority, pairing, travel/locations, breaks, activation, work limits, time off, shift rotations/patterns, shift type diversity, fairness; shift-service side: alternative shifts, cost management, demand-based scheduling, priority/optional shifts, skills/risk factors, shift assignments. — [Timefold Employee Shift Scheduling constraints](https://docs.timefold.ai/employee-shift-scheduling/latest/user-guide/constraints)

**XHSTT (high school timetabling, ITC2011)**
- An instance has four parts: Times (sequence = "cycle", usually one week; arbitrary time groups such as Monday or afternoons; days/weeks are labelled time groups), Resources (partitioned into resource types such as Teacher, Room, Class, Student, and any number of others; resource groups such as "Science laboratories"), Events, and Constraints. — [Post et al., "The Third International Timetabling Competition", Ann Oper Res 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)
- An Event has a fixed integer duration, a time (preassigned or open) and any number of event resources; each event resource may be preassigned or open, but its resource type is fixed. Example: class 7A + teacher Smith + one open Rooms resource, duration 2; a constraint then says the room should come from the ScienceLaboratories group. Courses are event groups. — [Post et al. 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)
- Splitting is modeled, not pre-decided: "class 7A might need to meet for Science for a total duration of 6 ... in events of duration 1 or 2, with at least one event of duration 2" is a single event of duration 6 plus split constraints. — [Post et al. 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)
- Constraint types in the ITC2011 report (15): Assign Resource, Assign Time, Split Events, Distribute Split Events, Prefer Resources, Prefer Times, Avoid Split Assignments, Spread Events, Link Events, Avoid Clashes, Avoid Unavailable Times, Limit Idle Times, Cluster Busy Times (busy on a limited number of days), Limit Busy Times (busy a limited number of times each day), Limit Workload. — [Post et al. 2013, Table 1](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf). A later source counts 16 constraint types; I infer the 16th is Order Events, but did not confirm it. — [arXiv 2407.16898](https://arxiv.org/pdf/2407.16898)
- "Any constraint may be declared hard or soft and no constraint is predefined as such"; each constraint has parameters (which events/resources, to what extent, weight). — [arXiv 2407.16898 (search summary)](https://arxiv.org/pdf/2407.16898); [UTwente XHSTT tutorial](https://www.utwente.nl/en/eemcs/dmmp/hstt/tutorial)
- Scoring: infeasibility value = sum over hard constraints of violations x weight; objective value = same over soft; comparison is lexicographic (infeasibility first). — [Post et al. 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)
- Usability signal: ITC2011 had 17 registrations and 5 submitting teams, vs over 100 registrations / ~40 active teams for ITC2007; organizers cite "the complexity of the format, which was remarked upon by several participants" as a possible reason. — [Post et al. 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)

**INRC-II (nurse rostering)**
- Hard: H1 at most one shift per nurse per day; H2 coverage >= minimum per shift per skill; H3 shift-type successions must be legal (forbidden successor pairs); H4 a shift of a skill must be filled by a nurse with that skill. — [INRC-II problem description (Ceschia et al.), arXiv 1501.04177](https://ar5iv.labs.arxiv.org/html/1501.04177)
- Soft with weights: S1 optimal coverage shortfall (30); S2 min/max consecutive assignments per shift type (15) and global consecutive working days (30); S3 consecutive days off (30); S4 undesired shift/day-off preferences (10); S5 complete weekends (30); S6 total assignments within contract min/max (20); S7 max working weekends (30). — [INRC-II, arXiv 1501.04177](https://ar5iv.labs.arxiv.org/html/1501.04177)
- File structure: Scenario (shift types with min/max consecutive and forbidden successors; contracts with min/max total assignments, min/max consecutive working days and days off, max working weekends, complete-weekend flag; nurses with contract and skills), Week data (min and optimal requirement per shift/skill/day; nurse requests), History (border state: last shift, consecutive counters, cumulative totals). — [INRC-II, arXiv 1501.04177](https://ar5iv.labs.arxiv.org/html/1501.04177)
- The key structural idea is **contracts**: constraints are parameterized per contract and nurses reference a contract rather than carrying their own rules. — [INRC-II, arXiv 1501.04177](https://ar5iv.labs.arxiv.org/html/1501.04177)

**Curtois / schedulingbenchmarks.org nurse rostering**
- Instances include shift-on requests (an employee wants a specific shift), shift-off requests, and per-day cover requirements given as minimum, maximum or preferred cover per shift type or time period. — [Curtois/Qu benchmark, search summaries of Stirling and UTwente papers](https://ris.utwente.nl/ws/files/5391711/DaysOffScheduling.pdf)
- CPMpy ships a loader for these instances (`cpmpy.tools.datasets.nurserostering`, `load_nurserostering()`). — [CPMpy docs](https://cpmpy.readthedocs.io/en/logo/api/tools/datasets/nurserostering.html)

**ITC 2019 (university course timetabling, UniTime lineage)**
- Data model: courses -> configurations -> subparts (lecture/lab/tutorial) -> classes; each class has candidate times (bit-string patterns over weeks, days, start, length) and candidate rooms with penalties; rooms have capacity and unavailability; students have course demands (student sectioning combined with time/room assignment is the novelty). — [Holm et al., MIP formulation of ITC2019, DTU](https://backend.orbit.dtu.dk/ws/files/221992887/A_MIP_Formulation_of_the_International_Timetabling_Competition_2019_Problem.pdf); [ITC2019 problem scope summaries](https://link.springer.com/article/10.1007/s10951-023-00801-w)
- Objective = weighted sum of time penalty, room penalty, distribution penalty and student conflicts. — [DTU MIP paper](https://backend.orbit.dtu.dk/ws/files/221992887/A_MIP_Formulation_of_the_International_Timetabling_Competition_2019_Problem.pdf)
- Distribution constraint vocabulary (each can be required or carry a penalty): SameStart, SameTime, DifferentTime, SameDays, DifferentDays, SameWeeks, DifferentWeeks, Overlap, NotOverlap, SameRoom, DifferentRoom, SameAttendees, Precedence, WorkDay(S), MinGap(G), MaxDays(D), MaxDayLoad(S), MaxBreaks(R,S), MaxBlock(M,S). — [DTU MIP paper](https://backend.orbit.dtu.dk/ws/files/221992887/A_MIP_Formulation_of_the_International_Timetabling_Competition_2019_Problem.pdf) (the fetched summary listed the core names; the parameterized forms in parentheses come from my knowledge of the spec and should be checked against the official ITC2019 format page)

**FET (school timetabling, open source)**
- Students are organized as years -> groups -> subgroups (subgroup is the smallest independent unit; groups/years may overlap for electives); also teachers, subjects, activity tags, rooms, buildings. An activity is "a coupling of one or more teachers, a subject and one or more students set". — [FET FAQ](https://lalescu.ro/liviu/fet/doc/en/faq.html)
- Constraints are split into time constraints (days/hours, min spacing between activities, preferred slots, max daily hours, early/late) and space constraints (preferred rooms, room availability). — [FET FAQ](https://lalescu.ro/liviu/fet/doc/en/faq.html)
- Every constraint has a weight percentage: 100% = hard (must hold); <100% = soft, which in FET's algorithm effectively means "how hard to try before giving up" rather than a penalty coefficient. — [FET FAQ](https://lalescu.ro/liviu/fet/doc/en/faq.html)

**OR-Tools CP-SAT shift scheduling example**
- Decision variables are Booleans work[e, s, d] (employee, shift, day); the example is driven by data tables rather than bespoke code. — [OR-Tools shift_scheduling_sat.py](https://raw.githubusercontent.com/google/or-tools/stable/examples/python/shift_scheduling_sat.py)
- `shift_constraints` tuples `(shift, hard_min, soft_min, min_cost, soft_max, hard_max, max_cost)` bound consecutive run lengths, e.g. `(0, 1, 1, 0, 2, 2, 0)` = 1-2 consecutive rest days. `weekly_sum_constraints` use the same 7-tuple for weekly totals, e.g. `(0, 1, 2, 7, 2, 3, 4)`. — [OR-Tools shift_scheduling_sat.py](https://raw.githubusercontent.com/google/or-tools/stable/examples/python/shift_scheduling_sat.py)
- `penalized_transitions` `(prev_shift, next_shift, penalty)` with penalty 0 meaning forbidden (e.g. night -> morning); `requests` `(employee, shift, day, weight)` with negative = desired; `weekly_cover_demands` per day per shift; `excess_cover_penalties` per shift. — [OR-Tools shift_scheduling_sat.py](https://raw.githubusercontent.com/google/or-tools/stable/examples/python/shift_scheduling_sat.py)
- Helpers `add_soft_sequence_constraint` and `add_soft_sum_constraint` implement the hard/soft band pattern (hard outside [hard_min, hard_max], linear cost outside [soft_min, soft_max]); all penalties are summed into one minimized linear objective. — [OR-Tools shift_scheduling_sat.py](https://raw.githubusercontent.com/google/or-tools/stable/examples/python/shift_scheduling_sat.py)

**MiniZinc global constraints (vocabulary reference)**
- Relevant globals: `all_different`; `global_cardinality(vars, values, occurs)` (+ `_closed`); `cumulative(start, duration, resource, capacity)`; `disjunctive(start, duration)`; `regular(vars, states, transitions, initial, accepting)` for automaton-defined sequences; `bin_packing`/`bin_packing_capa`; `sliding_sum(low, high, window, vars)`; `count`, `among`; `table`; `value_precede`; `lex2` for symmetry breaking. — [MiniZinc global constraints library](https://docs.minizinc.dev/en/stable/lib-globals.html)

### Inferences
- Two families exist: (a) **declarative instance formats with a closed constraint vocabulary** (XHSTT, INRC-II, ITC2019, FET) and (b) **programmatic models** (Timefold, CP-SAT, MiniZinc, CPMpy). A chat-driven engine needs (a) as its spec (so an LLM can emit/edit it and a manager can read it) compiled to (b).
- The OR-Tools example's 7-tuple `(hard_min, soft_min, min_cost, soft_max, hard_max, max_cost)` is a reusable "band" primitive that unifies hard and soft bounds for counts, sums and run lengths. It is the most directly portable idea for a CP-SAT engine.
- CP-SAT has native equivalents for the MiniZinc globals that matter (AddAllDifferent, AddNoOverlap/AddCumulative with interval variables, AddAutomaton for `regular`, AddAllowedAssignments for `table`) — based on general OR-Tools knowledge, not a source fetched here.

### Gaps
- Could not fetch the Timefold quickstart source code (GitHub paths 404'd) to quote exact employee-scheduling constraints (e.g. required skill, no overlap, min hours between shifts, one shift per day, unavailable/undesired/desired dates, balance). Search snippets mention them but are not reliable enough to cite as exact names.
- HSEval spec (jeffreykingston.id.au) was unreachable, so XHSTT cost functions (Linear/Quadratic/Step) and the exact 16th constraint were not confirmed.
- No UniTime, aSc Timetables or CPMpy-specific modeling docs were retrieved. aSc is closed-source; its data model was not researched.

## What is the common core across them?

### Takeaway
The shared core is: **Slots** (ordered time units grouped into days/weeks) + **typed Resources** (with groups/tags and attributes like skills or capacity) + **Demands/Events** (need N resources of a type, at some time, for some duration) + an **assignment relation** + a small set of constraint *shapes* applied to a selector of resources/events: cardinality/coverage, no-overlap, availability/domain restriction, sequence/pattern, distribution/spread, linking (same/different), balance, and preference.

### Cited Findings
- XHSTT already generalizes teachers, rooms, classes and students into "resources" of user-defined types, and lessons into events with open/preassigned time and resource slots. — [Post et al. 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)
- XHSTT's constraints split cleanly into event-side (assign, prefer, split, spread, link, avoid split assignments) and resource-side (avoid clashes, unavailable times, idle times, busy days, busy times per day, workload). — [Post et al. 2013, Table 1](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)
- INRC-II's model is the same core with days as slot groups, shifts as sub-slots, skills as resource attributes, and coverage as per-(day, shift, skill) demand with min and optimal levels. — [INRC-II](https://ar5iv.labs.arxiv.org/html/1501.04177)
- Timefold's school model is entity (Lesson) x variables (timeslot, room) over fact value ranges; constraints are pairwise joins (`forEachUniquePair` with equal timeslot and equal resource = conflict). — [Timefold school timetabling constraints](https://docs.timefold.ai/timefold-solver/1.x/quickstart/shared/school-timetabling/school-timetabling-constraints)
- ITC2019 adds a hierarchy (course -> config -> subpart -> class) and student sectioning, i.e. assigning students to classes, which is the same core as "class placement". — [DTU MIP paper](https://backend.orbit.dtu.dk/ws/files/221992887/A_MIP_Formulation_of_the_International_Timetabling_Competition_2019_Problem.pdf)

### Inferences
- A minimal general data model:
  - `Slot{id, order, day, period, start, length, tags}`, `SlotGroup{id, slots}` (days, weekends, mornings).
  - `Resource{id, type, attributes{skills, capacity, contract, gender, level...}, tags}`, `ResourceGroup`.
  - `Demand/Event{id, duration, time: fixed|domain, roles:[{type, count, allowed: group/filter, fixed?}], tags}`. Shift rostering: demand = (day, shift, skill) with count = coverage. Timetabling: event = lesson with roles teacher/class/room. Placement: demand = class "seat bucket" with role student and count = capacity, or flip it: entity = student, variable = class.
  - `Constraint{type, selector (which resources/events), params, mode: hard|soft, weight, priority_level}`.
- Two variable directions both appear: "resource -> slot" (rostering Booleans x[e,d,s]) and "event -> slot/resource" (timetabling). In CP-SAT both reduce to a Boolean x[demand_role, resource, slot] (or x[event, slot] plus x[event, resource]), so one engine can host both, with domain pruning from availability/skills/prefer constraints.
- The "contract" pattern (INRC-II) generalizes to "a named rule bundle attached to a set of resources", which keeps specs short.

### Gaps
- No single published survey was retrieved that explicitly proposes a unified cross-domain schema; the synthesis above is my inference from the formats.

## Which constraint types recur in each domain?

### Takeaway
Rostering is dominated by **coverage, single-assignment-per-day, forbidden successions/min rest, consecutive-run bounds, totals per period, weekends, skills, requests and fairness**. School timetabling is dominated by **no-clash per resource, required hours per subject/course, availability, idle gaps, daily/weekly load limits, spread across days, linking/same-room**. Class placement is **capacity, together/apart, and balance across classes**. All three map onto ~10 constraint shapes.

### Cited Findings
- Rostering (INRC-II): one shift per day; min coverage per shift/skill; forbidden successions; skill match; optimal coverage; min/max consecutive per shift type and globally; min/max consecutive days off; preferences; complete weekends; total assignments min/max; max working weekends. — [INRC-II](https://ar5iv.labs.arxiv.org/html/1501.04177)
- Rostering (OR-Tools): consecutive-run bands, weekly sum bands, penalized/forbidden transitions, per-employee requests, cover demand with excess penalty. — [OR-Tools shift_scheduling_sat.py](https://raw.githubusercontent.com/google/or-tools/stable/examples/python/shift_scheduling_sat.py)
- Rostering (Timefold commercial): contracts, work limits, time off, rotations/patterns, shift type diversity, fairness, pairing, skills, priority/optional shifts, cost. — [Timefold ESS constraints](https://docs.timefold.ai/employee-shift-scheduling/latest/user-guide/constraints)
- School (XHSTT): clashes, unavailable times, idle times, busy days, busy times per day, workload, split/distribute lesson durations, spread events across the cycle, link events, prefer times/resources, same resource across a course. — [Post et al. 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)
- School (Timefold quickstart): room/teacher/student-group conflict (hard); teacher room stability, teacher time efficiency (consecutive lessons), subject variety (soft). — [Timefold docs](https://docs.timefold.ai/timefold-solver/1.x/quickstart/shared/school-timetabling/school-timetabling-constraints)
- School (FET): min days between activities, max hours daily, not-available times, preferred rooms, max gaps (time vs space constraint split). — [FET FAQ](https://lalescu.ro/liviu/fet/doc/en/faq.html)
- University (ITC2019): same/different time/day/week/room, overlap/not-overlap, precedence, min gap, max days, max day load, max breaks, max block, same attendees, student conflicts. — [DTU MIP paper](https://backend.orbit.dtu.dk/ws/files/221992887/A_MIP_Formulation_of_the_International_Timetabling_Competition_2019_Problem.pdf)
- Packing-type globals (bin_packing_capa, global_cardinality) match class placement's capacity and per-class counts. — [MiniZinc globals](https://docs.minizinc.dev/en/stable/lib-globals.html)

### Inferences — minimal general constraint catalog (each: selector + params + hard|soft + weight/band)
1. **Assign / coverage (cardinality)**: count of resources assigned to demand within [min, max] (with optimal/target). Covers INRC H2/S1, cover demands, XHSTT Assign Resource/Time, class capacity. CP-SAT: linear sum with band.
2. **At most one at a time (no-overlap)** per resource (or per day). Covers H1, XHSTT Avoid Clashes, teacher/room/class conflict. CP-SAT: sum <= 1 per (resource, slot) or AddNoOverlap on intervals.
3. **Eligibility / availability (domain)**: skills, unavailable times, prefer times, prefer resources/room groups, fixed preassignments. Hard version = domain pruning (do not create the variable); soft version = linear penalty.
4. **Count bands over a window**: per resource, per slot group (day, week, horizon, weekend). Covers total assignments, max lessons per day (Limit Busy Times), workload, max working weekends, days worked (Cluster Busy Times), weekly sums. CP-SAT: sum with 7-tuple band.
5. **Sequence / run length**: min/max consecutive working days, consecutive same shift, consecutive days off, max block of lessons. CP-SAT: soft sequence helper or AddAutomaton.
6. **Transitions / rest**: forbidden or penalized (shift_a on day d, shift_b on day d+1), min rest hours. CP-SAT: pairwise implications or automaton.
7. **Gaps / compactness**: idle times between busy slots in a day (teachers/classes), complete weekends. CP-SAT: reified "busy before and after but not now".
8. **Spread / distribution**: lessons of a course on distinct days, min days between, max per day. CP-SAT: count per day <= 1 / band.
9. **Relational (link/same/different/together/apart/precedence)**: same time, same room, same teacher for a course, students together/apart, order. CP-SAT: equality/inequality of assignment literals.
10. **Balance / fairness**: deviation from mean or max-min spread of counts or attribute sums across resources (shifts per employee) or across groups (gender/level per class). CP-SAT: AddMaxEquality/AddMinEquality on sums, or absolute deviations.
11. **Preference / request**: weighted wish (+/-) for a specific (resource, demand/slot). CP-SAT: linear objective term.
- Hard/soft is not a property of the type but of the instance (XHSTT and FET both do this), so the catalog should carry `mode` on each constraint instance.

### Gaps
- No primary source fetched for class placement (student sectioning into homerooms) beyond ITC2019 sectioning; balance-across-classes constraints are inferred from domain knowledge, not cited.

## What do standard interchange formats look like, and could one be the internal spec?

### Takeaway
XHSTT is the most general declarative format (user-defined resource types, events with open roles, 15-16 typed constraints, per-constraint hard/soft + weight), but it is XML-heavy, timetabling-centric, and was criticized as complex; INRC-II and the Curtois format are rostering-specific; Timefold JSON is solver-specific and code-coupled. Better to adopt XHSTT's concepts (times/time groups, typed resources/groups, events with roles, typed constraints with selector + hard flag + weight) in a JSON schema of your own, with importers for XHSTT/INRC-II as validation corpora.

### Cited Findings
- XHSTT is an XML archive containing instances and solution groups; solutions are lists of sub-events with duration, time and resource assignments; HSEval evaluates them online. — [Post et al. 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)
- Organizers cite format complexity as a likely reason for low participation. — [Post et al. 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)
- 35 XHSTT instances from 10 countries were available at competition time; datasets are hosted at UTwente. — [Post et al. 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf); [UTwente HSTT datasets](https://www.utwente.nl/en/eemcs/dmmp/hstt/datasets/Greece/HighSchool1)
- INRC-II splits data into scenario / week / history files; constraints are fixed (H1-H4, S1-S7) with fixed weights, parameterized only through contracts and shift types. — [INRC-II](https://ar5iv.labs.arxiv.org/html/1501.04177)
- Timefold's service JSON accepts per-dataset weight overrides under `config.model.overrides`. — [Timefold ESS constraints](https://docs.timefold.ai/employee-shift-scheduling/latest/user-guide/constraints)
- ITC2019 uses an XML format with compact bit-string time patterns. — [DTU MIP paper](https://backend.orbit.dtu.dk/ws/files/221992887/A_MIP_Formulation_of_the_International_Timetabling_Competition_2019_Problem.pdf)

### Inferences
- Recommended internal spec: JSON with `slots`, `slot_groups`, `resource_types`, `resources`, `resource_groups`, `demands/events` (with roles), `rule_bundles` (contracts), and `constraints[]` where each entry = `{type from catalog, applies_to selector, params, mode: hard|soft, weight or band costs, priority}`. This maps 1:1 to XHSTT concepts and to INRC-II (contracts -> rule bundles), so importers are straightforward and public benchmarks can be used for regression tests.
- A closed constraint vocabulary is what makes the spec safe for an LLM to edit and for a manager to read back ("max 5 consecutive days, soft, weight 30"), unlike Timefold-style code streams.

### Gaps
- Timefold's exact JSON input schema for its employee-scheduling service was not retrieved.
- schedulingbenchmarks.org's text/XML format sections were not retrieved.

## How are hard vs soft constraints, weights and lexicographic priorities expressed?

### Takeaway
Three patterns: (1) **per-constraint hard flag + integer weight with lexicographic hard-then-soft comparison** (XHSTT, INRC-II); (2) **multi-level scores** (Timefold hard/medium/soft, with medium used for "unassigned required work"); (3) **bands with hard and soft limits in one constraint** (OR-Tools 7-tuple). FET uses a percentage where 100% = hard. In CP-SAT, levels are implemented either by big-M weighting into one objective or by sequential solves fixing earlier levels.

### Cited Findings
- XHSTT: each constraint has a Boolean hard/soft flag and integer weight; better = smaller infeasibility, then smaller objective. — [Post et al. 2013](https://www2.cs.sfu.ca/~mitchell/cmpt-827/2015-Fall/Projects/TT-ITC-2011-Report.pdf)
- XHSTT: no constraint type is predefined hard or soft. — [arXiv 2407.16898 (search summary)](https://arxiv.org/pdf/2407.16898)
- INRC-II: H1-H4 hard; S1-S7 soft with fixed weights 10-30. — [INRC-II](https://ar5iv.labs.arxiv.org/html/1501.04177)
- Timefold: HardMediumSoft; medium = maximize assigned mandatory shifts; weight x match score; weight cap 1e12; weight 0 disables. — [Timefold ESS constraints](https://docs.timefold.ai/employee-shift-scheduling/latest/user-guide/constraints)
- OR-Tools example: hard bounds plus soft bounds with linear costs in one tuple; all soft costs summed into one minimized objective. — [OR-Tools shift_scheduling_sat.py](https://raw.githubusercontent.com/google/or-tools/stable/examples/python/shift_scheduling_sat.py)
- FET: weight percentage 0-100; 100% = must hold. — [FET FAQ](https://lalescu.ro/liviu/fet/doc/en/faq.html)
- ITC2019: weighted sum of time, room, distribution and student-conflict penalties; distribution constraints are either required or have a penalty. — [DTU MIP paper](https://backend.orbit.dtu.dk/ws/files/221992887/A_MIP_Formulation_of_the_International_Timetabling_Competition_2019_Problem.pdf)

### Inferences
- For the engine: give each constraint instance `mode` (hard|soft), `weight` (int), and optional `level` (int, for lexicographic tiers such as "coverage gaps" > "fairness" > "preferences"). Implement a Timefold-like **medium tier** for "required demand left unfilled" so the solver always returns a schedule (with explicit holes) instead of INFEASIBLE, which is important for a chat UX.
- Hard constraints that would make the model infeasible should be optionally relaxable into a very-high-tier soft version to produce explanations ("which hard rules conflict").
- Use the band form (`hard_min, soft_min, soft_max, hard_max, cost_below, cost_above`) for every count/sequence constraint, so "hard" and "soft" are just parameter choices, not different constraint types.
- Quadratic/step cost functions (XHSTT reportedly supports Linear/Quadratic/Step; not confirmed here) can be approximated in CP-SAT with AddMultiplicationEquality or piecewise tables for fairness.

### Gaps
- Could not confirm XHSTT's CostFunction semantics (Linear/Quadratic/Step) from the HSEval spec.
- No benchmark data was found comparing big-M weighting vs sequential lexicographic solving in CP-SAT for these problem classes.
