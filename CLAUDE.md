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
1  LLM Fundamentals        — prerequisite mechanics (tokens, context, sampling, model families)
2  RAG Fundamentals         — first real architecture: retrieval + grounding
3  AI Agents 101             — what an agent/tool is, the 4-step loop
4  Prompt Engineering        — step 2 of that loop, done properly
5  The Harness Pattern       — step 3–4 of that loop, formalized (2nd source diagram)
6  Implementing & Testing    — the harness, as real code
7  Evaluation Metrics        — is any of the above actually good?
8  Golden Datasets           — where the test cases in Ch.7 come from
9  Compliance Mapping        — EU AI Act / DORA / OWASP, mapped to Ch.7's metrics
10 CI/CD Quality Gates       — enforce Ch.7-9 automatically, pre-deploy
11 Observability             — the same questions as Ch.7, post-deploy, continuously
```

**Renumbering happened once already** (chapters were originally written 1–9 in build order: harness trio first, then RAG/eval/observability/golden/compliance/CI-CD as a second batch; then renumbered to the sequence above to match the roadmap image and to insert the two new foundational chapters). If another renumbering is ever needed: move every folder to a `tmp-` prefix first to avoid collisions, then to final names; then do a single-pass regex remap of `Chapter N` text mentions and relative-link folder names using an explicit old→new dict (not sequential chained replacements, which double-map); then manually fix any plural "Chapters N–M" range mentions, since a range in the old numbering usually isn't contiguous in the new one.

## Current status (check before assuming anything is stale)

- All 11 chapters are written and cross-linked correctly (verified: every relative link resolves, every Previous/Next pointer is consistent with the table in the README).
- Chapter 6's harness code is implemented and unit-tested — **8/8 pytest passing, actually run, not transcribed** — but **not yet wired into `portfolio-risk-evaluator`'s real `/review` endpoint**. That project's repo was empty on GitHub (`git ls-remote` returned nothing) the last time this was checked, so the wiring step is blocked on Fernando providing the real `main.py`/`schemas.py`, or doing the wiring himself against Chapter 6's `WIRING.md`-equivalent guidance.
- Chapters 2 and 7–10's content originated from Fernando's pre-existing guides (`llm-agentic-eval-guide.html`, `deepeval-ragas-guide.html`/`-v2.html`, `deepeval-metrics-guide.html`, `clinic-ai-testing/TESTING_AI_SYSTEMS.md`) — ported and reorganized, not written from scratch. If something in those chapters seems off or dated, the source-of-truth guides are the first place to check before assuming the port introduced an error.
- Chapters 1, 3 (partially — the "What is an agent/tool" sections), 4, 5, 6, and 11 are original to this notebook.

## Roadmap — queued, not yet written

See the README's "Roadmap — not yet written" section for the live list. As of this writing: LLM-as-judge selection in depth, drift detection tooling, agent framework comparison (LangGraph vs. AgentExecutor vs. CrewAI/AutoGen), and tool-calling mechanics (function-calling schemas, MCP) — that last one because the source roadmap image's "Tools / Actions" section was cut off in the screenshot and its content was never actually seen, so it shouldn't be invented.

## Working style Fernando expects (applies here same as everywhere)

- Opinionated recommendations he can react to, not menus of options.
- Direct pushback when a request's framing is off, with the reasoning shown — not silent compliance and not softened feedback.
- Don't fabricate confidence about unverified things (a trunk project's exact schema, a source image's cut-off content, a claim about what's "already been tested" without actually running it).
- Search this repo's own project knowledge / existing guides before writing new theory content — porting and reorganizing existing, already-good material beats regenerating it from scratch.

## Practical: no push access

Whoever/whatever is working on this repo in a sandboxed tool environment (this includes Claude via chat) typically has no push credentials for `github.com/fgmartinez/qa-agentic-theory`. The working pattern has been: build and verify locally, package as a tarball, hand it to Fernando with exact `git add / commit / push` commands to run himself. Don't assume a `git push` will succeed — check, and fall back to that pattern if it doesn't.
