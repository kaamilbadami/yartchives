# Yartchives Roadmap

This file is the durable product and engineering roadmap for Yartchives.

Current `main` is the source of truth. GitHub issues are bounded execution units underneath this roadmap; they should not become a second competing roadmap.

## Product thesis

Yartchives is a CS-first internship product focused on one question:

> What should I apply to next?

The product combines public opportunity sources into one normalized feed, then uses Apply Next to turn that feed into a decision queue instead of another job board to browse.

The first beta is intentionally focused on Computer Science students. Broader career-area support can come later without changing the underlying architecture.

## Roadmap operating model

Use this hierarchy:

**roadmap outcome → measurable gap/evidence → bounded GitHub issue → resource locks → implementation → measurement → next gap**

Roadmap tracks describe durable outcomes, not implementation tasks.

A roadmap item should produce implementation work only when there is concrete evidence of a gap. Do not create work merely to keep agents busy.

When implementation work is created:

- inspect current `main` first;
- keep one issue bounded to one root-cause change;
- prefer regression tests and generic architecture over one-off patches;
- preserve product invariants unless an issue explicitly changes them;
- use resource locks to prevent overlapping work;
- prefer broad aggregators as the discovery backbone and direct employer sources as targeted gap-fillers;
- do not use LinkedIn or Handshake as production scraping sources;
- keep unknown requirements unknown;
- do not commit private user profile, resume, credential, secret, or account data.

## Current phase: CS-first beta

The near-term objective is a small CS-student beta where the core loop works reliably:

**profile → recommendations → Apply / Hide / Save → next recommendation → Good / Bad feedback**

The beta does not require perfect market coverage, every ATS family, broader career areas, or a major redesign.

The beta is ready when:

- automation no longer needs routine manual babysitting;
- the UI is clearly CS-first;
- Apply Next is fast, concise, and understandable;
- recommendation explanations make the value and biggest concern clear;
- action state changes are responsive and reversible;
- major empty, error, and mobile states are covered;
- obviously dead or inappropriate recommendations are under control;
- recommendation feedback is available and useful for learning.

Issue #280 remains the final beta verification gate.

---

## Track 1 — Automation reliability

### Outcome

GitHub issues, Jules sessions, PRs, checks, merges, retries, and cleanup should complete without the product owner acting as the workflow orchestrator.

### Success signals

- eligible autonomous work starts without manual dispatch;
- completed work does not remain stuck as open PRs or stale Jules sessions;
- transient Jules/platform failures receive bounded automatic recovery;
- workflow-failure issues enter the same authoritative lifecycle as normal autonomous work;
- spare Jules capacity is used for legitimate non-overlapping work when such work exists;
- task-generation or maintenance automation can fail without blocking already-valid product work.

### Near-term direction

- Finish the authoritative workflow-failure → Jules lifecycle work.
- Add evidence-backed autonomous backlog replenishment (#507).
- Keep concurrency resource-driven rather than forcing arbitrary utilization.
- Improve diagnostics when slots remain unused.

### Non-goals

- weakening resource locks to increase session count;
- inventing refactors or cleanup tasks just to occupy Jules capacity;
- letting automation make product-policy decisions silently.

---

## Track 2 — Feed coverage and source quality

### Outcome

Yartchives should discover a large, useful share of relevant US undergraduate CS opportunities while preferring validated direct application destinations.

### Success signals

- independent coverage benchmarks improve over time;
- direct-link coverage is high enough that intermediary destinations are exceptional rather than routine;
- source-family failures are isolated and diagnosable;
- the largest remaining gaps are attacked generically by ATS/source family;
- broad aggregators remain useful as the backbone while employer sources close measured gaps;
- the product does not claim complete market coverage before the coverage contract is actually satisfied.

### Near-term direction

- Resolve the current systemic source-health regression.
- Raise direct-link coverage by fixing generic unresolved destination patterns.
- Continue the evidence-driven generic coverage loop.
- Improve Fortune 500 / high-value CS benchmark coverage by fixing source-family gaps, not by accumulating employer exceptions.

### Non-goals

- maximizing source count for its own sake;
- employer-by-employer scraping campaigns;
- scraping LinkedIn or Handshake as production sources.

---

## Track 3 — Apply Next recommendation quality

### Outcome

A student with limited application time should be able to choose the next few roles to apply to without opening another job-search product.

### Success signals

- recommendations reflect qualification fit, application value, location fit, and freshness under the canonical scoring contract;
- eligibility remains a gate rather than a bonus;
- link provenance remains metadata rather than a ranking signal;
- weakly understood listings do not outrank similarly strong, well-understood listings without an explainable reason;
- recommendations clearly state why the role is worth applying to and the biggest concern;
- recommendation quality improves from actual beta feedback rather than speculative scoring complexity.

### Near-term direction

- Keep the Top 10 decision-first and concise.
- Improve authoritative posting evidence coverage where it materially changes recommendation confidence.
- Continue competition/application-value work without presenting fake acceptance probabilities.
- Improve required-vs-preferred and evidence-confidence explanations.
- Use beta feedback to identify ranking problems before expanding the model.

### Non-goals

- opaque AI/LLM ranking as the default decision engine;
- prestige/selectivity scores disguised as acceptance probability;
- silent changes to the 100-point scoring contract.

The current scoring semantics are defined in `PRODUCT_INVARIANTS.md`.

---

## Track 4 — Frontend and product experience

### Outcome

The CS-first beta should feel fast, obvious, and focused on decision-making rather than exposing internal system complexity.

### Success signals

- Apply Next has a clear entry and profile setup flow;
- the recommendation queue does not overwhelm the user with unnecessary listings;
- primary actions respond immediately and preserve state correctly;
- mobile layouts keep important actions accessible;
- loading, empty, stale, and error states are understandable;
- labels and controls use language students understand;
- the interface does not expose implementation/debug concepts unless they provide user value.

### Near-term direction

- Finish the current beta UI polish.
- Keep the landing/header hierarchy concise.
- Remove redundant or misleading controls.
- Reduce avoidable navigation/loading latency.
- Use beta sessions to find real confusion before larger redesign work.

### Non-goals

- a broad visual redesign before the core loop proves useful;
- adding features solely to make the interface look more complete.

---

## Track 5 — Performance and freshness

### Outcome

The feed and Apply Next should feel current and responsive without making slow enrichment work part of every critical path.

### Success signals

- feed publication cadence is predictable and observable;
- the dominant runtime stages are measured rather than guessed;
- slow enrichment, audits, and inspections are decoupled where they do not need to block publication;
- Apply Next interactions avoid unnecessary recomputation or network waits;
- freshness is represented honestly in ranking and UI;
- performance changes are justified by measured bottlenecks.

### Near-term direction

- Finish decoupling generated feed publication from Git commits.
- Keep bounded posting inspections off the hourly publication critical path.
- Persist enough stage-level observability to diagnose regressions.
- Optimize frontend paths only where measurements show meaningful user-visible delay.

### Non-goals

- speculative optimization;
- moving complexity into the client just to make workflows shorter.

---

## Track 6 — Beta learning and launch readiness

### Outcome

The first beta should generate useful evidence about whether Yartchives helps CS students decide what to apply to next.

### Success signals

- beta users can complete the core loop without explanation from the product owner;
- recommendation feedback is captured with minimal private data;
- recurring complaints become measurable product gaps;
- roadmap priorities change when real usage contradicts assumptions;
- known non-blocking limitations are documented before expanding the beta.

### Near-term direction

- Complete the final beta-readiness smoke test (#280).
- Run a small CS-student beta.
- Review Good / Bad suggestion feedback and observed friction.
- Convert repeated evidence into bounded roadmap-linked issues.
- Expand scope only after the core loop is stable.

### Non-goals

- treating beta launch as a finish line;
- expanding to broad career areas before the CS-first experience is validated.

---

## How autonomous work should use this roadmap

The roadmap is context, not permission to manufacture tasks.

Automation may create or queue work from a roadmap track only when all of the following are true:

1. there is a concrete current-main signal or measured gap;
2. the problem can be expressed as a bounded implementation task;
3. success can be objectively verified;
4. the task has explicit resource locks;
5. the task does not duplicate an existing issue;
6. the task does not conflict with active Jules, feedback-reserved, or Codex-reserved work;
7. the task does not require an unresolved product decision.

Good evidence includes reproducible workflow failures, failing regression coverage, machine-produced audit gaps, measured performance bottlenecks, repeated beta feedback, and benchmark regressions.

Weak evidence includes generic cleanup opportunities, subjective code-style preferences, speculative rewrites, documentation-only churn, and work whose value cannot be measured.

Issue #507 owns the first implementation of capacity-aware evidence-backed task generation.

## Relationship to older planning issues

Issue #18 contains valuable historical Apply Next product thinking and remains useful context, but this file is the durable cross-product roadmap going forward.

Issue #280 remains the current beta gate.

Individual issues should reference the relevant roadmap track when practical, but the roadmap should not duplicate every open issue or become a manually maintained issue index.

## Review cadence

Update this file when one of these changes:

- the product thesis;
- the current phase;
- a durable roadmap outcome;
- the definition of success for a track;
- a major non-goal or product invariant.

Do not update it for every implementation detail, PR, or transient bug. Those belong in GitHub issues and code.
