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
- do not use LinkedIn, Handshake, or Indeed as production scraping sources; use them only to discover/audit gaps and trace roles back to authoritative employer/ATS destinations;
- keep unknown requirements unknown;
- do not commit private user profile, resume, credential, secret, or account data.

## Current phase: prove discovery trust before beta promotion

The near-term objective is not feature completeness. It is to prove that Yartchives is a more trustworthy way for a CS student to decide what to apply to next than a diligent repeated ChatGPT/web-search workflow.

The core loop remains:

**profile → recommendations → Apply / Hide / Save → next recommendation → Good / Bad feedback**

But a polished ranking experience is not sufficient if the candidate universe is materially incomplete. Coverage therefore becomes a release-critical input to trust, not merely an ongoing maintenance metric.

Yartchives should not be treated as broadly beta-ready until:

- a reproducible external-discovery benchmark compares Yartchives against a diligent, tailored ChatGPT/web-search workflow across representative student personas;
- Yartchives captures the large majority of reviewed strong opportunities from that external benchmark, with no obvious systemic ATS/source-family holes;
- Yartchives also surfaces additional strong opportunities or provides materially better freshness, authoritative links, evidence, ranking, or persistent context such that the overall student decision workflow is better than the external baseline;
- misses are classified by root cause: employer discovery, provider resolution, retrieval, normalization/classification, term filtering, freshness, link quality, or ranking;
- source-family misses generate generic fixes and are re-measured until the systemic gap is closed or shown to be non-release-blocking;
- recommendation usefulness, eligibility, explanation integrity, security, and first-use UX gates also pass.

Perfect market coverage is not required. Materially inferior discovery coverage is a release blocker.

Issue #898 is the trust/readiness release gate. Issue #901 is the security/abuse-resistance release gate.

### Trust benchmark implementation sequence

The first trust benchmark is now an explicit staged build rather than a one-off manual comparison:

1. check in a sanitized persona cohort using short mnemonic codes only;
2. convert each persona into a bounded, reproducible search/ranking input without committing raw resumes, social-profile dumps, contact details, citizenship, or work-authorization assumptions;
3. build the external-discovery set independently of the Yartchives feed using a diligent tailored ChatGPT/web-search workflow;
4. validate discovered opportunities against authoritative employer/ATS destinations and freeze the reviewed comparison set before looking at Yartchives recall;
5. run the same frozen personas against the current Yartchives feed/ranker and capture the visible Top 10 plus candidate-universe evidence;
6. measure opportunity-level recall, usefulness, eligibility/trust failures, freshness/link quality, and Yartchives-only useful discoveries;
7. classify every meaningful miss through the existing coverage taxonomy and create the smallest bounded ATS/source/ranking/eligibility follow-up issue;
8. rerun only the affected benchmark slice after each fix, while preserving the frozen external comparison set unless the benchmark is intentionally versioned.

The initial reviewed real-derived cohort is `KB`, `AA`, `JH`, `AL`, `GW`, `DD`, `BM`, `NR`, and `AM`. The existing Bel Air finance-sophomore reference remains in the benchmark suite so Finance coverage is still represented even though the first real-user-derived cohort is sophomore-heavy. Add synthetic freshman/junior and other edge cases only to cover release-gate gaps, not to replace the real-derived cohort.

The first implementation should optimize for reproducibility and measurement, not a perfect harness. Persona fixtures and deterministic validation come first; independent external discovery and authoritative validation come next; ranking/coverage defects discovered by the run become separate bounded work.

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
- Use all otherwise-idle Jules capacity for legitimate evidence-backed work when non-overlapping current-main signals exist; existing eligible work is always selected before generating more.
- Keep #507's evidence-backed replenishment architecture healthy and extend providers only from machine-verifiable signals; zero generated work remains valid when no strong evidence exists.
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

- against a reviewed external-discovery benchmark, Yartchives captures the large majority of strong opportunities a diligent repeated ChatGPT/web-search workflow finds for representative CS-student personas;
- Yartchives also finds useful opportunities the external workflow misses, or provides enough freshness, authoritative evidence, ranking quality, and persistent context to make the overall decision workflow materially better;
- coverage is measured at the opportunity level, not only by indexed-listing count or resolved-employer count;
- the coverage chain is observable end to end: employer discovered → provider/source resolved → jobs retrieved → internship/term/classification preserved → authoritative destination reachable → role reaches the candidate set;
- direct-link coverage is high enough that intermediary destinations are exceptional rather than routine;
- source-family failures are isolated and diagnosable;
- the largest remaining gaps are attacked generically by ATS/source family;
- broad aggregators remain the discovery backbone while employer/ATS sources close measured gaps;
- the product does not claim trustworthy market coverage before the release benchmark supports it.

### Near-term direction

- Bootstrap the sanitized multi-persona fixtures and deterministic validator, then build and run the external ChatGPT/web-search comparison required by #898. Freeze externally discovered strong opportunities before comparing them with Yartchives, and convert "captures most strong opportunities" into a measured threshold before release rather than relying on listing-count intuition.
- Treat opportunity recall against that benchmark as the primary coverage metric; use employer/provider resolution as diagnostic leading indicators rather than the final success condition.
- Resolve the largest current systemic source-family and discovery gaps before spending roadmap priority on additional UI polish or ranking complexity.
- Keep independent ATS-family coverage lanes continuously replenished: Workday, Greenhouse, Lever, Oracle, iCIMS, SmartRecruiters, Ashby, SuccessFactors, Eightfold, Avature, Phenom, BrassRing, Jobvite, Paylocity, Breezy, Workable, ApplyToJob, Paradox, and newly fingerprinted families each use their own resource lock.
- After an ATS-family task completes, re-measure current `main`; if a meaningful generic gap remains, allow the next bounded issue for that same family to be generated automatically. Do not impose one blanket coverage WIP cap across independent ATS locks.
- Expand coverage benchmarks beyond Fortune 500 to the employer/source categories that materially matter for CS internship search: major technology, defense/aerospace, finance, semiconductor, industrial/engineering, research labs, government, universities, strong regional employers, and high-value remote roles.
- Fix source-family gaps generically rather than accumulating employer-specific production exceptions.

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

Broad beta promotion should happen only after Yartchives demonstrates that its discovery + ranking workflow is trustworthy enough to outperform a diligent general-purpose ChatGPT/web-search workflow for the target CS-student use case.

### Success signals

- #898's external-discovery comparison shows Yartchives is not materially missing strong opportunities that a diligent ChatGPT/web-search workflow repeatedly finds;
- benchmark personas receive useful top-10 recommendations from a sufficiently complete candidate universe, with no known major eligibility/trust failures;
- #901's security and abuse-resistance gate passes or has only explicitly documented low-risk exceptions;
- external students can complete the core loop without explanation from the product owner;
- recommendation feedback is captured with minimal private data;
- recurring complaints become measurable product gaps;
- roadmap priorities change when real usage contradicts assumptions.

### Near-term direction

- Make #898's staged persona → independent external discovery → authoritative validation → frozen comparison → Yartchives comparison pipeline the immediate release-readiness priority, and close the largest systemic discovery/source-family gaps it exposes.
- Complete #901's security/abuse-resistance gate in parallel where it does not contend with coverage resources.
- Only after those gates are credible, run a small CS-student beta and compare whether students make better application decisions with Yartchives than with a reasonable ChatGPT/web-search workflow.
- Review Good / Bad suggestion feedback and observed friction.
- Convert repeated evidence into bounded roadmap-linked issues.
- Expand scope only after the CS-first trust bar is met.

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

Issue #507 completed the first implementation of capacity-aware evidence-backed task generation. The dispatcher now treats that as an ongoing operating capability: it selects existing eligible work first, then may use remaining Jules capacity for machine-verifiable non-overlapping work. It re-reads issue state between creations so dedupe and resource locks remain authoritative. Coverage is intentionally lane-based rather than globally capped: distinct ATS-family locks may run concurrently, and a completed family can generate another bounded issue after current-main evidence is re-measured. Zero generated work remains correct when no qualifying evidence exists.

## Relationship to older planning issues

Issue #18 contains valuable historical Apply Next product thinking and remains useful context, but this file is the durable cross-product roadmap going forward.

Issue #280 is historical beta-smoke context and is closed. Current release readiness is governed by #898 (trust/coverage/readiness) and #901 (security/abuse resistance).

Individual issues should reference the relevant roadmap track when practical, but the roadmap should not duplicate every open issue or become a manually maintained issue index.

## Review cadence

Update this file when one of these changes:

- the product thesis;
- the current phase;
- a durable roadmap outcome;
- the definition of success for a track;
- a major non-goal or product invariant.

Do not update it for every implementation detail, PR, or transient bug. Those belong in GitHub issues and code.
