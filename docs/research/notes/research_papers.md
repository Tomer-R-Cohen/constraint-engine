# Academic research: LLMs translating natural language into optimization / constraint models (state as of Oct 2026)

Note on verification: findings marked [verified] were read from the paper or abstract page during this session (2 Oct 2026). Items marked [prior knowledge] come from the researcher's background knowledge of well-known papers; the links are believed correct, but the numbers were NOT re-fetched in this session and should be spot-checked before quoting. "PR" = peer-reviewed; "preprint" = arXiv only, as far as could be determined.

## Q1. Key papers and systems (timeline)

### Takeaway
The field moved in three waves. (1) 2022-23: NL4Opt-style LP word problems and prompting pipelines. (2) 2024-25: agentic systems (OptiMUS, Chain-of-Experts), fine-tuned "OR LLMs" (ORLM, LLMOPT, SIRL, OptiMind), and CP-specific work (CP-Bench, Text2Zinc, ConstraintLLM). (3) 2026: verification and hallucination detection (CP-SynC, OptArgus, Opt-Verifier, OptiRepair), intermediate representations (CIR/R2C), and scheduling-specific benchmarks (SCHEDBench).

### Cited Findings
**Foundations / LP-MILP line**
- NL4Opt competition (NeurIPS 2022 competition track): two subtasks, entity recognition and generating a logical form for LP word problems. This is the origin of most later MILP benchmarks [prior knowledge]. — [arXiv 2303.08233](https://arxiv.org/abs/2303.08233)
- "Holy Grail 2.0: From Natural Language to Constraint Models" (Tsouros, Verhaeghe, Kadıoğlu, Guns; arXiv Aug 2023, position paper). Took inspiration from NL4Opt, gave early results from decomposition-based prompting of GPT models, and set out a blueprint for conversational modelling assistants. — [arXiv 2308.01589](https://arxiv.org/pdf/2308.01589) [verified via search snippet]
- OptiGuide (Microsoft, 2023): uses an LLM to answer what-if questions about an existing supply-chain optimization model by writing code that changes the model. The LLM does not write the model itself [prior knowledge]. — [arXiv 2307.03875](https://arxiv.org/abs/2307.03875)
- OptiMUS-0.3 (Stanford; AhmadiTeshnizi, Gao, Udell et al.; arXiv Jul 2024, v3 later): a modular LLM agent that models and solves MILPs from long descriptions, with error correction and a "connection graph" of which constraints use which variables and parameters. It reports gains of more than 22% on easy datasets and more than 24% on hard ones over prior state of the art. It introduced NLP4LP, 355 problems including real-world descriptions an order of magnitude longer than in other MILP modelling datasets. — [arXiv 2407.19633](https://www.arxiv.org/abs/2407.19633) [verified via search snippet]. Earlier OptiMUS v0.1/v0.2 appeared at ICML 2024 [prior knowledge] — [arXiv 2402.10172](https://arxiv.org/abs/2402.10172)
- Chain-of-Experts (ICLR 2024, PR): multi-agent "experts" (modelling, programming, reviewing) coordinated by a conductor. Introduced the ComplexOR dataset [prior knowledge]. — [OpenReview](https://openreview.net/forum?id=HobyL1B9CZ)
- ORLM (fine-tuned open models on the synthetic OR-Instruct data; introduced the IndustryOR benchmark; later published in the journal Operations Research) [prior knowledge]. — [arXiv 2405.17743](https://arxiv.org/abs/2405.17743)
- MAMO benchmark (EasyLP / ComplexLP; checks answers by solving the model) [prior knowledge] — [arXiv 2405.13144](https://arxiv.org/abs/2405.13144). OptiBench / ReSocratic (ICLR 2025) [prior knowledge] — [arXiv 2407.09887](https://arxiv.org/abs/2407.09887). LLMOPT (ICLR 2025; five-element formulation plus multi-instruction fine-tuning and self-correction) [prior knowledge] — [arXiv 2410.13213](https://arxiv.org/abs/2410.13213). OR-LLM-Agent (2025 preprint; agentic modelling, coding and debugging) [prior knowledge] — [arXiv 2503.10009](https://arxiv.org/abs/2503.10009)
- SIRL, "Solver-Informed RL" (2025): uses solver feedback (whether the model is feasible, objective value, execution) as a reinforcement-learning reward to train formulation models. — [arXiv 2505.11792](https://arxiv.org/pdf/2505.11792) [verified exists]
- OptiMind (Microsoft, Sep 2025): "Teaching LLMs to think like optimization experts". Cleans the training and test data and adds expert hints for each class of problem. — [arXiv 2509.22979](https://arxiv.org/pdf/2509.22979) [verified exists]
- Survey "Optimization Modeling Meets LLMs: Progress and Future Directions" (Xiao et al., Aug 2025; listed as IJCAI 2025 survey track). Taxonomy: data synthesis, fine-tuning, inference frameworks, benchmarks, evaluation. The authors also released a cleaned benchmark collection. — [arXiv 2508.10047](https://arxiv.org/pdf/2508.10047) [verified]
- ORThought (Aug 2025): expert-guided reasoning for logistics optimization modelling, with a new logistics benchmark. — [arXiv 2508.14410](https://arxiv.org/html/2508.14410v1)
- ORGEval (Oct 2025): judges model correctness by graph-theoretic comparison (model isomorphism) rather than by matching the objective value. — [arXiv 2510.27610](https://arxiv.org/pdf/2510.27610)

**Constraint programming (CP) line**
- "Constraint Modelling with LLMs Using In-Context Learning" (CP 2024, LIPIcs, PR). — [Dagstuhl](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.CP.2024.20)
- Text2Zinc (Kadıoğlu et al.; AAAI 2025 workshop / arXiv Mar 2025): 1,775 natural-language instances covering both satisfaction and optimization problems, 110 of them manually verified. — [arXiv 2503.10642](https://arxiv.org/pdf/2503.10642)
- CP-Bench, renamed DCP-Bench-Open (Michailidis, Tsouros, Guns, KU Leuven): 101 problems in v1, 164 in the latest version. Compares MiniZinc, CPMpy and OR-Tools CP-SAT. Published in JAIR (PR, per the arXiv v3 page). — [arXiv 2506.06052v3](https://arxiv.org/html/2506.06052v3) [verified]
- CP-Agent (Szeider; arXiv Aug 2025; to appear at AGENT@ICSE 2026 workshop): a general-purpose coding agent with a persistent Python/CPMpy environment that iterates on its model. — [arXiv 2508.07468](https://arxiv.org/html/2508.07468)
- Gala: "Global LLM Agents for Text-to-Model Translation" (Sep 2025): one agent per global-constraint type. — [arXiv 2509.08970](https://arxiv.org/pdf/2509.08970)
- ConstraintLLM (EMNLP 2025 main, PR): a fine-tuned open LLM for CP modelling, with Constraint-Aware Retrieval (CARM), Tree-of-Thoughts and guided self-correction. Introduced IndusCP (140 industrial-level CP tasks) and reports about 2x the baselines on IndusCP. — [ACL Anthology 2025.emnlp-main.809](https://aclanthology.org/2025.emnlp-main.809); [arXiv 2510.05774](https://arxiv.org/pdf/2510.05774); code: https://github.com/william4s/ConstraintLLM
- "Modeling Copilots for Text-to-Model Translation" (Kadıoğlu group, Apr 2026; ships as the PyPI package `text2model`). — [alphaXiv 2604.12955](https://www.alphaxiv.org/abs/2604.12955)
- Workshop venue: "LLMs meet Constraint Solving 2025". — [site](https://sites.google.com/view/llm-solve-2025)

**2026 verification / robustness wave (all preprints)**
- CP-SynC (May 2026): a multi-agent zero-shot MiniZinc modeller in which validation agents write semantic checker programs that test candidate solutions. — [arXiv 2605.01675](https://arxiv.org/pdf/2605.01675)
- OptArgus (May 2026): the first fine-grained hallucination taxonomy for optimization modelling (objective, variable, constraint and implementation hallucinations), with four specialist auditor agents run by a conductor. — [arXiv 2605.11738](https://arxiv.org/pdf/2605.11738)
- Opt-Verifier (May 2026), "dual-side verification" — [arXiv 2605.29556](https://arxiv.org/pdf/2605.29556). Strategy-Aware Optimization Modeling with reasoning LLMs (May 2026) — [arXiv 2605.02545](https://arxiv.org/pdf/2605.02545). EvoOptiGraph (Jun 2026) — [arXiv 2606.26578](https://arxiv.org/pdf/2606.26578). OptiRepair (Feb 2026): closed-loop diagnosis and repair of supply-chain models — [arXiv 2602.19439](https://arxiv.org/pdf/2602.19439). MM-OptBench (May 2026), a multimodal benchmark grounded by a solver — [arXiv 2605.12154](https://arxiv.org/pdf/2605.12154)
- Canonical Intermediate Representation (CIR) plus the Rule-to-Constraint (R2C) framework (Lyu et al., Feb 2026). — [arXiv 2602.02029](https://arxiv.org/abs/2602.02029)
- SCHEDBench (Sharma & Sharma, Aug 2026). — [arXiv 2608.00991](https://arxiv.org/abs/2608.00991)

### Inferences
- The center of gravity has shifted from "can an LLM write a model?" to "how do we know the model is right?" Most 2026 papers are about verification, auditing or repair rather than raw generation.

### Gaps
- No standalone paper titled "CP-LLM" or "NL2Zinc" was found. These names seem to be informal labels for the CP-Bench, Text2Zinc and ConstraintLLM line.
- Exact accuracy numbers for NL4Opt winners, Chain-of-Experts, ORLM, LLMOPT, OR-LLM-Agent and MAMO were not re-fetched in this session.

## Q2. Reported accuracy and how it falls on realistic problems

### Takeaway
Headline numbers of 80-95% on toy LP benchmarks (NL4Opt and similar) drop to about 20-50% on industrial or complex sets (IndustryOR, ComplexOR, IndusCP, R2C's rule-heavy benchmark). Even on clean CP puzzles, single-shot accuracy is about 50-75%. Benchmarks themselves are noisy: 25-54% of test items in some are wrong.

### Cited Findings
- Benchmark label noise: the 2025 survey reports error rates of IndustryOR 54.0%, NL4Opt 26.4%, ComplexLP 23.7% and ComplexOR 24.3%. Overall, "30%-60% test instances" in some benchmarks are incorrect because of missing or ambiguous data, wrong reference answers and rounding. Cleaning took more than a month of expert effort. — [Survey arXiv 2508.10047](https://arxiv.org/pdf/2508.10047) (numbers from the search snippet of this source; the PDF was too large to fully parse)
- On the cleaned benchmarks, methods score roughly 61.2-73.8% on NL4Opt and only 31.2-42.9% on IndustryOR. — [Survey arXiv 2508.10047](https://arxiv.org/pdf/2508.10047) (search snippet)
- The hardest formulation benchmarks (IndustryOR, Mamo Complex, OptMATH) see accuracies of only about 20-50% even for the strongest models. Another summary reports Claude Opus 4 and DeepSeek-V3 tied at 54.82% overall accuracy. — search-result summaries citing [2508.10047](https://arxiv.org/pdf/2508.10047) / [OptiMind 2509.22979](https://arxiv.org/pdf/2509.22979) (the exact attribution of the 54.82% figure could not be pinned to one paper; treat it as approximate)
- CP-Bench / DCP-Bench-Open (JAIR): zero-shot best accuracy is about 57.3% for MiniZinc, about 65-70% for CPMpy and about 68-75% for OR-Tools, with documentation in the system prompt. For CPMpy with gpt-5.1: baseline 70.1%, repeated sampling (k=10) about 80-82%, self-verification about 80-85%, both combined 90.2% (Kimi-K2: 89.0%). Gains reach up to 35 points for MiniZinc. — [arXiv 2506.06052v3](https://arxiv.org/html/2506.06052v3) [verified]
- Overfitting to the given instance: gpt-5.1 scored 78.3% when checked on the single default instance but only 60.9% when the same model was checked on multiple instances, a 17.4-point drop. LLMs "frequently overfit to specific values" instead of writing a general model. — [arXiv 2506.06052v3](https://arxiv.org/html/2506.06052v3) [verified]
- Text2Zinc (MiniZinc): basic prompting gives 19.04% execution accuracy. Chain-of-Thought with data and examples gives 58.73% execution accuracy but only 25.39% solution accuracy. So most models that run still give wrong answers. — [arXiv 2503.10642](https://arxiv.org/pdf/2503.10642)
- CP-SynC raises CP-Bench MiniZinc accuracy: DeepSeek-V3 from 56.7 to 77.7, GPT-4o from 65.3 to 78.0, Gemini-2.5-flash-lite from 48.3 to 67.0. — [arXiv 2605.01675](https://arxiv.org/pdf/2605.01675)
- R2C (CIR) scores 47.2% on its own benchmark of problems with rich operational rules, even though it is the state of the art there. Realistic rule-heavy problems are still below 50%. — [arXiv 2602.02029](https://arxiv.org/abs/2602.02029)
- ConstraintLLM roughly doubles the baselines on IndusCP (140 industrial tasks). This implies baselines score very low on industrial CP. — [arXiv 2510.05774](https://arxiv.org/pdf/2510.05774)
- OptiMUS-0.3 shows bigger relative gains on harder, longer problems (+24%), but absolute accuracy on hard sets stays well below that on easy ones. — [arXiv 2407.19633](https://www.arxiv.org/abs/2407.19633)

### Inferences
- In a real product, expect roughly 1 in 3 to 1 in 2 freely generated models of a realistic rule set to be wrong somewhere unless there are strong guardrails. Many of those errors are silent: the model runs and returns a plausible schedule.
- Reported numbers are not comparable across papers because labels are noisy and the metric is "objective value matches", which can accept wrong models that happen to hit the same optimum (ORGEval's motivation).

### Gaps
- No per-rule accuracy study was found for real customer rule sets (for example, a school's actual timetabling policy).

## Q3. Which output target works best?

### Takeaway
Among free-form targets, high-level Python libraries (CPMpy) and the OR-Tools Python API clearly beat MiniZinc. The strongest reliability results on real business problems come from constrained targets: expert templates or constraint catalogs where the LLM only extracts parameters (SMILO about 90%), or intermediate representations built on rule archetypes (CIR/R2C).

### Cited Findings
- Direct comparison (CP-Bench): Python-based frameworks reach up to about 65-75%; MiniZinc peaks at about 50-57%. The authors attribute this to LLMs seeing far more general Python than specialized modelling languages in training. CPMpy's higher-level abstractions help. — [arXiv 2506.06052](https://arxiv.org/html/2506.06052v3)
- Template / catalog approach on workforce scheduling: SMILO (Li, Zhang, Mak-Hau; arXiv Nov 2025, preprint) works in three stages. It identifies the relevant modelling components, uses the LLM only to extract problem-specific information, and then builds the MILP from expert-defined templates. It "consistently generates correct models in 90% of test instances across five trials", more than 35 percentage points above direct LLM generation. Tested on workforce scheduling in manufacturing, logistics and services. — [arXiv 2511.02364](https://arxiv.org/abs/2511.02364) [verified abstract]
- Intermediate representation: CIR encodes operational rules as "constraint archetypes" plus candidate modelling paradigms. This separates the rule's logic from its mathematical form, and an R2C multi-agent pipeline instantiates the model. It reports state of the art on its rule-heavy benchmark and best-reported results on some public ones. — [arXiv 2602.02029](https://arxiv.org/abs/2602.02029)
- Structured actions instead of code for interactive scheduling: MeetMate (Microsoft Research; ACM TiiS, Sep 2024, PR) turns chat messages into constraint-management actions (add, change priority, delete). A Coder LLM writes each preference as a small Python function, and a CP solver combines a weighted list of these to produce diverse suggestions. — [arXiv 2312.06908](https://arxiv.org/pdf/2312.06908); [Microsoft Research](https://www.microsoft.com/en-us/research/publication/i-want-it-that-way-enabling-interactive-decision-support-using-large-language-models-and-constraint-programming/)
- Retrieval of examples is not a reliable fix on its own: in CP-Bench, retrieval-augmented in-context learning (RAICL) was "ineffective; often degraded performance". — [arXiv 2506.06052v3](https://arxiv.org/html/2506.06052v3). By contrast, ConstraintLLM reports gains from constraint-aware retrieval combined with fine-tuning and Tree-of-Thoughts — [arXiv 2510.05774](https://arxiv.org/pdf/2510.05774)
- Global-constraint-aware decomposition (Gala) assigns one agent per global constraint type, a middle ground between free code and a catalog. — [arXiv 2509.08970](https://arxiv.org/pdf/2509.08970)

### Inferences
- For a product where non-experts state scheduling or assignment rules, the evidence favors: a fixed catalog of rule types (archetypes) with typed parameters, with the LLM classifying and extracting into that catalog and a solver-side compiler that is trusted code. Free-form solver code should be a fallback, if used at all. SMILO's +35 points and the CIR results support this. CP-Bench's Python > MiniZinc result matters only if free code is generated.
- A catalog also makes verification and explanation tractable: each rule maps one-to-one to a constraint the user can see and confirm.

### Gaps
- No head-to-head study was found comparing "fixed catalog" with "free CPMpy code" on the same scheduling rule set. SMILO compares against direct LLM MILP, not against agentic and verified pipelines.
- No source was found that compares Pyomo or AMPL targets directly.

## Q4. Failure modes and mitigations

### Takeaway
The dominant risk is the silent wrong model: it runs and is feasible but encodes the rule differently from what was meant. Syntax and API errors are easy to catch and fix with solver feedback. Semantic errors need semantic checkers, multi-instance testing, independent auditing, or human confirmation.

### Cited Findings
- Error classes: CP-Bench separates "detectable errors" (syntax, invalid API use) from modelling errors. Better prompts reduced detectable errors but sometimes increased logical mistakes. Self-verification cut detectable errors (gpt-5.1: 19 to 5) but had mixed effects on modelling errors. — [arXiv 2506.06052v3](https://arxiv.org/html/2506.06052v3)
- Hard-coding the instance and overfitting to the given numbers: a 17.4-point drop when a model is checked across multiple instances. — [arXiv 2506.06052v3](https://arxiv.org/html/2506.06052v3)
- Hallucination taxonomy for optimization modelling: objective, variable, constraint and implementation failures. Separate specialist auditors beat a single-agent checker, with fewer false alarms on correct models and better detection of natural hallucinations. — [OptArgus arXiv 2605.11738](https://arxiv.org/pdf/2605.11738)
- Semantic checkers: agents write independent solution-checking code (a "checker") and use its feedback to refine the model. This gives +11 to +21 points over the CP-Bench baseline in MiniZinc. — [CP-SynC arXiv 2605.01675](https://arxiv.org/pdf/2605.01675)
- Repeated sampling plus self-verification with solver execution: 70.1% to 90.2% (gpt-5.1, CPMpy). — [arXiv 2506.06052v3](https://arxiv.org/html/2506.06052v3)
- Iterative agent loop in a persistent code environment (CP-Agent) — [arXiv 2508.07468](https://arxiv.org/html/2508.07468). Solver feedback as a reinforcement-learning reward (SIRL) — [arXiv 2505.11792](https://arxiv.org/pdf/2505.11792). Closed-loop diagnosis and repair (OptiRepair) — [arXiv 2602.19439](https://arxiv.org/pdf/2602.19439)
- Sensitivity to wording: in SCHEDBench, reordering constraints in the text changed violation rates beyond the noise between random seeds for five models. Identical formal problems gave different violations under equivalent phrasings, so constraint order acts as a "latent control variable". — [arXiv 2608.00991](https://arxiv.org/html/2608.00991v1)
- Evaluation fragility: a matching objective value does not prove the model is correct. ORGEval proposes checking whether the generated model is graph-isomorphic to the reference instead. — [arXiv 2510.27610](https://arxiv.org/pdf/2510.27610)
- Human confirmation and explanation: CIR/R2C and TRACE-cs include user verification steps. TRACE-cs (course scheduling) uses logic to produce provably correct explanations and uses the LLM only to phrase them. — [arXiv 2409.03671](https://arxiv.org/html/2409.03671v3); [arXiv 2602.02029](https://arxiv.org/abs/2602.02029)
- Separating extraction from formulation (templates) is itself the mitigation in SMILO (90% correct versus about 55% direct). — [arXiv 2511.02364](https://arxiv.org/abs/2511.02364)

### Inferences
- Product mitigations ranked by evidence: (1) constrain the target, using a catalog or templates; (2) execute and test against independent checkers or several instances, never only against the example the user gave; (3) sample several times and require agreement; (4) read the parsed rule back to the user in plain language before it takes effect; (5) use solver-backed explanations (MUS or conflict sets) for infeasibility rather than LLM guesses. The MUS-based explanation work came from prior knowledge of Tsouros/Guns group papers and was not re-verified here.
- Normalize or reorder rule text internally (for example, the order of the catalog) to reduce the wording sensitivity SCHEDBench documents.

### Gaps
- No quantitative study was found specifically on LLM + MUS explanations to end users in this session.

## Q5. Work on LLMs plus rostering, timetabling and assignment

### Takeaway
Such work exists but is thin. When LLMs build schedules directly, the schedules are frequently infeasible, especially for timetabling. Model generation for workforce scheduling works best with expert templates, and interactive scheduling systems (MeetMate, TRACE-cs) use the LLM as a translator around a CP or logic core.

### Cited Findings
- SCHEDBench (preprint, Aug 2026): 1,132 instances across job-shop, RCPSP, nurse rostering (INRC, NSPLib) and curriculum timetabling (ITC). The LLMs write schedules directly, which OR-Tools CP-SAT then validates. Best overall feasibility is GPT-5.5 at 55.9%; the median across 13 models is 15.2%. Average feasibility by problem type: INRC nurse rostering 63.4%, NSPLib 33.8%, ITC timetabling 0.4%, job-shop 14.2%. — [arXiv 2608.00991](https://arxiv.org/html/2608.00991v1)
- SMILO (workforce scheduling, MILP via expert templates): 90% correct models, more than 35 points above direct LLM. — [arXiv 2511.02364](https://arxiv.org/abs/2511.02364)
- MeetMate (meeting scheduling, LLM + CP, ACM TiiS 2024, PR): a diary study, a quantitative evaluation and a user study. — [arXiv 2312.06908](https://arxiv.org/pdf/2312.06908)
- TRACE-cs (course scheduling, hybrid logic + LLM explanations). — [arXiv 2409.03671](https://arxiv.org/html/2409.03671v3)
- LLM-H²S (SSRN preprint): the LLM acts as a hierarchical heuristic solver for multi-constraint nurse scheduling. It notes that classic IP, metaheuristic and CP methods cannot take constraints stated in natural language. — [SSRN 7009806](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7009806)

### Inferences
- Strong evidence that the LLM must not be the solver for timetabling (0.4% feasibility). The architecture should be: LLM turns language into a structured rule, a deterministic compiler turns the rule into constraints, and a CP-SAT solver produces the schedule. This matches what MeetMate and SMILO do.

### Gaps
- No public benchmark was found for school timetabling rules in natural language that measures correct translation of rules (as opposed to direct schedule generation). This is an open gap. Nothing was found on Hebrew-language or other non-English rule statements.
