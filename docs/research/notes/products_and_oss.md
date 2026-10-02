# Chat-driven constraint solver landscape: products and open source (as of Oct 2026)

Method note: about 25 web searches and fetches on 2026-10-02. Some fetched pages read as forward-dated (for example, Timefold blog posts dated June 2026 and model names such as "GPT-5.6-Terra" and "Gemini 3.8 Flash" in repos). They are reported as the sources state them. Star counts are as of the fetch date. Several vendor claims could only be checked against marketing pages; these are marked "marketing only".

## Q1. Which commercial products offer chat or natural-language rule entry for scheduling, rostering or optimization?

### Takeaway
Big solver vendors (Gurobi, IBM, Timefold) now have LLM layers, but these are aimed at modelers and developers or at explaining and querying schedules. They are not end-user "describe rules → solved roster" tools. Workforce-management apps (Deputy, ShiftScheduler.ai) add chat agents that edit and publish schedules on top of fixed rule settings. School timetabling apps advertise "AI" chat without technical evidence. None of the products checked lets a non-expert define arbitrary new constraint types in chat and have them compiled into a verified solver model.

### Cited Findings

**Gurobi (MIP solver vendor)**
- Feb 2025: Gurobi launched "Gurobi AI Modeling". It has a docs page, an "AI Modeling Assistant" custom GPT that converts plain-text problem descriptions into mathematical models and **gurobipy code** (so the LLM writes free-form code), and a "Prompt Engineer" custom GPT that iterates with the user toward a good problem description. The approach is described as "problem-first, mathematics-second". — [Gurobi newsroom](https://www.gurobi.com/company/newsroom/gurobi-ai-modeling-empowers-users-with-accessible-optimization-resources); [BusinessWire 2025-02-13](https://www.businesswire.com/news/home/20250213363045/en)
- Later, Gurobi launched the "Intelligence Hub" with three agents. "Modeler" (beta) translates business problems into production-quality models. "Explainer" (experimental) allows natural-language interaction with models and faster infeasibility diagnosis. "Gurobot" is the earlier assistant, now consolidated into the Hub. Gurobi also ships an experimental **Local MCP server** for Cursor, Claude Desktop and custom agent pipelines. The article gives no date and no pricing. — [EfficientlyConnected](https://www.efficientlyconnected.com/gurobi-intelligence-hub-ai-agents-optimization/)
- Classification: general (any MIP), developer and analyst audience, needs a commercial Gurobi licence to solve. It is not a scheduling product.

**IBM Decision Optimization (watsonx / Cloud Pak for Data)**
- The "Modeling Assistant" lets users "formulate models in natural language", which "requires little to no knowledge of OR, and does not require you to write Python code". The user first **selects a decision domain** and is then guided by the assistant. It is English only. Models deploy with watsonx.ai Runtime. — [IBM docs](https://www.ibm.com/docs/en/DSXDOC/DO/DODS_Mdl_Assist/exhousebuildintro.html)
- Inference: this is a long-standing (pre-LLM) guided controlled-natural-language feature over a **fixed catalog of domains and constraint templates**, with a CPLEX backend. It is the closest enterprise analogue to a "rule catalog" design. Whether it now uses generative LLMs was not confirmed.

**Timefold (formerly OptaPlanner team; open-core solver plus SaaS models)**
- Raised a **$13M Series A** (led by Alstin Capital, with KOMPAS VC) announced in July 2026. The "platform's copilot already lets planners interrogate schedules in natural language". The solver is deterministic and API-first ("JSON in, JSON out, over REST"). Timefold says AI agent adoption "pulls demand toward Timefold's API". — [KOMPAS VC](https://www.kompas.vc/news/why-we-invested-in-timefold)
- Position: "LLMs can't optimize schedules, but AI can". The problem space is too large for LLMs, for example 10 employees over one week is about 10^63 combinations. LLMs should call the solver through tool calling or **MCP**. — [Timefold blog](https://timefold.ai/blog/llms-cant-optimize-schedules-but-ai-can)
- Classification: domain-specific prebuilt models (employee shift scheduling, field service routing, and others), plus a general open-source solver (Apache-2.0, Java/Python). The copilot explains and queries schedules; I found no evidence that it authors new constraints from chat. No public pricing was found (demo-led). — [GitHub timefold-solver](https://github.com/TimefoldAI/timefold-solver)

**Nextmv (DecisionOps) → acquired by FICO**
- Nextmv is a DecisionOps platform (versioning, CI/CD, shadow testing) for routing, scheduling and packing models across Gurobi, CPLEX, OR-Tools and HiGHS. It was founded in 2019 and raised an $8M Series A from FirstMark. — [aggregator yespress](https://yespress.io/nextmv.md)
- FICO's acquisition of nextmv.io Inc **closed May 2026**. — [Faegre Drinker deal note](https://www.faegredrinker.com/en/services/experience/2026/6/fair-isaac-corporation-completes-acquisition-of-nextmvio-inc)
- Classification: infrastructure for OR teams. I found no concrete natural-language modeling product (gap).

**Deputy (shift-work WFM)**
- "Deputy AI" is a conversational agent: "build a schedule, edit shifts, and publish schedules using natural language", fill gaps and fix timesheets from a phone. — [Deputy AI page](https://deputy.com/ai); help article [here](https://help.deputy.com/hc/en-au/articles/14862592379791-How-to-manage-your-Schedule-with-Deputy-AI) (returned 403 to fetch, so details are unverified)
- Inference: the chat drives Deputy's existing auto-scheduler and its fixed rule settings (award and compliance rules). It is not open-ended constraint authoring.

**Quinyx**
- AI-driven scheduling built on demand forecasting (POS data, foot traffic). I found no evidence of chat-based rule entry. — [rfp.wiki comparison](https://www.rfp.wiki/vendors/quinyx/deputy)

**When I Work**
- Has an auto-assign feature. No natural-language agent was found in these sources. — [G2 compare](https://www.g2.com/compare/deputy-vs-when-i-work)

**ShiftScheduler.ai (small SaaS)**
- A rostering tool that uses **Google OR-Tools**. Users "define custom rules" through setup steps and then "ask me to schedule a specific date range" in chat. It has a **built-in MCP server** with tools such as shiftscheduler-search, -assign, -vacations and -location-history, so Claude or ChatGPT can operate it. Pricing is €1–2 per seat per month with a 30-day trial. — [shiftscheduler.ai](https://shiftscheduler.ai/)
- Classification: rostering-specific with a fixed rule set plus chat. This is the closest small commercial match to "chat + CP solver" for shifts.

**Solvice (OnShift)**
- A workforce-scheduling solver API (shift creation and filling). No LLM interface was confirmed. — [Solvice](https://www.solvice.io/workforce-scheduling-api)

**Lindy (AI agent builder)**
- Offers an "AI Employee Scheduling" template that assigns shifts by role, skills, seniority and hour limits. It is marketing only; no solver is disclosed. — [Lindy](https://www.lindy.ai/tools/ai-employee-scheduling)

**School timetabling**
- TimetableMaster advertises an AI agent with "natural language commands, intelligent execution" and a chat UI, and claims 50,000+ institutes. The page gives **no technical detail** on the solver ("machine learning", "neural networks") or on how chat maps to constraints. Marketing only. — [TimetableMaster](https://www.timetablemaster.com/timetable-generator-ai)
- Skoolia, Da1TimeTable, Kiwibee and Vidyalaya make similar "AI timetable generator" claims. Marketing only. — [Skoolia](https://skoolia.com/features/ai-timetable-generator); [Da1](https://da1timetable.ai/); [Kiwibee](https://kiwibee.io/en/solutions/scheduling)
- For aSc TimeTables and Prime Timetable, no LLM or chat features were found. Prime "has not stated whether it uses AI". — [Virto guide](https://www.virtosoftware.com/edu/school-time-table-maker-ai-guide/); [EdTech Impact](https://edtechimpact.com/products/prime-timetable/)

**AMPL**
- Publishes employee-scheduling notebooks (Colab). No LLM product was confirmed in this search. — [AMPL Colab](https://ampl.com/colab/notebooks/employee-scheduling-optimization.html)

### Inferences
- The market has split into three layers:
  - (a) Solver vendors add LLM copilots for modelers (Gurobi Modeler, IBM Modeling Assistant) or explanation (Timefold copilot, Gurobi Explainer).
  - (b) WFM apps add chat agents that operate fixed scheduling features (Deputy, ShiftScheduler.ai).
  - (c) Solver vendors expose MCP and tool-calling so third-party agents can call them (Gurobi Local MCP, ShiftScheduler MCP, Timefold's stated direction).
- No vendor checked publicly offers "manager-owned rules in plain language → validated constraint model → solve → explain trade-offs" for school class placement specifically.

### Gaps
- Not researched or no evidence found: Microsoft or Google first-party OR + LLM products (beyond OptiGuide research), Hexaly LLM features, Decision Brain, Cosmo Tech, Pathway, Taiga, Shiftboard, Untis AI features, and Quinyx's "Quinyx AI" assistant details.
- Pricing for Gurobi AI Modeling and Intelligence Hub (the custom GPTs appear free; the solver licence is commercial), IBM and Timefold was not found.
- The exact date of the Gurobi Intelligence Hub launch was not found.

## Q2. Which open-source projects combine an LLM with a solver?

### Takeaway
The open-source projects are mostly research agents that make the LLM write free-form solver code (OptiMUS, Chain-of-Experts, OptiGuide/OptiMind, mcp-solver v4), plus a growing set of MCP servers that expose solvers to any chat client. Only toy projects follow the "LLM fills a strict JSON rule schema → CP-SAT" pattern.

### Cited Findings
- **OptiMUS** (Stanford, Udell group) is an LLM agent that formulates MILPs from natural language, writes and debugs solver code, and checks solutions. Versions: v0.1 (2023, sequential), v0.2 (2024, agent-based), v0.3 (2024, RAG and large-scale). MIT licence, ~299 stars, only 32 commits. Hosted demo at optimus-solver.com. NLP4LP dataset (non-commercial). — [GitHub](https://github.com/teshnizi/OptiMUS); [arXiv 2407.19633](https://arxiv.org/html/2407.19633v3); [2026 paper PDF](https://web.stanford.edu/~udell/doc/udell26optimus.pdf)
- **Microsoft OptiGuide**: ~717 stars, MIT, active. It contains LLM what-if analysis for supply-chain optimization (Gurobi), "Foundation Models for MILP" (ICLR 2025), and **OptiMind** (teaching LLMs expert optimization formulation). The LLM writes code against a fixed existing model (what-if), not a model from scratch. — [GitHub](https://github.com/microsoft/OptiGuide)
- **Chain-of-Experts** is a multi-agent OR framework: a conductor coordinates interpreter, modeler, coder and reviewer agents with backward reflection. It is a research artifact (ICLR 2024). — [OpenReview](https://openreview.net/pdf/49af0563be670f07c0061eb77288f20933ca4ad5.pdf)
- **mcp-solver** (Stefan Szeider, TU Wien) has ~183 stars and an MIT licence. v1–v3 exposed tools for editing a MiniZinc, PySAT or Z3 model item by item (add_item, replace_item, solve_model) with validation on each edit; v3 is documented in a SAT 2025 paper. **v4 is a full redesign**: the host LLM is a "solver-writing agent" that writes Python in a persistent kernel (python_exec, submit_code). Backends are PySAT, MaxSAT, Z3, CPMpy, Clingo and DIDP. The README claims validation on 229+ benchmark instances. — [GitHub](https://github.com/szeider/mcp-solver); [arXiv 2501.00539](https://arxiv.org/html/2501.00539v2)
- **mcp-ortools** (Jacck) is an MCP server that takes a JSON model (variables with domains, constraints in OR-Tools method syntax, an optional objective) and solves it with CP-SAT. MIT, a small hobby project. — [Glama](https://glama.ai/mcp/servers/Jacck/mcp-ortools)
- Other MCP solver servers: chuk-mcp-solver, mcp-optimizer, minizinc-mcp, and a community GurobiMCP (KKonuru) that solves LLM-formulated problems on a local Gurobi. — [Glama chuk](https://glama.ai/mcp/servers/@chrishayuk/chuk-mcp-solver/blob/4b08db51f509407685916d8070e1b6d2b31e41ac/README.md); [Glama mcp-optimizer](https://glama.ai/mcp/servers/@dmitryanchikov/mcp-optimizer/blob/65db2231711535033936975e7450032a3a494954/README.md); [minizinc-mcp](https://glama.ai/mcp/servers/r33drichards/minizinc-mcp); [GurobiMCP](https://mcpservers.org/hi/servers/KKonuru/GurobiMCP)
- **slimaneoptic/shift-scheduler** follows the rule-catalog pattern. An LLM (via OpenRouter, with a built-in regex parser as fallback) turns free-form notes into changes that must match "a strict JSON schema", validated before **OR-Tools CP-SAT**. Coverage and seniority are high-penalty soft constraints, so the solver always returns a solution. It has 0 stars and 3 commits, so it is a toy, but it shows the architecture. — [GitHub](https://github.com/slimaneoptic/shift-scheduler)
- **Timefold Solver** and **OptaPy** provide employee-rostering and school-timetabling quickstarts. OptaPy is the older, superseded Python port, so treat it as legacy. — [OptaPy](https://github.com/optapy/optapy); [Timefold Python blog](https://timefold.ai/blog/new-open-source-solver-python)
- Research benchmarks and venues: ConstraintBench (2026) benchmarks LLMs solving constraint problems directly. The "LLM-Solve 2026" workshop covers LLMs and agents for constraint modeling, solving and explanation in scheduling, rostering and routing. — [ConstraintBench](https://arxiv.org/html/2602.22465v1); [LLM-Solve 2026](https://sites.google.com/view/llm-solve-2026)
- An individual developer pattern: use ChatGPT to write a constraint-solver program for personal logistics. — [emschwartz.me](https://emschwartz.me/new-life-hack-using-llms-to-generate-constraint-solver-programs-for-personal-logistics-tasks/)

### Inferences
- Two architectures dominate:
  - (1) **Free-form code generation**: OptiMUS, Gurobi AI Modeling and mcp-solver v4. This is flexible but needs validation loops, and errors are silent semantic bugs.
  - (2) **Structured model or rule schema**: IBM Modeling Assistant, mcp-ortools JSON, shift-scheduler JSON. This is safer and auditable but limited to the catalog.
- mcp-solver's move from validated item edits (v3) to free code (v4) suggests that its research authors find stronger LLMs make free-form code workable. That is for benchmark puzzles, not end-user-owned rules.

### Gaps
- Last-commit dates for OptiMUS and OptiGuide were not shown in the fetches.
- No well-known open-source "Timefold + LLM" quickstart or LangChain + OR-Tools scheduling app was confirmed.
- OptiMUS hosted demo status and pricing were not checked.

## Q3. Is there a genuinely general "upload spreadsheet + chat → solved assignment" product?

### Takeaway
I found no mature general product that does this end to end. The nearest options are:
- ShiftScheduler.ai: chat over OR-Tools, but rostering only with a fixed rule set.
- Gurobi AI Modeling and Intelligence Hub, OptiMUS's hosted demo, and mcp-solver in Claude Desktop: general, but they produce code for technical users and do not manage spreadsheets, rule ownership, explanations or iterations for non-experts.
- Generic chatbots (ChatGPT, Claude, Copilot), which are widely promoted for rotas and timetables but do not guarantee constraint satisfaction.

### Cited Findings
- Guides tell users to paste an Excel template into ChatGPT with max hours, availability and other rules and paste the roster back. There is no solver and no feasibility guarantee. — [RosterElf](https://www.rosterelf.com/blog/create-staff-rota-excel-using-chatgpt); [Virto guide](https://www.virtosoftware.com/edu/school-time-table-maker-ai-guide/)
- Timefold: Stephan Jansen tried to build a 5-day conference schedule with ChatGPT and got a feasible result for only one day. LLMs are non-deterministic. — [KOMPAS VC](https://www.kompas.vc/news/why-we-invested-in-timefold); [Timefold blog](https://timefold.ai/blog/llms-cant-optimize-schedules-but-ai-can)
- Research shows LLMs used directly as schedulers (for example, radiotherapy scheduling feasibility under realistic constraints, and "LLMs can Schedule") but not as production tools. — [arXiv 2605.12896](https://arxiv.org/pdf/2605.12896); [arXiv 2408.06993](https://arxiv.org/pdf/2408.06993)

### Inferences
- What existing options lack, compared with the vision:
  - Data ingestion from arbitrary spreadsheets, with column mapping.
  - A non-programmer-safe rule layer (validated catalog or DSL) rather than raw code.
  - Explanation of trade-offs and infeasibility in plain language. Gurobi Explainer is experimental and Timefold's copilot is domain-specific.
  - Multiple alternative solutions to compare.
  - Coverage of education use cases such as student class placement, for which no LLM + solver product was found.
- That niche (class placement and balancing with chat) appears unoccupied, based on what was checked.

### Gaps
- No search on Product Hunt or Hacker News for small startups (for example "constraint AI" style YC companies).
- Israeli or local school placement tools were not covered.

## Q4. Latest developments, 2025–2026

### Takeaway
2025–2026 brought consolidation (FICO buying Nextmv) and funding (Timefold's $13M Series A). Solver vendors are shipping agent and MCP layers (Gurobi Intelligence Hub, Local MCP), WFM vendors are adding conversational agents (Deputy AI), and MCP solver servers and benchmarks are spreading.

### Cited Findings
- Feb 2025: Gurobi AI Modeling (custom GPTs). — [BusinessWire](https://www.businesswire.com/news/home/20250213363045/en)
- 2025: mcp-solver v3 paper at SAT 2025; v4 later redesigned as a code-writing agent. — [GitHub](https://github.com/szeider/mcp-solver)
- ICLR 2025: Microsoft "Foundation Models for MILP"; OptiMind added to OptiGuide. — [GitHub](https://github.com/microsoft/OptiGuide)
- 2026: Gurobi Intelligence Hub (Modeler in beta; Explainer and Local MCP experimental). — [EfficientlyConnected](https://www.efficientlyconnected.com/gurobi-intelligence-hub-ai-agents-optimization/)
- May 2026: FICO completed its acquisition of Nextmv. — [Faegre Drinker](https://www.faegredrinker.com/en/services/experience/2026/6/fair-isaac-corporation-completes-acquisition-of-nextmvio-inc)
- July 2026: Timefold $13M Series A, with a natural-language copilot for querying schedules. — [KOMPAS VC](https://www.kompas.vc/news/why-we-invested-in-timefold)
- 2026: ConstraintBench and the LLM-Solve 2026 workshop. — [ConstraintBench](https://arxiv.org/html/2602.22465v1); [LLM-Solve](https://sites.google.com/view/llm-solve-2026)

### Inferences
- The industry consensus, stated explicitly by Timefold and implied by Gurobi's and IBM's designs, is "LLM for language, solver for search". The open question is how much of the model the LLM may write.

### Gaps
- Not verified in this pass: launch dates and details for Deputy AI, Quinyx AI and When I Work AI features; Google OR-Tools or Microsoft first-party LLM integrations in 2026.
