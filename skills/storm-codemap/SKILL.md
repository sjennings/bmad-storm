---
name: storm-codemap
description: Produce or incrementally update an architectural map of the codebase on explicit invocation only, respecting existing project-context and AGENTS.md documentation ownership.
---

# Storm Codemap

Generate a navigable architectural map of the codebase — subsystems, entry points, dependency direction, and the contracts between them. Explicit invocation only: the codemap is never rebuilt automatically as a side effect of other work.

## Ownership rules (read first)

1. Existing project documentation is authoritative. Read `AGENTS.md`, project-context files, and architecture docs before mapping; the codemap **cites** them and must not contradict or duplicate them as a competing source of truth.
2. If the project already owns an architecture document, the codemap is either an update proposal for that document (through its owning workflow, e.g. `maintaining-project-context`) or a dated, clearly-labeled derived view — never a parallel authority.
3. Code and tests win over prose. Where the map and the code disagree, the map records what the code does and flags the doc drift.

## Procedure

1. Scope: whole-repo or a named subtree. Use `storm-explorer` lanes for large repos, each owning a disjoint subtree.
2. Capture per subsystem: purpose (one line), key files/symbols, inbound/outbound dependencies, invariants the code enforces, and test locations.
3. Record freshness: generation date and the commit the map was built from. A map without a freshness stamp is treated as stale.
4. Incremental updates map only the changed subtree plus its direct neighbors; note the delta in the map's change log section.

## Output

Write to the location the operator names (default: a dated section or file under the project's existing docs tree, behind the same ownership rules). Do not check the map into generated-artifact directories that other tooling owns.
