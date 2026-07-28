---
name: storm-harness-improvement
description: Bounded loop for improving agent instructions, skills, tools, or checks after a trajectory exposes avoidable friction, plus the rules for promoting a trajectory lesson into a durable repository home. Use when an implementation or verification run hit avoidable agent friction and you are deciding whether to change CLAUDE.md, a skill, a storm override, a tool, a test, an ADR, or deferred-work.md.
---

# Harness improvement

## Improvement loop

When an implementation or verification trajectory exposes avoidable agent friction, improve the environment through this bounded loop rather than adding generic advice:

```text
baseline → earliest failed handoff → smallest owning intervention
→ native verification → fresh equivalent rerun → retain, revise, or remove
```

Before changing instructions, skills, tools, or checks, record the bounded job, target revision, accepted outcome, required proof, authority envelope, stop conditions, available context/capabilities, and observable friction. Classify the earliest failed handoff as **context**, **capability/tool legibility**, **domain ownership**, **authority**, **proof**, **feedback/delivery**, or **possible worker limitation**. Do not call a single failure a worker limitation until comparable evidence rules out an environmental gap.

Choose the smallest reversible change at the authoritative owner. Verify both the target-native contract and the user/runtime journey, then rerun an equivalent job in a fresh session with the same authority and materially equivalent state. Compare accepted outcome, claim-matched proof, human relay, retries, authority/recovery behavior, displaced complexity, and maintenance cost. Retain a change provisionally only when the intervention was actually available and used, the bounded job improved, and its carrying cost is justified.

## Durable harness feedback

Promote a trajectory lesson only when it is durable, recurring, and owned by a repository boundary. Put it in the narrowest authoritative home:

- `CLAUDE.md` or a per-subtree contract — a stable rule
- a **storm module skill** — a repeatable procedure owned by this harness (change it in the module repo, not the installed copy)
- a **storm override** (`_bmad/custom/*.toml`) — wiring between storm and a stock workflow (change the template in `storm-setup/assets/overrides/` and re-run `storm-setup`, so the fix survives reinstalls)
- a tool diagnostic — a discoverability or recovery failure
- a test/infrastructure scan — an executable invariant
- an ADR — an architectural decision
- `deferred-work.md` — an accepted unresolved issue

Never edit installed BMAD files (`_bmad/core|bmm/`, stock skill folders) — a lesson that seems to require it belongs in an override, a storm skill, or an upstream issue. Do not create a parallel tracker or add an instruction merely because one run was inconvenient. Record the observed job, owner, evidence, maintenance/revisit condition, and retirement condition when promoting a lesson.
