# Complaints workforce planning models for complex, age‑dependent casework

## How organisations typically model casework and backlog operations

A complaints operation like yours is best understood as a *backlog (“inventory”) system with deadlines*, not a classic “real‑time contact” queue. Your own description already contains the key distinguishing features: work items persist for days/weeks, accumulate into WIP, can be deferred, have allocation delays, can be reopened, and have regulatory deadlines that are measured in calendar or working days. fileciteturn0file0

This distinction matters because many widely taught workforce models in customer operations come from call centres, where work arrives continuously, is served immediately (or waited for), and does **not** create a multi‑day backlog in the same way. In mainstream call‑centre practice, the Erlang C (M/M/s) family and its variants (including Erlang A with abandonments) are commonly used for interval staffing, often via the “stationary‑interval / SIPP” approximation in which a day is broken into pieces and treated as approximately stationary within each interval. citeturn4view0

By contrast, back‑office/casework and “work item” environments are repeatedly described (by both independent commentary and vendors) as having *different mathematics* because: (i) work can be deferred into a backlog, (ii) service level goals are expressed in days/weeks/months or as deadlines rather than seconds, and (iii) people often have multiple work items open concurrently. citeturn16view0turn16view1turn16view2

These characteristics are also explicitly built into modern “back‑office workforce management” product narratives: they emphasise backlog tracking, deferrable work, longer SLAs, multi‑step processes, and skill/proficiency effects rather than abandon rates and short wait targets. citeturn16view1turn18view0turn16view2turn17view0

Publicly, it is hard to point to a single dominant “complaints‑specific” workforce planning model that leading UK banks or insurers openly document end‑to‑end (most firms treat these methods as internal operating IP). I don’t know the exact proprietary modelling stack used inside any specific firm unless they have published it. What *is* well‑documented across industries that run deadline‑driven, multi‑skill backlogs (telecoms field service, IT service request fulfilment, healthcare flow, back‑office operations) is a pattern: **simulation and simulation‑optimisation become the workhorse methods once the process has multi‑step flows, work prioritisation, and rich operational constraints**. citeturn6search0turn15view0turn6search9turn22view0

## Modelling paradigms that fit the complaints dynamics

A useful way to organise the model choice is to separate (a) *representation fidelity* (what behaviours can the model represent) from (b) *decision use* (what decisions it needs to support: staffing, cross‑skilling, prioritisation, hiring lead time, etc.). A major literature review of workforce planning methods groups approaches into **analytical**, **simulation**, and **empirical/data‑driven**; within simulation it specifically distinguishes **discrete‑event simulation (DES)**, **system dynamics (SD)**, and **agent‑based modelling (ABM)**. citeturn22view0

For your interdependency structure—especially “age profile → burden → unit hours → capacity → age profile”—three paradigms are especially relevant:

**Discrete‑event (or discrete‑time) simulation**  
DES is repeatedly used where the system has a chronological sequence of events, multiple queues, complex routing/allocation rules, heterogeneous skills, and SLA/deadline logic. A concrete cross‑industry example is entity["company","Openreach","uk telecoms access network"]’s bespoke DES “Workforce Dynamic Simulator,” created specifically to evaluate resource commitments under different repair SLAs; their write‑up explicitly contrasts queueing theory and Monte Carlo against DES and argues DES better captures operational detail (skills, rosters, priority allocation, geography) when reality is complex. citeturn15view0  
In call‑centre operations research, a major simulation review similarly emphasises that uncertainty and operational complexity across the planning hierarchy often drive the need for simulation rather than closed‑form formulas. citeturn6search0

**Queueing theory and fluid approximations (analytical, but “deadline aware”)**  
Queueing can still be valuable, but more as *theory, approximations, and sanity checks* than a full operational “digital twin,” because your system violates key assumptions behind common Erlang models (e.g., no backlog, short services, stationary behaviour). This limitation is also stated explicitly in both industry commentary and vendor material: Erlang is portrayed as not designed for interruptible/deferred tasks or service levels expressed in hours/days. citeturn16view0turn16view1  
However, there is a rich queueing literature on **deadline/lead‑time systems** (earliest‑deadline‑first and related policies) that uses the right performance language—fraction late, lead‑time distributions—rather than only average wait/queue length. citeturn24search3turn24search7turn24search11

**System dynamics (stocks‑and‑flows) for feedback loops and tipping points**  
Your “burden spiral” is structurally a reinforcing feedback loop: as backlog ages, work content increases, which reduces throughput, which further increases backlog. SD is designed to represent stocks (WIP) and flows (arrivals/closures) with feedback, delays (allocation delays, hiring lead time), and nonlinearities. Workforce/backlog SD models are common enough that there are dedicated SD papers building “workforce + backlog” structures for teaching and experimentation. citeturn14view0turn22view0turn14view2

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["system dynamics stock and flow backlog diagram","discrete event simulation process flow diagram queue resources","queueing theory diagram customers servers waiting line","workforce management backlog service level dashboard"],"num_per_query":1}

From a practical modelling standpoint, the consistent message across method reviews is: simulation approaches are often preferred when you need a thorough understanding of a workforce system and its interactions, while recognising that simulation itself does not “guarantee optimality” (you often pair it with optimisation if you need prescriptive staffing decisions). citeturn22view0turn6search9turn6search0

## Handling the burden–age feedback loop and steady‑state behaviour

Your “burden multiplier rises with age” is an example of **delay‑dependent / state‑dependent service requirements**: the work required to complete an item is not independent of how long it has waited or how congested the system is. This is not just an intuitive operational observation; it aligns with a broader service operations literature that documents *workload‑dependent* or *delay‑dependent* service times and then develops queueing models where service behaviour changes with system state. citeturn5view0turn5view1turn1search14

Two implications follow for modelling your spiral:

A closed‑form “one‑shot” staffing formula is unlikely to be robust once burden materially depends on the age distribution. Even in much simpler settings, state‑dependent queues require careful translation from empirical service time patterns into model parameters (and the literature notes pitfalls in treating mean service times as simply the inverse of service rates once state dependence is introduced). citeturn5view0

Iteration, simulation, or a fixed‑point solver is the normal resolution mechanism. In other words: you generally solve “capacity = demand hours” jointly with “demand hours depend on backlog age/burden” by iterating until the age distribution and the implied burden are consistent with the achieved throughput.

A useful conceptual way to frame steady state in your environment is:

- The system is stable only if *effective* completion capacity exceeds *effective* work creation over the long run.
- But “effective” here is nonlinear: once backlog ages, *required work per completion* increases (your burden), so the same headcount produces fewer closures, which pushes the system further into an older age mix.

In classic queueing, a baseline stability condition is that utilisation (traffic intensity) must be below 1 for a basic queue to have a steady state; in large‑scale call‑centre theory this extends into the **quality‑and‑efficiency driven** regime and “square‑root safety staffing” logic, which provides structural insight into why small buffers can prevent large performance degradation. citeturn3view1turn4view0  
But your burden mechanism makes the system closer to a “nonlinear service” queue/network: as delay rises, the service requirement rises, which is exactly the sort of mechanism that can create tipping points and apparent “backlog explosions” even when you thought you were only slightly under‑resourced. The fact that multiple industries build bespoke simulation for SLA/resource assessment under complex allocation rules is consistent with this: they do it because simple models often miss these nonlinearities. citeturn15view0turn6search0

A practical steady‑state answer for complaints therefore tends to be framed as:

- Use a fast, iterated model (fluid or age‑structured) to compute equilibrium WIP/age under a proposed staffing plan and prioritisation policy; then
- Use simulation to validate the equilibrium and explore non‑steady behaviours (weekday/weekend cycles, demand spikes, hiring lags).

This is effectively what the back‑office WFM tooling literature describes: iterative evaluation of schedules and service levels for “immediate and deferred queues,” tracking backlog, and incorporating skill/proficiency, rather than assuming an Erlang‑style closed form. citeturn16view1turn17view0turn18view0

## Allocation, diary management, and prioritisation policies

### Allocation delay and the “two‑pool” structure

Your unallocated pool + allocated diary structure can be modelled as a **two‑stage network**: (1) intake/triage queue (unallocated), then (2) casework processing (allocated). This resembles structures used in multi‑step back‑office modelling, where items can be held, moved between process steps, and are processed by different teams. citeturn16view1turn18view0

One important takeaway from the vendor and practice literature is that *forecasting data and operational data are fragmented in back offices*, so tooling often puts emphasis on establishing consistent volume, inventory (backlog), and completion measurement across disparate sources (workflow systems, completed volumes, productivity capture). citeturn18view0turn16view1  
For your modelling, that implies the two‑pool logic should be treated as first‑class state (not a minor correction), because the allocation delay changes both the age‑at‑work‑start and the FTC probability realisation point.

### Diary size, multitasking, and WIP limits

The research base for “diary size → productivity” in complaints specifically is not something I can point to as a single canonical result. What *is* documented in adjacent “knowledge work item” domains is the general flow principle: high WIP increases cycle time and can reduce throughput due to multitasking and waiting effects.

Two strands are particularly transferable:

- Back‑office commentary explicitly notes that employees often have multiple work items open at the same time, unlike telephony. citeturn16view0
- Empirical Kanban research (in another multi‑item knowledge‑work domain) finds that WIP is correlated with lead time: lower WIP tends to be associated with shorter lead times, consistent with queues/flow theory. citeturn8search7turn8search1

In operational terms for complaints, this suggests a realistic modelling feature: diary size is not just an “output metric,” it can be a *control lever* (a WIP limit per handler, per skill group) that shapes cycle time and breach risk by reducing context switching and making work‑completion more “pull‑based.”

A second transferable strand comes from public sector casework (e.g., entity["organization","Department for Education","UK government department"] guidance on social work), which explicitly separates *caseload counts* from *workload/complexity* and encourages time‑diary approaches to understand intensity and task mix—because case counts alone can be misleading. citeturn8search2turn8search20  
This aligns with your “touches” concept: if touches (and their timing) vary, then diary size alone is an incomplete predictor of load, and you need a work content model (touch distribution or effort‑over‑age curve).

### Prioritisation policies for breach control

Once deadlines exist, “oldest first” becomes a natural heuristic, and there is deep queueing literature on **earliest‑deadline‑first (EDF)** and related due‑date disciplines where performance is measured by lateness/late fraction rather than only average waiting time. citeturn24search3turn24search7turn24search11

The caveat is that many EDF optimality results are presented in settings with assumptions that differ from human casework (e.g., preemption allowed, overheadless switching, known processing times). citeturn24search7turn23view1  
For your environment, the practical takeaway is not “EDF is optimal,” but:

- “Time‑to‑deadline” is the right state variable for SLA risk control.
- Priority policies meaningfully change the equilibrium age distribution, which changes burden and closes the loop back into capacity.

That means prioritisation should be modelled explicitly and tested, not assumed.

## Regulatory SLA modelling for FCA and payment services

Two features make your regulatory constraints unusually important for workforce planning:

- They are strict “final response” style deadlines with customer escalation paths.
- They mix **calendar‑day clocks** (8 weeks) and **business‑day clocks** (15/35 business days), which interact with weekday‑only staffing and weekend ageing.

### FCA DISP time limits and reporting categories

Under entity["organization","Financial Conduct Authority","uk financial regulator"] complaint rules, the headline concept is that firms must provide a “final response” within **8 weeks** for most complaints; this is repeatedly referenced across FCA‑linked materials and policy discussions. citeturn11search0turn11search6turn11search16turn11search20

Recent FCA complaints reporting policy also underscores why “age bands” matter operationally: reporting categories explicitly include “closed within 3 days,” “closed within 8 weeks but after 3 days,” “closed after 8 weeks,” and “open after more than 8 weeks,” which structurally mirrors the way your model tracks survival/age profiles and breach states. citeturn9view2turn11search22

For modelling, this supports a best‑practice structure: treat age‑based segmentation as a first‑class state and ensure your simulator can reproduce the regulatory reporting breakdowns by design, not as an after‑the‑fact BI layer.

### Payment services complaint deadlines

Public sources aimed at firms state that payment services complaints have a shorter deadline: **15 days** to resolve, extendable to **35 days** in exceptional circumstances with interim communication expectations (and firms must still respond within 15 days to explain the delay and expected final response timing). citeturn9view3turn0search10turn0search4

This is directly relevant to your workforce model for two reasons:

- Your system needs both *calendar* and *business day* clocks, sometimes simultaneously (because a case can be in a product line that mixes PSD2‑eligible and non‑eligible complaint types).
- Weekend closures are absent (Mon–Fri working), while ageing continues (calendar days always advance), creating deterministic “Monday bulge” dynamics and systematic deadline pressure around long weekends.

Back‑office WFM documentation from multiple vendors describes a similar operational truth in generic terms: back‑office tasks can queue and wait while teams are not scheduled (e.g., closed days), and WFM logic may distribute workload across open days within the SLA horizon. citeturn16view2turn16view1  
That behaviour is conceptually close to what you need for weekend/weekday realism, except your SLAs are regulatory and heterogeneous rather than a single “handle within 30 days” setting.

### Early warning systems and “cases at risk of breach”

The emerging tool pattern is to compute SLA performance as “completed within SLA ÷ completed total” and provide intraday monitoring of service level and occupancy for workitems/cases, supplemented by workflow‑based alerts and instrumentation. citeturn17view0turn18view0turn16view1  
The key modelling implication is that “early warning” is not separate from the workforce model: it’s the same lead‑time/age distribution state, just exposed operationally with thresholds and forward projections.

## Tooling landscape and a recommended end‑to‑end framework

### What commercial tools exist and what they typically cover

The commercial “WFM + backlog/work item” ecosystem generally provides:

- Forecasting of volume and handle time for workitems/cases, capacity planning and hiring plans, schedule generation, and service level reporting. citeturn17view0turn17view1turn18view0turn16view1
- Back‑office specific features such as backlog tracking, deferrable task service goals (days/weeks), and multi‑skill/proficiency support; some tooling explicitly describes “queue hopping”/resource sharing between work queues based on priorities and service goals. citeturn16view1turn18view0turn16view2

What these tools *often do not* give you out of the box—especially for a complaints operation with your specific loops—is a transparent, calibrated model of **age‑dependent burden** and changes in work content as cases approach breach. Vendors discuss deferrable work, backlog, and proficiency; the “burden multiplier as a function of age band” is typically something you would calibrate internally and either (a) embed into your own simulator, or (b) reflect indirectly via empirical handle time patterns by age and workflow stage. citeturn16view1turn5view0turn5view1

### What open frameworks exist

If you continue building in Python, there are mature simulation libraries for DES such as **SimPy** (process‑based discrete‑event simulation in Python) and **salabim** (Python DES framework; published in the Journal of Open Source Software). citeturn21search0turn21search8turn21search25  
For hybrid SD+DES approaches, both the method literature and major commercial simulation platforms explicitly promote multi‑method (“hybrid”) modelling when you need feedback loops plus detailed event logic. citeturn21search6turn21search24turn7search20

### A best‑fit modelling framework for your complexity level

Given your scale (~1,000/day, ~800 handlers, 14 skill groups) and the specific feedback loops you described, the strongest evidence‑aligned recommendation is a **hybrid framework** with three layers, each used for what it is good at:

**A steady‑state / fast scenario layer (iterated age‑structured model)**  
Purpose: rapid staffing estimates, “what if” comparisons, and producing an equilibrium age profile consistent with capacity.  
Method: an iterated stock‑and‑flow or age‑structured fluid model that solves a fixed point: the closure capacity implied by headcount must match arrivals given the burden implied by the resulting age distribution. This directly addresses the fact that closed‑form Erlang logic is not designed for deferred/backlogged work with long deadlines. citeturn16view0turn16view1turn5view0turn22view0

**A policy‑accurate operational layer (discrete‑event or discrete‑time simulation)**  
Purpose: evaluate allocation rules, FTC behaviour at assignment, weekend/weekday calendars, cross‑skilling overflow, prioritisation strategies (oldest‑first vs newest‑first vs time‑to‑deadline), seasonal spikes, and replan cadence.  
Rationale: this is the approach used in multiple complex SLA environments explicitly because it can represent “real world” constraints and rule‑based allocation. citeturn15view0turn6search0turn17view0turn18view0

**A prescriptive decision layer (optimisation wrapped around simulation)**  
Purpose: choose headcount by skill group (and cross‑skill mix) that minimises cost under breach/service constraints, including robustness to demand uncertainty and training lags.  
Rationale: in call‑centre multi‑skill staffing, a well‑established line of work uses **simulation‑optimisation** and linear/integer programming with simulation evaluation because purely analytical service level constraints are hard in multi‑skill systems. citeturn6search9turn6search0turn4view1

This layered approach also maps cleanly onto the “capacity planning hierarchy” emphasised in call‑centre operations research: forecasting → staffing → scheduling → intraday control, with increasing operational detail as you move from strategic to real‑time decisions. citeturn3view1turn4view0

### How this framework answers your core research questions

It directly resolves the circular dependencies you highlighted by treating them as a coupled dynamic system rather than a single‑pass formula, which is consistent with the broader literature on state‑dependent service and backlog systems. citeturn5view0turn5view1turn14view0turn16view1

It provides a natural way to represent and test:

- The “burden‑WIP spiral” as a nonlinear service requirement effect (delay/state dependent service), which has recognised importance in queueing/service science. citeturn5view1turn1search14turn5view0
- Allocation delay and FTC as a branching event at assignment time (two‑stage network). citeturn17view1turn16view1
- Cross‑skilling and overflow as multi‑skill routing/capacity sharing, which is exactly the class of problem where simulation‑optimisation is common. citeturn6search9turn6search21turn4view1
- Deadline/breach performance using lead‑time/to‑deadline state (EDF‑style thinking), focusing on “fraction late” and lateness distributions rather than only average time. citeturn24search3turn24search7turn24search11
- Weekend/weekday dynamics using calendar‑time simulation and “work only on open days” logic similar to backlog WFM handling. citeturn16view2turn17view0turn9view3

In short: for your level of complexity, the “best” model is usually not a single technique. It is a **hybrid, calibrated, simulation‑centred framework** with a fast steady‑state solver and an optimisation wrapper—because that combination is the most consistent with (i) what the workforce planning literature recommends when systems are complex, (ii) the documented limits of Erlang‑style formulas for deferred/backlogged work, and (iii) how other SLA‑heavy industries justify their choice of simulation for resource and service‑level trade‑offs. citeturn22view0turn16view0turn16view1turn15view0