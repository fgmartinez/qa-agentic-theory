# CLAUDE.md

Read this before doing anything else in this repo. It exists so a new conversation — chat, Claude Code, whatever — doesn't need Fernando to re-explain the project from zero.

## What this repo is

`qa-agentic-theory` is a theory notebook, not a shipping product. Its entire purpose is to be the place where an AI Quality Engineering concept gets learned and worked through *once, completely*, before any code touching it lands in a trunk (portfolio) project. See the root [`README.md`](./README.md) for the chapter list and reading paths — this file is about *how to work on the repo*, not what's in it.

## The non-negotiable rule this repo exists to serve

**No rework in trunk projects.** Fernando's own stated principle: rewriting code in a trunk project (`portfolio-risk-evaluator`, `fintech-support-ai-evaluator`) is expensive — those repos are meant to be interview-defensible, coherent histories, not scratch pads. This repo is the scratch pad instead. The workflow, every time:

1. A topic needs to be learned or a design needs to be worked out.
2. It gets a chapter here — theory, worked examples, code if applicable — until it's *right*, not just *written*.
3. Only then does the corresponding piece land in a trunk project, usually as a small drop-in package plus a short wiring note.

If a request comes in that would add half-finished or exploratory code directly to a trunk project instead of working it out here first, that's worth flagging back to Fernando, not just doing.

## Chapter conventions — follow these exactly for any new chapter

- **Folder**: `NN-kebab-case-slug/`, two-digit zero-padded number, matching its position in the reading order (not necessarily the order it was written in — see "Renumbering" below).
- **File**: chapter content lives in `NN-slug/README.md`. If a chapter ships code, the code lives in `NN-slug/<real project structure>` (e.g. `06-implementing-and-testing-the-harness/app/harness/`), runnable standalone from inside that folder.
- **Header line** (line 3, after the H1 and a blank line): always `*Part of [qa-agentic-theory](../README.md). Previous: [Chapter N-1 — Title](../NN-slug/README.md). Next: [Chapter N+1 — Title](../NN-slug/README.md).*` — first chapter has no Previous, last chapter has no Next (say so explicitly instead of omitting silently).
- **Closing `## Next` section**: every chapter (except the last) ends with a short paragraph and a link into the next chapter, framed as *why* that's the next thing, not just *that* it's next.
- **Self-contained means self-contained**: a chapter should teach its topic completely enough that reading only that file — no other chapter open — is enough to understand and apply it. Cross-references to other chapters are for *depth*, not for load-bearing definitions the reader can't do without.
- **Language**: English only, no exceptions — this is publishable portfolio material.
- **Tie to the trunk projects**: every chapter should end up connected to `portfolio-risk-evaluator` and/or `fintech-support-ai-evaluator`/`clinic-ai-testing` concretely, not just in the abstract. A chapter that never touches what's actually being built is a chapter that drifts from the point of the repo.
- **Don't invent what isn't verified.** If a claim needs a fact from a trunk project's actual code (a schema field name, a real test count) and that code isn't available to check, say so explicitly and give the reader an adapter/placeholder instead of a plausible-sounding guess. This repo has done this before (Chapter 6's `WIRING.md`-equivalent section) — it's the standard to hold to, not an exception.

## Chapter order — why it's what it is

The order follows a public AI Agents learning roadmap end to end (archived as `images/ai-agents-roadmap.png`), not the order chapters happened to get written in:

```
1  LLM Fundamentals          — prerequisite mechanics (tokens, context, sampling, model families)
2  RAG Fundamentals          — first real architecture: retrieval + grounding
3  AI Agents 101             — what an agent/tool is, the 4-step loop
4  Prompt Engineering        — step 2 of that loop, done properly
5  The Harness Pattern       — step 3–4 of that loop, formalized (2nd source diagram)
6  Implementing & Testing    — the harness, as a real backend service
7  Tool Calling & Schemas    — how a call is described and emitted (the other half of tool use)
8  Evaluation Metrics        — is any of the above actually good?
9  Golden Datasets           — where the test cases in Ch.8 come from
10 Compliance Mapping        — EU AI Act / DORA / OWASP, mapped to Ch.8's metrics
11 CI/CD Quality Gates       — enforce Ch.8-10 automatically, pre-deploy
12 Observability             — the same questions as Ch.8, post-deploy, continuously
```

**Renumbering has happened twice.** First: chapters were originally written 1–9 in build order, then renumbered to match the roadmap image and insert two foundational chapters. Second: Chapter 7 (Tool Calling) was inserted, shifting old 7–11 to 8–12.

The procedure that worked both times, and should be reused: move every folder to a `tmp-` prefix first to avoid collisions, then to final names; then do a **single-pass** regex remap of `Chapter N` mentions and relative-link folder names using an explicit old→new dict (**not** sequential chained replacements, which double-map: 7→8, then that 8→9); exclude any file already authored in the new numbering; then manually fix plural "Chapters N–M" ranges, since a range in the old numbering usually isn't contiguous in the new one. The second renumber touched 17 files automatically and needed 4 manual range fixes.

## Textbook conventions (added in the study-book pass)

The repo is now a **study textbook**, not a summary notebook. Anything new must match:

- **Every chapter ends with `## Exercises` then `## Interview preparation`**, before `## Next`. Exercises use `<details><summary>Solution</summary>` so the reader can attempt first. Solutions explain the *reasoning*, and where possible name the second, non-obvious point the surface answer misses.
- **Interview answers are written as spoken answers** — first person, concrete, naming a trade-off. Not definitions.
- **Chapters with a hard concept get a `## Worked example`** with real numbers or a real trace, placed before the exercises.
- **Verified, not transcribed.** Test counts and command output in a chapter must come from an actual run. Chapter 6's 112 and Chapter 7's 27 were both run; the `uvicorn` transcript and the JSON log lines in Chapter 6 are real captured output.
- Front matter: [`STUDY-GUIDE.md`](./STUDY-GUIDE.md), [`GLOSSARY.md`](./GLOSSARY.md), [`CAPSTONE.md`](./CAPSTONE.md). Adding a chapter means adding its terms to the glossary and, if it changes the reading order, updating the study guide's paths.

## Current status (check before assuming anything is stale)

- **All 12 chapters written**, cross-linked, each with exercises + interview sections. Every relative link and Previous/Next pointer verified resolving.
- **Chapter 6 is now a full backend service, not the original four-file module.** FastAPI app (`/health`, `/rules`, `/review`), Pydantic schemas with a closed `RuleId`, a decision layer (`RuleBasedDecisionEngine` + `LLMDecisionEngine` with grounding validation + `OllamaClient`), and the harness proper: intent-derived idempotency keys, a pure resolver, a separate `Corrector`, and a **bounded ACT→OBSERVE→CORRECT loop**. **112 tests passing, actually run.** Service verified booting under `uvicorn` with real curl requests.
  - The original version had a genuine hole worth remembering: the resolver returned `RETRY`/`CORRECT` and **nothing ever retried or corrected** — the loop did not exist. ADR-003 in that chapter records the fix.
- **Chapter 7 is new** and ships a tool-calling toolkit: a registry deriving JSON Schema from type hints (both OpenAI and Anthropic dialects) and a validating dispatcher. **27 tests passing.**
- **`portfolio-risk-evaluator` has now been read** (`4a10109`, Days 1–3 done, 54 tests passing, `/review` still 501, `src/agent/` empty) — and it invalidated a claim this notebook had carried since Chapter 5 was written.

  **The harness does not drop into that project.** It is a *review* system: `ReviewAction` is `auto_approve` / `secondary_review` / `escalate_immediate`, `ReviewDecision` carries no amount, there is no payment gateway, and its own `CLAUDE.md` forbids connecting one. Nothing for the executor to execute. What transfers is the **resolver** half — `compute_risk_level(triggers) -> RiskLevel` is already a resolver in Chapter 6's sense. The executor belongs to `fintech-support-ai-evaluator`. Full reconciliation in [`WIRING.md`](./06-implementing-and-testing-the-harness/WIRING.md).

  Two consequences for future work: **do not copy `app/harness/` into that repo** (an unused abstraction is worse than none), and **do not rename Chapter 6's schemas to match** — they are teaching schemas for a refund domain, correctly labelled as such.

- **Working in `portfolio-risk-evaluator` is governed by that repo's own `CLAUDE.md`, not this one.** It is explicit and it documents a time the rule was already broken: smallest reviewable increment, explain before implementing, let Fernando write the first attempt at core learning-relevant logic (rule conditions, agent nodes, graph edges). Writing a whole layer unattended there is the specific failure it warns against — do not repeat it, even when this notebook has the answer ready.
- Chapters 2 and 8–11's content originated from Fernando's pre-existing guides (`llm-agentic-eval-guide.html`, `deepeval-ragas-guide.html`/`-v2.html`, `deepeval-metrics-guide.html`, `clinic-ai-testing/TESTING_AI_SYSTEMS.md`) — ported, reorganized, then extended with worked examples and exercises. If something there seems off or dated, check the source guides before assuming the port introduced an error.
- Chapters 1, 3, 4, 5, 6, 7, and 12 are original to this notebook.

## Roadmap — queued, not yet written

See the README's "Roadmap — not yet written" section for the live list. As of this writing: LLM-as-judge selection in depth, drift detection tooling, agent framework comparison (LangGraph vs. AgentExecutor vs. CrewAI/AutoGen), and **persistence + the outbox pattern** — that last one because Chapter 6's design *observes* the "rail confirmed but our state didn't persist" failure (`APPROVED` + `not state_persisted` → `ESCALATE`) but cannot yet prevent it.

Tool-calling mechanics came off this list — it is now Chapter 7. Note the source roadmap image's "Tools / Actions" section was cut off in the screenshot and was never actually seen, so that chapter was written from primary knowledge of how the APIs work rather than from the image; it should not be presented as following that diagram.

## Working style Fernando expects (applies here same as everywhere)

- Opinionated recommendations he can react to, not menus of options.
- Direct pushback when a request's framing is off, with the reasoning shown — not silent compliance and not softened feedback.
- Don't fabricate confidence about unverified things (a trunk project's exact schema, a source image's cut-off content, a claim about what's "already been tested" without actually running it).
- Search this repo's own project knowledge / existing guides before writing new theory content — porting and reorganizing existing, already-good material beats regenerating it from scratch.

## Practical: no push access

Whoever/whatever is working on this repo in a sandboxed tool environment (this includes Claude via chat) typically has no push credentials for `github.com/fgmartinez/qa-agentic-theory`. The working pattern has been: build and verify locally, package as a tarball, hand it to Fernando with exact `git add / commit / push` commands to run himself. Don't assume a `git push` will succeed — check, and fall back to that pattern if it doesn't.
