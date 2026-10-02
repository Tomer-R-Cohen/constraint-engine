# Architecture patterns for reliable LLM + constraint-solver products for non-expert users

Context: product where a non-technical user uploads spreadsheets and chats rules; an LLM agent builds the model through tool calls into a fixed constraint catalog; OR-Tools CP-SAT solves; assumption literals explain infeasibility; rounds of 3 diverse options. Research date: 2026-10-02.

## Q1. Fixed constraint catalog / DSL via tool calls vs free-form solver code generation vs hybrid

### Takeaway
Free-form LLM model generation is still unreliable even on textbook problems (best ~65-71% correct on CP-Bench, with "silently wrong" models rising as prompts get richer), while systems that route the LLM through predefined, validated functions reach roughly 85-95% on the tasks those functions cover. The evidence favours a hybrid: a typed catalog for the common case, plus a narrow, validated and sandboxed escape hatch whose output a human must review.

### Cited Findings
- CP-Bench (101 problems from CP repositories, up to 2,017 constraints) compares LLMs writing MiniZinc, CPMpy and raw OR-Tools CP-SAT Python. Best results are about 65% for CPMpy, about 50% for OR-Tools and at most 50% for MiniZinc. GPT-4.1-mini gets 63%, rising to 71% with repeated sampling (k=10, solution majority vote) plus self-verification. — [CP-Bench, arXiv 2506.06052](https://arxiv.org/html/2506.06052v2)
- CP-Bench: detailed API documentation helps the high-level frameworks but shows diminishing returns for the low-level OR-Tools API. Retrieval of similar examples (RAG few-shot) *lowered* accuracy. As documentation grew, runtime errors fell but "modeling errors" (models that run but are logically wrong or unsatisfiable) rose, so syntactic success hides semantic failure. Authors: "expert validation remains essential." — [CP-Bench](https://arxiv.org/html/2506.06052v2)
- OptiChat (INFORMS J. Data Science) uses a hybrid of predefined functions (diagnose/IIS, retrieval, sensitivity, what-if) plus controlled code generation only for "why-not" queries. Overall accuracy is 84.3% on 172 Q&A pairs over 24 models: diagnosing 89.7%, retrieval 94.9%, sensitivity 94.4%, what-if 84.6%, why-not (code generation) 62.2%, rising to 78.4% with o3. In the ablation, **removing the predefined functions dropped diagnosing and sensitivity accuracy to 0%**. Failure modes for GPT-4.1 were syntax errors 46.8%, classification (wrong tool) 31.3% and logic 21.9%. — [OptiChat, arXiv 2501.08406](https://arxiv.org/html/2501.08406v2)
- MCP-Solver exposes item-based editing tools (clear_model, add_item, replace_item, delete_item, get_model, solve_model). Every edit is validated before it is applied (MiniZinc parse and type check; for Python modes, AST analysis that flags unsafe operations). Its stated limits: one backend per session to avoid burdening the LLM, synchronous solving, security isolation that restricts functionality, and a reviewer that checks feasibility but not correctness. Evaluation was only three showcase problems. — [MCP-Solver, arXiv 2501.00539](https://arxiv.org/html/2501.00539v2)
- OptiMUS (LLM agent for MILP) processes each constraint independently through a "connection graph" to cope with long descriptions and large data. It also names hallucinated constraints and hallucinated API calls as core failure modes. — [OptiMUS](https://ar5iv.labs.arxiv.org/html/2402.10172); [arXiv 2407.19633](https://arxiv.org/html/2407.19633v3)
- Gurobi's "Modeler" agent (Gurobi Intelligence Hub) builds a structured business specification (Overview, Objective, Constraints, Input data, Output format, Test scenarios, Out-of-scope), asking "clarifying questions one at a time". It then generates gurobipy code plus a pytest suite with one test per specified scenario, iterates until the tests pass, and "stops and asks you to weigh in" when spec, code and tests disagree. — [Gurobi Modeler docs](https://docs.gurobi.com/projects/intelligence/en/current/modeler.html). Gurobi AI Modeling (custom GPTs) launched Feb 2025. — [Gurobi newsroom](https://www.gurobi.com/company/newsroom/gurobi-ai-modeling-empowers-users-with-accessible-optimization-resources)
- Minimal-core-guided repair (Aug 2026, workshop poster): when LLM-generated solver code runs but is UNSAT or wrong, the repair loop gets a minimal unsat core over the model's own constraints. Compared with bare error messages, this cut "fabrication" in weaker models from 79% to 7%. — [Sarkar, arXiv 2608.14771](https://arxiv.org/abs/2608.14771)
- Security of running generated code: generated code can exfiltrate environment variables, open reverse shells or delete mounted volumes, through hallucination or prompt injection. Plain containers are considered insufficient for untrusted code; production systems use gVisor (Modal) or Firecracker microVMs (E2B, Vercel). Firecracker claims under 125 ms cold boot and under 5 MiB overhead. — [Modal](https://modal.com/resources/best-sandboxed-environments-ai-code-generation); [tianpan.co](https://tianpan.co/blog/2026-03-09-agent-sandboxing-secure-code-execution) (vendor and blog sources; figures are vendor claims)

### Inferences
- Shibutzit's catalog-via-tool-calls design matches the pattern with the strongest evidence (OptiChat's ablation). Each catalog entry acts as a "predefined function" whose semantics, paraphrase and explanation text are owned by code, not by the LLM.
- The escape hatch should be an expression mini-DSL over catalog primitives (for example linear sums or counts over typed entity sets, validated by a parser and AST whitelist like MCP-Solver's), not arbitrary Python. Run it in a sandbox only if arbitrary code is unavoidable. Treat its output as "unverified" until the user confirms it with a paraphrase and a test.
- Test-time scaling (sample N candidate tool-call sequences and majority-vote on the resulting solutions) is a cheap reliability lever that the evidence supports for model construction.
- Tool-selection (classification) errors are a third of failures in OptiChat, so a small, well-named catalog with mutually exclusive descriptions matters as much as catalog coverage.

### Gaps
- No published head-to-head production study of "catalog vs codegen" on rostering specifically; evidence is from benchmarks of textbook problems and OptiChat's LP/MILP models.
- No quantitative coverage numbers found for how many real-world user rules a fixed catalog covers (the share that needs an escape hatch).

## Q2. Spreadsheet ingestion and schema inference

### Takeaway
LLM table understanding is good but fragile on long tables and shuffled rows or columns, so let the LLM *propose* the mapping, let deterministic code do the parsing and validation, and have the user confirm. Gurobi Modeler's structured "Input data" spec section is a concrete template.

### Cited Findings
- MMTU (about 28k questions over 25 table tasks, including schema matching, entity matching, data cleaning and column transforms): reasoning models beat chat models by more than 10 points, but "performance drops sharply on long tables and under shuffled rows or columns." — [MMTU, arXiv 2506.05587](https://arxiv.org/html/2506.05587v3); [UMich summary](https://cse.engin.umich.edu/stories/turning-the-tables-a-benchmark-for-llms-in-data-analysis)
- Magneto (PVLDB 2025) combines small LMs for candidate retrieval with LLMs for reranking in schema matching, a cost and accuracy split. — [Magneto](https://alphaxiv.org/abs/2412.08194)
- OptiMUS handles large data files by not putting the data in the prompt; the model references parameters symbolically. — [OptiMUS](https://ar5iv.labs.arxiv.org/html/2402.10172)
- OptiGuide's design principle: answer what-if questions "without sending proprietary data over to LLMs". The LLM writes the query or modification and the solver runs on the data locally. — [OptiGuide, arXiv 2307.03875](https://arxiv.org/abs/2307.03875)
- Gurobi Modeler makes "Input data" an explicit specification section the user co-develops before implementation. — [Gurobi Modeler](https://docs.gurobi.com/projects/intelligence/en/current/modeler.html)

### Inferences
- Recommended pipeline:
  1. Deterministic parsing (sheet and header detection, type sniffing).
  2. Send the LLM only headers plus a small sample and column statistics, not whole tables (privacy, and MMTU's fragility on long tables).
  3. The LLM proposes an entity, attribute and relation mapping (for example "sheet Teachers, column X = subject qualification").
  4. Deterministic validators check referential integrity across sheets, duplicates, unmapped values and type errors.
  5. A confirmation card shows the inferred entities with counts ("I found 42 teachers, 18 classes, 7 subjects; 3 teacher names in the Classes sheet don't match").
- Store the confirmed mapping as a versioned artifact so re-uploads of next term's file reuse it (the template-per-domain idea).

### Gaps
- No HCI study found specifically on confirmation UX for LLM-inferred spreadsheet schemas in optimization tools.

## Q3. Verifying that the model matches user intent

### Takeaway
Converging practice: (1) back-translate every formal constraint into plain language for confirmation, (2) separate hard rules from soft preferences explicitly, (3) keep executable test scenarios derived from the spec, and (4) let users interrogate solutions ("why is X here", "why not Y") with answers computed by re-solving, not by LLM narration.

### Cited Findings
- U-Define (2026): users classify constraints as hard or soft. Hard rules are checked by formal model checking; soft ones by LLM-as-judge. Typed constraints "improve perceived usefulness, performance, and satisfaction". Hard-only proved overly restrictive, and **numeric flexibility weights confused users**. Designers should show the mapping from user phrases to formal predicates and back-translate finalized properties into plain language for confirmation. — [U-Define, arXiv 2605.02765](https://arxiv.org/abs/2605.02765); back-translation recommendation per [search summary of the PDF](https://arxiv.org/pdf/2605.02765)
- VeriPlan: user constraints are translated into LTL/PRISM templates, model-checked, and presented back in natural language for user verification. — [VeriPlan, arXiv 2502.17898](https://arxiv.org/pdf/2502.17898)
- Gurobi Modeler: test scenarios are part of the spec, one pytest per scenario; it asks "which side is correct" when spec and code diverge. — [Gurobi Modeler](https://docs.gurobi.com/projects/intelligence/en/current/modeler.html)
- LLM-assisted active constraint acquisition (LlmAcq, JAIR) asks users targeted queries and interprets natural-language answers, which "dramatically decreases the number of queries". — [JAIR 19277](https://jair.org/index.php/jair/article/view/19277); [IJCAI 2024](https://ijcai.org/proceedings/2024/212)
- Timefold score analysis returns a per-constraint breakdown and, with ConstraintJustification, the specific entities behind each match. Stated uses include "understanding why… specific scheduling decisions", "explaining why a particular assignment wasn't made" and "validating manual changes". — [Timefold docs](https://docs.timefold.ai/timefold-solver/latest/constraints-and-score/understanding-the-score); [score analysis](https://docs.timefold.ai/job-scheduling/latest/user-guide/score-analysis); [Timefold 1.4 blog](https://timefold.ai/blog/timefold-solver-1-4-brings-explainable-score)
- OptiChat answers why-not questions by adding a constraint that forces the alternative and re-solving (counterfactual), and what-if questions by re-solving modified models. — [OptiChat](https://arxiv.org/html/2501.08406v2)
- OptiMUS and related work: a model may be syntactically correct and produce a number while violating the problem's logic, so solutions must be checked for logical feasibility. — [arXiv 2407.19633](https://arxiv.org/html/2407.19633v3)

### Inferences
- Each catalog constraint type should carry a code-owned paraphrase template ("Teacher {t} teaches at most {n} hours on {day}"). The LLM chooses parameters, and the UI shows the rendered template, not LLM prose. This is deterministic back-translation.
- An independent checker in plain Python that evaluates each constraint on the final assignment (Timefold-style per-constraint "matches") gives solver-independent verification and the raw material for "why" answers.
- Test scenarios: when a user states a rule, ask for or generate one concrete example ("so Dana can't be in two classes at 9:00, right?") and keep it as a regression check on the spec.
- Avoid exposing raw weights. Use ordinal priority levels, given U-Define's finding that numeric weights confuse users.

### Gaps
- No quantitative study found measuring how often back-translation catches mis-modelled constraints in practice.

## Q4. Infeasibility and explanation (MUS/MCS/IIS, CP-SAT assumptions, QuickXplain, step-wise explanations)

### Takeaway
The standard toolkit is mature. Use assumption literals plus CP-SAT's core as a seed, shrink it to a MUS (or a preferred MUS with QuickXplain, or the cheapest with optimal or OCUS), compute MCS/MSS for "what to relax", and present corrections in the user's own rule vocabulary. Users prefer "what can I keep and what must change" over a bare conflict set.

### Cited Findings
- CP-SAT assumptions: `model.add_assumptions([...])` and `clear_assumptions()`. On infeasibility, `sufficient_assumptions_for_infeasibility()` returns the conflicting assumptions; the primer calls it minimal but makes no uniqueness guarantee. Caveat: CP-SAT does not reuse learned clauses across runs with different assumptions, because each solve starts fresh. — [CP-SAT Primer, parameters](https://d-krupke.github.io/cpsat-primer/parameters.html)
  - Note (conflict): the OR-Tools API name says "sufficient", and in practice cores from CP-SAT are not guaranteed minimal. That is why CPMpy's `mus()` runs a deletion-based shrink on top of solver cores. Treat the CP-SAT core as a starting point and shrink it. — [CPMpy explain tools](https://cpmpy.readthedocs.io/en/latest/api/tools/explain.html)
- CPMpy `tools.explain` provides:
  - `mus` (deletion-based using assumptions)
  - `quickxplain` (preferred MUS that respects a constraint ordering)
  - `optimal_mus` and `smus` (cheapest or smallest MUS)
  - `ocus` (optimal constrained MUS via hitting sets)
  - `mss`, `mss_opt` (maximal satisfiable subset, weighted)
  - `mcs`, `mcs_opt` (minimal correction subset, weighted)
  - `marco` (enumerate all MUSes and MCSes)
  - `make_assump_model` (turns soft constraints into assumptions)

  Most of these need solvers that support assumptions (ortools, exact, z3, pysat). — [CPMpy explain docs](https://cpmpy.readthedocs.io/en/latest/api/tools/explain.html); [CPMpy unsat core docs](https://cpmpy.readthedocs.io/en/latest/unsat_core_extraction.html)
- Gamba, Bogaerts and Guns: step-wise explanations, where each step is a MUS-derived inference chosen to minimise a cost or interpretability function. Related: OUS/OCUS for efficiently finding optimal explanation steps; using certifying solvers to generate steps; and preference elicitation to learn which explanation steps users find simplest. — [Framework, arXiv 2006.06343](https://arxiv.org/pdf/2006.06343); [OUS, arXiv 2105.11763](https://arxiv.org/pdf/2105.11763) and [extended version 2303.11712](https://arxiv.org/pdf/2303.11712); [Certifying solvers, arXiv 2511.10428](https://arxiv.org/pdf/2511.10428); [Preference elicitation for step-wise explanations, arXiv 2511.10436](https://arxiv.org/pdf/2511.10436)
- Survey (Gupta, Genc, O'Sullivan, IJCAI 2021): most explanation approaches rest on minimal conflicts, but "a minimal conflict does not necessarily give an intuitive explanation… many users want to be shown which subsets of their constraints they can satisfy and which they cannot". Counterfactual explanations, computed via conflict detection plus maximal relaxations, tell users what to *change* rather than what to remove. — [IJCAI 2021 survey](https://www.ijcai.org/proceedings/2021/601); [UCC repository](https://cora.ucc.ie/bitstreams/adb69714-1672-4658-9b77-f0a739ead622/download)
- OptiChat diagnoses infeasibility via the IIS and then proposes *minimal parameter adjustments* to restore feasibility (89.7% accuracy on diagnosing queries). — [OptiChat](https://arxiv.org/html/2501.08406v2)
- In an older empirical study of interactive problem solving, users called explanation services more often after solver failures, and were "skeptical toward artificial solver performance" and preferred to keep control, with expertise and task difficulty interacting. — [CNR, Key Issues in Interactive Problem Solving](https://iris.cnr.it/handle/20.500.14243/29149)

### Inferences
- Concrete recipe for Shibutzit:
  1. Attach one assumption literal per *user-level rule instance group* (for example "Rule 3: max 6 hours/day", not per-variable), so a core maps directly to sentences the user wrote.
  2. Shrink the CP-SAT core with deletion or QuickXplain, ordered by "most recently added or least trusted rule first", so the explanation blames new rules preferentially.
  3. Compute 1-3 weighted MCSs, with costs set by rule priority, and present them as "keep everything except…" choices. This fits the existing rounds-of-3 options UX.
  4. Include data-level relaxations (for example "add 2 hours to teacher X's availability") as OptiChat does, not only rule removal.
- Under the "rules owned by manager" principle (see project memory), MCS results should be presented as explanations of the conflict and its consequences, not as recommendations to change the rules.
- Step-wise explanation (Gamba et al.) suits "why is X forced here" questions about a *feasible* solution: the chain of MUS steps from the facts to the forced assignment.

### Gaps
- No user study found that compares MUS vs MCS vs counterfactual presentations with non-expert schedulers specifically.
- Did not verify current OR-Tools release notes on whether `SufficientAssumptionsForInfeasibility` is guaranteed minimal; treat it as non-minimal.

## Q5. Solution diversity and interactive re-optimisation

### Takeaway
Use Hamming-distance-based diversity to generate alternatives, and minimal-perturbation (penalise change from the published plan, or pin locked parts) for re-solves. Both are standard. Timefold's productised versions are pinning, a disruption penalty and a "Recommended Fit" API.

### Cited Findings
- To generate k maximally diverse solutions, CP uses Hamming-distance constraints or objectives between solutions; the same machinery yields "similar" solutions (minimal change). — [Similar/Diverse solutions in ASP, arXiv 1108.3260](https://arxiv.org/pdf/1108.3260); [Constraints journal, 10.1007/s10601-011-9108-5](https://unpaywall.org/10.1007%2FS10601-011-9108-5)
- Minimal perturbation problem: interleave optimisation and satisfaction to find a new solution closest to the old one after a change (applied to meeting scheduling). — [search result summary; same Constraints-journal line of work](https://unpaywall.org/10.1007%2FS10601-011-9108-5)
- Timefold non-disruptive replanning: store the original and current values and add a soft constraint penalising each changed assignment (for example -1000 per change), so "the gain of changing an assignment must outweigh the disruption cost". Pinning (`@PlanningPin`) hard-locks confirmed assignments. — [Timefold docs](https://docs.timefold.ai/timefold-solver/latest/responding-to-change/non-disruptive-replanning); [manual intervention](https://docs.timefold.ai/employee-shift-scheduling/1.28.x/manual-intervention)
- Timefold's Recommended Fit API returns a sorted list of feasible placements for a new or changed item. — [Timefold real-time planning](https://docs.timefold.ai/timefold-platform/latest/guides/responding-to-disruptions-with-real-time-replanning)
- CP-SAT warm start: `add_hint` speeds re-solves. `fix_variables_to_their_hinted_value` validates a hint. Hints can be lost in presolve (workaround: `keep_all_feasible_solutions_in_presolve`), and even feasible but bad hints can mislead the search. — [CP-SAT Primer](https://d-krupke.github.io/cpsat-primer/parameters.html)
- Users are more likely to understand solutions they helped create; interactive editing tools helped employees produce better schedules faster. — [MERL TR2001-39](https://www.merl.com/publications/docs/TR2001-39.pdf) (older HCI source; summary from search snippet)

### Inferences
- For "rounds of 3", pick options as: best objective; then the best solution subject to Hamming distance ≥ d from option 1 (or maximising distance with an objective tolerance, for example within 3% of the best); then likewise from options 1 and 2. Explain each option's distinguishing trade-off via the per-constraint score breakdown.
- For "refine option B", use hints from B plus a change-penalty term (Timefold style), and pin anything the user explicitly locked.
- Preference elicitation: record which option is chosen and why (reason chips), and translate that into priority ordering. Avoid raw weights (U-Define).

### Gaps
- No vendor documentation found on CP-SAT-specific diverse-solution recipes beyond general Hamming-distance techniques; the Krupke primer page did not cover it.

## Q6. Agent tooling patterns (MCP, tool schemas, guarding against hallucinated numbers, evaluation)

### Takeaway
The solver (and a deterministic checker) must be the only source of any number or claim about the schedule. The LLM chooses tools and phrases results. Validate every tool call, keep models editable item by item, and regression-test the agent with scenario suites, as Nextmv and Gurobi do for models.

### Cited Findings
- OptiGuide: the solver produces the outputs and the LLM only translates them into language; what-if queries work by the LLM modifying solver input. — [OptiGuide](https://arxiv.org/abs/2307.03875); [summary in arXiv 2407.19633](https://arxiv.org/html/2407.19633v3)
- OptiChat: function calls "minimize the risk of hallucinations". A "Reminder" agent supplies syntax and component identification, and an "Illustrator" preprocessing step improved follow-up accuracy. — [OptiChat](https://arxiv.org/html/2501.08406v2)
- MCP-Solver shows MCP as a transport for solver tools, with validation on each edit. — [MCP-Solver](https://arxiv.org/html/2501.00539v2)
- OptArgus and Opt-Verifier: multi-agent hallucination detection that audits structural consistency between the problem description, the symbolic model and the solver code, plus dual-side verification. — [Opt-Verifier, arXiv 2605.29556](https://arxiv.org/pdf/2605.29556); [search summary](https://arxiv.org/abs/2505.11792v1)
- Nextmv's DecisionOps testing covers batch, scenario and acceptance tests (business-KPI comparison between model versions) and shadow and switchback tests online, with versioned models and managed input sets. — [Nextmv test](https://nextmv.io/test); [acceptance testing blog](https://webflow.nextmv.io/blog/introducing-acceptance-testing-its-like-ci-cd-for-your-decision-algorithm)
- CP-Bench: majority voting over solutions from 10 sampled models gives about +10 points, so solution-level agreement is a usable correctness signal. — [CP-Bench](https://arxiv.org/html/2506.06052v2)

### Inferences
- Guardrails:
  1. Tool results carry structured numbers; the response renderer pulls numbers from tool results (template slots), not from LLM text.
  2. A post-hoc check flags any number in the LLM reply that does not appear in the tool results of that turn.
  3. JSON-schema-strict tool arguments with enums of real entity IDs, so the LLM cannot reference nonexistent teachers.
- Agent eval: a golden set of (spreadsheets, chat transcript) pairs mapped to expected catalog constraints and properties of the solution (feasible/infeasible, specific constraint satisfied). Run it on every prompt or model change (the Nextmv acceptance-test idea applied to the agent).

### Gaps
- No published numbers found on hallucinated-number rates in deployed optimization chatbots.

## Q7. Multi-tenant / generic product concerns (templates, spec versioning, reproducibility, CP-SAT scale)

### Takeaway
Treat the problem spec (data mapping + constraint instances + priorities) as a versioned, diffable document, run versions through scenario and acceptance tests, and set user-facing time budgets (about 60-120 s). CP-SAT handles realistic rostering sizes (about 180k variables) but needs time limits and gap limits for interactive use.

### Cited Findings
- A CP-SAT study of healthcare workforce scheduling reached feasible schedules on instances up to 179,800 variables and 351,425 constraints (80 nurses), with proven optimality on some benchmarks. — [arXiv 2608.30419 via opentrain summary](https://www.opentrain.ai/papers/from-metaheuristics-to-exact-methods-a-cp-sat-approach-for-multi-objective-healt--arxiv-2608.30419/) (secondary aggregator; primary not fetched)
- A nurse rostering comparison found CP-SAT more consistent than Tabu Search and a GA-SA hybrid at medium and large scale; a 90-120 s time limit was the best quality/wait trade-off. — [Undip eprint 46608](https://eprints2.undip.ac.id/id/eprint/46608/)
- CP-SAT parameters: `max_time_in_seconds` (60-300 s suggested in development), `relative_gap_limit` (for example 0.05) for early stopping, and `num_workers` (portfolio; fewer workers can sometimes be faster). Callbacks slow the solver. — [CP-SAT Primer](https://d-krupke.github.io/cpsat-primer/parameters.html)
- Nextmv: version control, input sets and acceptance tests treat models like software. — [Nextmv](https://nextmv.io/test)
- Gurobi Modeler's fixed spec structure (Overview / Objective / Constraints / Input data / Output / Test scenarios / Out-of-scope) is a natural template schema. — [Gurobi Modeler](https://docs.gurobi.com/projects/intelligence/en/current/modeler.html)

### Inferences
- Reproducibility: persist the spec version, data hash, solver version, parameters and seed with each result. Note that multi-worker CP-SAT runs under a time limit are not deterministic, so for reproducibility store the solution itself, and use `num_workers=1` with a fixed seed (or a deterministic time) when exact replay matters.
- Domain templates: a template = catalog subset + entity schema + default priorities + example scenarios. New domains add catalog entries in code, not via LLM codegen.

### Gaps
- Primary source of arXiv 2608.30419 not fetched.
- No authoritative source located on CP-SAT determinism guarantees (`interleave_search`, deterministic time); the primer page did not cover them.
- No HCI study found on non-experts' tolerance for solver wait time beyond the 90-120 s rostering finding.
- The argumentation-based workforce explanation paper ([arXiv 2508.15118](https://arxiv.org/pdf/2508.15118)) reports improved user understanding with argumentative explanations and interactive edits, but the fetched summary lacked concrete numbers. Treat it as directional only.
