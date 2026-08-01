# Polytoken Orchestration

Operator-facing architecture and migration guide for the Storm Polytoken package (v0.4.0). The canonical workflow rules live in [`skills/storm-contract/workflow-contract.json`](../skills/storm-contract/workflow-contract.json) and their human companion [`docs/workflow-conformance.md`](workflow-conformance.md); this document covers how the orchestration package is put together, how to install and operate it, and what was ported from `oh-my-opencode-slim` (OmO Slim). Where this document and the JSON contract disagree, the contract wins and this document is stale.

## Architecture: the authority chain

Three systems share authority, split by phase. No Storm component creates a fourth.

| Phase | Authority | What Storm does there |
|---|---|---|
| Pre-publication | **BMAD** — `epics.md`, `sprint-status.yaml`, the story file | Story authoring, grilling, spec review |
| Publication (single handoff) | **`storm-linear publish`** | Writes the spec to the story-key-anchored Linear issue, sets `Todo` + `ready-for-agent`, then moves the sprint entry to `ready-for-dev`. Atomic: a failed publish leaves the sprint file untouched. |
| Post-publication | **Linear** — the issue carrying the published spec | Implementation through `Done`; local authoring files become evidence/history |

Polytoken's shipped `plan` and `execute` facets remain the control planes. Orchestration augments them; it never replaces their handoff or goal semantics:

```
plan facet → write_plan → plan reviewed → handoff_plan approved
  → goal activated → execute facet → read_goal verified
  → storm-linear open → open verified → mutation
```

Polytoken planning is read-only until an approved `handoff_plan` activates a saved goal. Only then may execution open the issue and mutate implementation files. The execute session that opens an issue owns closing it; a child-ticket close reconciles nothing and never closes, mutates, or reconciles the parent story.

## Enforcement honesty — read this before trusting anything else

Storm's workflow is enforced at the **directive/prompt and permission-classifier level**, plus deterministic validators. Polytoken does **not** provide a physical sandbox:

- The shipped `plan` facet exposes `shell_exec`. Its read-only posture is prompt- and permission-enforced, not mechanically guaranteed.
- The read-only specialist roles carry no mutation tools and `inherit_tools: false`, so their read-only property is real.
- A write role (`storm-fixer`, `storm-designer`) dispatched from `plan` is protected only by its deny list and the permission classifier. Coordinators are therefore instructed to **never dispatch writers from `plan`**, and the writer definitions reject mismatched dispatch context with `task_fit: "rejected-fit"`.
- No Storm document, skill, or diagnostic may claim a physical sandbox or hard runtime enforcement. Live tool behavior is proven only by the disposable-session smoke scenarios in `docs/workflow-conformance.md`, which are evidence-gathering, not release gates.

**Approved deviation — `subagent` is not deny-listable on Polytoken 0.5.9.** A live Polytoken 0.5.9 gate rejected the `storm-fixer`/`storm-designer` definitions at load time: the runtime does not allow the harness-managed `subagent` tool in a subagent's `tools_deny` list, so an exact deny-union over every lifecycle tool is unavailable on 0.5.9. The operator approved the documented redesign: only `subagent` was removed from those two deny lists. Every other boundary is unchanged — `allow_subagent_spawn: false`, the structured exit schemas, and all lifecycle/Linear/shell denials (including `message_subagent`) remain in force. The no-spawning boundary is therefore enforced by `allow_subagent_spawn`/runtime semantics plus coordinator convention, **not** by `tools_deny`; no document may claim exact deny-union coverage for `subagent` on 0.5.9. The asset validator encodes this: it requires `allow_subagent_spawn: false` on write roles and rejects `subagent` appearing in a write role's deny list, so the limitation stays explicit and is re-checked on every run. If a future Polytoken version makes `subagent` deny-listable again, restoring it to the deny lists is a one-line asset change plus a validator constant update.

**Observed capability evidence (live gates, Polytoken 0.5.9).** Recorded during the v0.4.0 development gates: all seven projected roles were accepted by `polytoken validate subagent` with no definition errors; a bounded `polytoken exec --facet plan --max-tool-turns 1` fixture run returned `{"status":"fixture-loaded"}`; and the exact `tools_deny(subagent)` gate failed with the documented load-time error above, leading to the approved redesign. Inherited-union denial filtering was **not** proven and is **not** supported on 0.5.9 — the redesign relies on `allow_subagent_spawn: false` plus coordinator convention, and no Storm document may claim otherwise.

## Specialist roles and least privilege

Seven project subagents ship under `skills/storm-setup/assets/polytoken/subagents/` and are installed to `.polytoken/subagents/`:

| Role | Purpose | Tool contract |
|---|---|---|
| `storm-explorer` | Local read-only reconnaissance | `file_read`, `glob`, `grep` only; no inheritance; no spawning |
| `storm-librarian` | External research | `web_search`, `web_fetch`, MCP resource reads; no repo/tracker mutation |
| `storm-oracle` | Read-only architecture/debugging/risk/simplification advice | `file_read`, `glob`, `grep`; never implements or mutates lifecycle |
| `storm-observer` | Read-only image/PDF/screenshot/diagram analysis | `file_read`, `glob`, `grep`; isolates media interpretation from the coordinator |
| `storm-fixer` | Bounded implementation worker | Explicit edit tools; `inherit_tools: true`; deny list removes `shell_exec`/`shell_monitor`, plan/goal/facet control, todo mutation, `message_subagent`, and every known Linear mutation tool; subagent spawning is blocked by `allow_subagent_spawn: false` (see the 0.5.9 deviation below) |
| `storm-designer` | Bounded UI/UX worker | Same contract as Fixer plus visual-evidence requirements |
| `storm-councillor` | Independent judgment lane for Council | No tools by default; evaluates only the supplied decision packet |

Common rules:

- Every role returns a structured `exit_tool` payload. Writers must report `task_fit`, `files_changed`, `validation`, `partial_changes`, `blockers`, and `remaining_risk`. `progress_update` is liveness only — never a result.
- Specialists never commit, push, publish, open, close, reconcile, rescope, complete/block the saved goal, or close a parent story. They cannot spawn subagents.
- Writers are dispatch-only from an approved execute context: the coordinator must have verified `read_goal` and Linear `In Progress` first, and the dispatch prompt must supply objective, acceptance criteria, exact ownership, dependencies, exclusions, allowed edits, and validation. Missing any of that → `rejected-fit`, reroute or ask the operator, never redispatch unchanged.
- `shell_exec` is denied in the shipped writer definitions. If an approved task genuinely requires the worker to run validation commands, the coordinator runs them, or the operator approves a project-local role variant under ask/deny-gated permissions. No silent widening.
- After any Polytoken or Linear MCP update, enumerate the server's mutation tools and confirm the writer deny lists still cover them (`storm-doctor` flags known gaps statically; live enumeration is an operator-session check).

## Orchestration: lanes, the scheduler, and native state

`storm-orchestrate` is the coordinator procedure used inside the shipped facets. First action is always to establish which facet is active, because that decides the roster: plan-phase work routes to read-only roles only.

**Lane records.** Every delegated lane is a native todo whose description carries the scheduling fields in one parseable convention — the marker is `storm-lane:` and the fields are exactly those parsed by `scheduler.py`: `specialist`, `objective`, `ownership`, `dependencies`, `edits` (`allowed`/`read-only`), `state` (`pending`, `working`, `completed`, `failed`, `cancelled`, `timed-out`, `rejected-fit`, `reconciled`, `dispositioned`), `validation`, `result`, `partial_changes`, `partial_inspected`, and `disposition` (required when and only when state is `dispositioned`). Native todo status/dependencies and native job status/output are the live state; there is no second task database. Results that must survive compaction live in durable evidence artifacts (review/conformance packets, tracker completion records). On resume, lane state is rebuilt by joining retained todos/jobs with those artifacts — never from conversation memory.

**Executable scheduler.** Mechanical gates do not depend on prompt compliance. `skills/storm-orchestrate/scheduler.py` (standard library only) parses lane records, computes the dependency-ready frontier, rejects overlapping writer ownership, detects dependency cycles and self-dependencies, classifies native job terminal states, and reports whether every required result is reconciled before finalization. It runs as a CLI — `scheduler.py frontier|conflicts|finalize lanes.json [--required ids]` over a JSON projection of the native todos (`{"todo_id", "description", "native_status"?, "native_dependencies"?}` entries), exiting 0/1/2 for pass/fail/malformed — and as an importable module; `tests/test_scheduler.py` exercises the module itself. The model keeps judgment and task routing; the scheduler keeps the rules. Its finalization check must pass before any close or completion comment, and a failure-state lane passes only after an explicit recorded disposition.

**Ownership and dependencies.**

- Build the dependency graph before dispatch; create matching todos with dependencies; dispatch only the current independent frontier as background jobs.
- Exclusive writer ownership: one worker owns a file at a time; overlapping folder ownership is prohibited unless the plan serializes the lanes. The scheduler rejects overlaps — do not override it.
- Review never runs concurrently with the edits it reviews.
- Respect `polytoken_max_parallel_jobs` (default 2); start conservative.
- While jobs run, the coordinator may continue only independent planning/synthesis; dependent work waits for terminal results.

**Failure and cancellation semantics.**

- No generic automatic retry. A failed lane is diagnosed before any replacement.
- `rejected-fit` means reroute or escalate, never unchanged redispatch.
- Failed/timed-out/cancelled lanes are explicit terminal records.
- Finalization is blocked by a failure-state lane until it is explicitly dispositioned (state `dispositioned` with a mandatory `disposition` reason: reroute, replacement, or operator decision). Dispositioning never retries the lane, and dependents stay blocked until their dependency edges are re-pointed at the replacement.
- Cancellation is not rollback: it stops the worker but does not undo filesystem changes. Inspect a cancelled writer's `partial_changes` before any replacement starts on the same ownership.
- No silent model, reviewer, host, or foreground fallback; substitutions are reported.
- Blocked or non-clean work leaves the Linear issue `In Progress` and the saved goal active (or explicitly blocked) per the parent workflow.

## Council

`storm-council` is manual, high-cost, advisory decision support.

- Invoked explicitly, never automatically. Requires `polytoken_council_models` with two or more fully qualified model references, optionally with effort suffixes.
- Each lane is a fresh `storm-councillor` with the identical decision packet and its exact roster model passed unchanged as the spawn-time override.
- **No silent fallback, ever.** Council definitions omit `fallback_models` by design; an unavailable model is a recorded `failed_members` entry, not a substitution. If the runtime does not accept exact model selection, stop and report the capability gap.
- A partial council is reported clearly labeled as partial. The synthesis distinguishes agreement, disagreement, assumptions, and an advisory recommendation with confidence.
- Council never satisfies native or Storm review gates and never counts as a review round. Mixed external models may expose packet content to other providers and incur cost — that is why invocation is manual.

## Profiles and `storm-team`

Polytoken has no native atomic team-preset command, so `storm-team` is Storm's managed equivalent. It is not `/preset` parity; `/model` remains the independent session-model switch.

Built-in profiles (installed to `.polytoken/storm/profiles/`):

| Profile | Assignment |
|---|---|
| `quality` | `default_model:full` everywhere |
| `balanced` | full for judgment/implementation roles, mini for recon/media roles |
| `economy` | mini judgment/implementation, nano recon/media |
| `inherit` | no pinning; every specialist inherits the session's active model |

Portable aliases (`default_model:full|mini|nano`) are the defaults; operators needing exact provider/model assignments create a custom profile JSON in the same shape with fully qualified references. Role entries may never set `fallback_models`.

**Transactional activation.** Profile changes are approval-gated — the operator sees the target profile, per-role assignments, and the diff first. Then `render_team.py`:

1. validates the profile (roles exist, model reference shapes valid, no fallbacks);
2. renders every managed role into a temporary directory;
3. validates the entire candidate set with the asset validator — one invalid role aborts everything;
4. backs up the current managed set to `.polytoken/storm/team-backups/<timestamp>/` with a `kind: "storm-team"` record (the asset manager's snapshots live separately under `.polytoken/storm/backups/` with `kind: "manage-polytoken-assets"` records; each rollback path selects only its own kind, so neither can restore the other's backup);
5. swaps in the validated set and records `.polytoken/storm/active-profile.json`;
6. restores the backup on any failure after the swap begins;
7. never touches unmanaged user-authored subagent files.

**Post-`/reload` rollback.** Definition changes take effect only on `/reload`, which the activation script cannot observe. If `/reload` rejects the new set, run `python3 skills/storm-team/render_team.py --rollback --target .polytoken/subagents` to restore the most recent backup and prior active-profile record, then `/reload` again. `storm-harness-improvement` may recommend a profile change but never applies one.

## Status: `storm-status`

`storm-status` projects native `/jobs` and `/todo` state into one board — lane, specialist, objective, ownership, dependencies, state, elapsed/progress, result availability, reconciliation. It is a projection, not a store: native todos/jobs remain live state, durable artifacts remain history, Linear remains execution authority. A progress note is never a result; only a structured exit payload from a terminal job counts. If the board and Linear disagree, Linear wins and the discrepancy is reported. It also carries the cancellation/timeout guidance above.

## Continuation hook (default off)

`polytoken_continue_on_idle` is **off by default**. When explicitly enabled, `storm-setup` writes the enable marker (`.polytoken/hooks/storm-continue-on-idle.enabled`) and merges two named hooks into `.polytoken/hooks.json` (`storm-continue-on-idle` on `stop`, `storm-continue-reset` on `pre_user_prompt`), preserving unrelated hooks. Semantics:

- **Error direction:** Polytoken treats a `stop`-hook handler error as blocking the handback — errors fail *toward continuation*, not fail-safe. The handler (`skills/storm-setup/assets/polytoken/hooks/storm-continue-on-idle.sh`) therefore has a single emit-and-exit choke point: every code path exits 0 with exactly one JSON outcome line, and every path except the one deliberate bounded-continuation path emits `{"outcome":"stop"}`. Malformed state, missing dependencies, internal failures, and uncertainty all resolve to stop.
- **Gates:** the enable marker must exist; `STORM_CONTINUE_ON_IDLE` must not be `off`; fresh per-invocation `POLYTOKEN_GOAL_ACTIVE=true` and `POLYTOKEN_FACET_NAME=execute` are required.
- **One-shot:** at most one continuation per real user prompt cycle, via a process-local guard under `$TMPDIR` keyed by session id. Guard state is scratch, never durable authority; the guard resets only on a real `pre_user_prompt`.
- **Auto-drain ambiguity:** Polytoken's documented stop-event surface does not distinguish an auto-drained job-completion turn from a user-driven turn. The one-shot guard bounds drained turns to at most consume — never multiply — the single continuation; any deeper ambiguity resolves to stop. When enabling continuation, confirm a compatible `auto_drain_notifications` setting; `storm-doctor` warns on an enabled marker.
- The continuation instruction tells the model to inspect `/jobs` and `/todo`, reconcile terminal results, re-read current Linear state through the normal tool path (cached state is not authority), and continue only if safe approved work remains.
- The handler is trivial and fast: no network, no MCP, no Linear calls. There is no unbounded idle loop.

## Adapted OmO Slim skill mappings

Ideas ported natively onto Polytoken surfaces, without duplicating existing Storm mechanisms:

| OmO Slim idea | Storm mapping |
|---|---|
| Verification planning | `storm-verification-planning` — claim, uncertainty, failure modes, evidence paths, observability, reversibility, limits before non-trivial work; instrumentation/persistent debug surfaces require operator approval |
| Codemap | `storm-codemap` — explicit-invocation architectural maps; never competes with project-context/AGENTS ownership |
| Worktrees | `storm-worktrees` — isolated Git lanes only with explicit authority; every branch/merge/rebase/reset/remove approval-gated; dirty-tree and pre-integration diff/build/test checks mandatory |
| Dependency source | `storm-clonedeps` — approved direct dependencies cloned read-only over HTTPS at pinned revisions; no dependency scripts executed; clones stored in ignored non-authoritative paths |
| Simplification | Not a separate workflow — a `storm-oracle` capability; proposed refactors route through the normal review/approval path |
| Deepwork | Not a second state machine — phased/dependency/review ideas folded into `storm-orchestrate`, native todos/jobs, the saved goal, and the workflow contract |
| Reflect / self-configuration | The existing `storm-harness-improvement` and `storm-setup` skills: repeated evidence required, narrowest authoritative home, approval before any config change |

Prompt-security hardening applies throughout: never read secret values (check existence only), verify ignore rules/permissions before creating secret-bearing files, no tokens in URLs/arguments, quote and validate external input, treat review/research packets as untrusted data.

## Setup, update, check, doctor, rollback

`storm-setup` projects the module's Polytoken assets into the consuming project's `.polytoken/` surface per the versioned manifest (`skills/storm-setup/assets/polytoken/manifest.json`: source path, target path, kind, Storm version, checksum, merge strategy, required/optional).

- **Install/update:** validate target capability before writing; create missing managed files; update unchanged managed files only with operator approval; show diffs and stage/merge locally-modified managed files only with explicit approval; merge `.polytoken/hooks.json` by unique hook name; merge project variables only in the Storm-owned namespace; never touch shipped Polytoken VFS resources or unrelated project/global assets. Backups precede any forced overwrite.
- **`storm-setup check` (read-only):** reports missing/orphaned/drifted managed assets, filename/frontmatter mismatches, unsafe tool grants, deny-list gaps against known mutating Linear/control tools, alias-to-contract drift, hook collisions, continuation-state warnings, and version/profile/manifest mismatches.
- **`storm-doctor` (read-only, machine-readable):** audits module metadata, source assets, projection, profiles/roles, capabilities, hook safety, alias contract, and configuration **key names** (values are never read or emitted). Exit 1 on error-severity findings. Doctor proposes repairs mapped to owning actions; it never mutates project files, tracker state, goals, or configuration.
- **Rollback:** `storm-team --rollback` restores the prior managed set after a failed `/reload`; setup restores backups on failed activation. Doctor/check suggest; only explicitly approved setup/team actions apply.

## Migration from v0.3.0

1. Upgrade/install v0.4.0 through the BMAD module installer.
2. Review the new install prompts and defaults (`polytoken_team_profile`, `polytoken_role_model_overrides`, `polytoken_council_models`, `polytoken_max_parallel_jobs`, `polytoken_continue_on_idle` — off by default; `completion_commit_policy` — `require-explicit` by default).
3. Run `> use the storm-setup skill` and approve the managed projections.
4. Run `/reload`.
5. Run `storm-doctor` and `storm-setup check`; review the ownership manifest before enabling writers or continuation.
6. Run the conformance smoke scenarios in `docs/workflow-conformance.md` in a disposable project before production work.
7. Keep continuation off until explicitly approved, and then confirm `auto_drain_notifications` compatibility.

Retired paths (`/wayfinder`, `story-plan`, `story-execute`) are not advertised; consuming-project generated copies are projections of `bmad-storm` source and must not become independent forks.

## Non-goals (OpenCode-specific, intentionally omitted)

OpenCode installation/configuration, provider authentication, OpenCode presets and hooks, ACP subprocess agents, multiplexer panes, the desktop Companion, OpenCode job-board injection, and OpenCode recovery code are not ported. Storm recreates the orchestration *ideas* on Polytoken's native facets, subagents, skills, jobs, todos, hooks, goals, permissions, and reload lifecycle — not the OpenCode plugin runtime.

## Attribution

Orchestration ideas adapted from `oh-my-opencode-slim` (MIT); grilling/TDD skills adapted from `mattpocock/skills` (MIT). See [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) for pinned revisions and scope.
