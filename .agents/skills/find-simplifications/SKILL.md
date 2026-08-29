---
name: find-simplifications
description: Find evidence-backed simplifications at an explicit maintenance request or milestone, and record durable proposals as Agent Notes without changing behavior opportunistically.
---

# Find Simplifications

Use this DeepSeek Harness-derived skill for a deliberate simplification survey, not as the behavior-preserving cleanup after every code task. Routine current-diff cleanup belongs to `code-simplifier`.

Read root `AGENTS.md`, and the architecture.

## Strong candidates

A strong candidate removes or collapses real cost and has verified evidence:

- a public method, option, event, helper, package, or FHIR capability has no production consumer;
- tests or docs are its only consumers and no current contract requires it;
- two stores, projections, or status fields represent the same authoritative fact;
- a shared abstraction has only one real adapter or consumer;
- transport, FHIR Operation, UI, or Agent tools duplicate a Command state machine;
- Web/Desktop/Mobile sharing pulls platform code across an established boundary;
- a compatibility, rollback, validation, or test path protects an unused API;
- maintained platform or dependency functionality can replace hand-rolled code with meaningful net deletion.

Do not propose removing FHIR R5 constraints, runtime validation at trust boundaries, synthetic-data protections, audit and idempotency controls, platform separation, or an Agent Note decision without evidence that defeats its rationale.

## Prove or reject

1. Search exact symbols, wire strings, exports, routes, schema fields, and configuration keys with `rg`.
2. Classify production consumers separately from tests, docs, fixtures, demos, and generated output. Inspect dynamic registrations and runtime entry paths before declaring a symbol unused.
3. Trace ownership, failure, persistence, and external compatibility. A caller proves use, not that the current public abstraction is the right owner.
4. For a dependency replacement, compare covered behavior, maintenance, transitive cost, residual glue, removed tests, and net deletion.
5. Reject candidates that only relocate complexity, contradict a current consumer, or require unrelated churn without reducing behavior or surface.

Prefer a few proven candidates over a broad inventory of guesses. A small local cleanup can use a scoped `TODO`, `FIXME`, or direct issue; a decision with real alternatives, consequences, and future re-litigation risk uses one proposed Agent Note under `.agents/notes/proposed/{class}/`.
