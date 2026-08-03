# Storm / BMAD / Linear orchestration rules

Storm is a project-local compatibility layer for an already-installed OMO-Slim. It is not an installer, provider configuration, or replacement for native BMAD workflows.

- Before publication, BMAD is authoritative for scope, requirements, acceptance criteria, and the current specification. Keep BMAD workflows canonical and use their native update paths.
- After publication, Linear is authoritative for execution state, ownership, and progress. Authenticated `linear-cli` 0.3.27 or later is required and assumed to be available.
- Every tracker mutation goes through the project `storm-linear` skill. Use its verified CLI commands; never invent a second tracker path.
- Only the coordinator/orchestrator may mutate tracker state. Specialists may report findings and proposed changes, but must hand tracker mutations back to the coordinator.
- If BMAD and Linear authority is ambiguous, stop and ask the operator; do not guess or silently reconcile the records.
- After any BMAD update, run `storm-setup check` before continuing.

This append does not install the CLI or configure credentials, providers, or secrets. It assumes an existing authenticated `linear-cli` supplied by the consuming project.
