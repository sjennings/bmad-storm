# Panel protocol — shared by storm-spec-review and storm-cross-review

The panel engine runs two tiers of reviewers over a self-contained packet, merges their findings, and presents a single triage. The two review skills differ only in what goes into the packet and which lenses run.

## 1. Assemble the packet

Write a single self-contained markdown file to `{implementation_artifacts}/storm-reviews/<slug>-packet.md`. It must be reviewable by a process with **no repo access and no conversation context**. Include, per the calling skill's packet spec: the artifact under review (spec text, or diff), the acceptance criteria and story scope, glossary excerpts for every domain term used, the project invariants relevant to the touched area (from the root and per-subtree contract files), and the review instructions. Nothing else — a bloated packet degrades every reviewer at once.

## 2. Tier 1 — context-free subagent lenses (same model, automatic)

Launch parallel subagents with **no prior conversation context**, one per lens the calling skill names. Lenses reuse BMAD's own review machinery where it exists (`bmad-review` with a single lens: `adversarial`, `edge-case-hunter`, `verification-gap`) plus any skill-specific lenses defined by the caller. Each subagent receives the packet (or the packet subset its lens specifies) and must return findings in the standard format below. Adversarial doctrine applies: the reviewer must find issues; zero findings triggers one re-analysis pass or an explicit justification.

## 3. Tier 2 — external-model reviewers (cross-model)

Read `external_reviewers` from `{project-root}/_bmad/storm/config.yaml` (comma-separated CLI names). For each reviewer, invoke it **non-interactively** with the packet and capture output to `{implementation_artifacts}/storm-reviews/<slug>-<reviewer>.md`. Known invocations:

| Reviewer | Invocation |
|---|---|
| `codex` | `codex exec "$(cat <packet>)" ` — or `codex exec "Review the file <packet> per its instructions"` when file access is available |
| `opencode` | `opencode run "Review the file <packet> per its instructions. Output findings only."` |
| `gemini` | `gemini -p "Review the file <packet> per its instructions. Output findings only."` |
| anything else | `<name> <packet>` — treat the config value as a command that takes the packet path |

**Failure handling:** a reviewer whose CLI is missing, unauthenticated, times out (10 min), or returns empty output is recorded in `failed_reviewers` and skipped. Report skipped reviewers to the operator prominently — a panel that silently shrank is worse than a small panel. Never let one reviewer's failure fail the review step.

## 4. Findings format (all reviewers)

Each finding: severity (`HIGH`/`MEDIUM`/`LOW`), one-line title, location (file:line for code; section for specs), evidence, and — for spec reviews — which acceptance criterion or invariant it implicates. Prose preambles are discarded at merge.

## 5. Merge and triage

1. Collect all findings; tag each with its source (lens or reviewer name).
2. Dedupe: findings pointing at the same location and defect merge into one entry listing all sources. **A finding surfaced independently by multiple model families is high-signal — rank it up.**
3. Present the merged list to the operator ranked by severity then source-count, in `bmad-code-review`'s triage format so downstream handling is identical for both native and panel findings.
4. The operator (or the calling workflow's triage step) disposes of each finding: fix, or record an explicit rebuttal with the reason. Expect false positives — adversarial reviewers are instructed to find problems; the human filters.

## 6. Loop discipline

After fixes, re-run per the calling skill's loop rule, up to `review_loop_max_rounds` (config). Each re-run is a **complete fresh pass over the fixed artifact** — not a spot-check of prior findings. Exit when a full pass returns no actionable findings; if rounds exhaust without convergence, or a finding needs a decision beyond the current scope, halt and report the outstanding findings to the operator rather than looping further.
