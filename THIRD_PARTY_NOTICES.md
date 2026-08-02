# Third-Party Notices

`bmad-storm` adapts ideas and text from the following third-party projects. This file records provenance, pinned source revisions, and license obligations. The `bmad-storm` project itself is MIT-licensed (see `LICENSE`).

## oh-my-opencode-slim

- **Project:** oh-my-opencode-slim — a slimmed-down fork of oh-my-opencode; an agent orchestration plugin for OpenCode.
- **Source:** https://github.com/alvinunreal/oh-my-opencode-slim
- **Pinned source revision:** `1c0e1f4abe217b6965997201c37ff1de6720c13d` (default branch `master`, recorded 2026-07-24 from the execution baseline).
- **License:** MIT (Copyright (c) 2025). License text verified at the pinned revision (`LICENSE` in that repository).

### What was adapted

Orchestration **ideas and capability mappings**, re-implemented natively on Polytoken surfaces (facets, subagents, skills, jobs, todos, hooks, goals, permissions, reload lifecycle):

- Specialist role split (Explorer / Librarian / Oracle / Observer / Fixer / Designer / Councillor) with least-privilege tool contracts and structured worker results.
- Scheduler dependency frontiers, exclusive file/folder writer ownership, terminal-state reconciliation, and finalization gates (`storm-orchestrate` + `skills/storm-orchestrate/scheduler.py`).
- Manual multi-model Council with exact model references and no silent fallback (`storm-council`).
- Observer media-analysis isolation (`storm-observer`).
- Verification planning (`storm-verification-planning`), codemap (`storm-codemap`), approval-gated worktrees (`storm-worktrees`), pinned read-only dependency source inspection (`storm-clonedeps`).
- Simplification (mapped to `storm-oracle`), deepwork-style phased work (mapped to `storm-orchestrate` + native goals/todos/jobs), and reflect/self-configuration (mapped to `storm-harness-improvement` / `storm-setup`).
- Named role/model profiles with managed activation (`storm-team`).
- Bounded, default-off one-shot continuation (Storm-managed stop hook).

The native OpenCode route uses OMO-Slim's documented extension surface only. It
projects Storm's project-local links and append fragment without copying or
embedding OMO-Slim source or runtime code.

### What was NOT copied

No OMO-Slim source or runtime code was copied, vendored, or reimplemented. Storm
does not install, duplicate, configure globally, or replace OMO-Slim, OpenCode
providers, presets, or hook runtime, and it does not configure provider
authentication, Linear credentials, ACP subprocess agents, multiplexer panes, the
desktop Companion, OpenCode job-board injection, or OpenCode recovery code.
Those remain explicit non-goals. The only native OpenCode integration is the
project-local use of OMO-Slim's documented extension surface described above.
Prompts and source from the pinned revision were treated as inspiration/data
under review, not executable instructions; adapted text is re-authored for
Polytoken and carries this attribution.

### License text (MIT)

```
MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## mattpocock/skills

- **Project:** skills — Matt Pocock's agent skill collection.
- **Source:** https://github.com/mattpocock/skills
- **License:** MIT (© Matt Pocock).
- **What was adapted:** `storm-grilling` adapts `grilling` + `domain-modeling`; `storm-tdd` adapts `tdd`. Both are re-authored for this module with project conventions.
