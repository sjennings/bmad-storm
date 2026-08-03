#!/usr/bin/env python3
"""Validate Storm-managed Polytoken assets (standard library only).

Checks the documented Polytoken load-time rules plus Storm's own safety
requirements without needing provider credentials:

  * filename/frontmatter ``name`` equality
  * no manual ``exit_tool`` grant (Polytoken registers it; listing it is a
    load-time rejection)
  * valid tool/skill allow/deny list shapes
  * read-only roles carry no mutation-capable tools and never inherit tools
  * write roles deny every known lifecycle/control/Linear-mutation tool,
    deny shell by default, and cannot spawn subagents. Exception: on
    Polytoken 0.5.9 the harness-managed ``subagent`` tool cannot appear in
    ``tools_deny`` (the runtime rejects such definitions at load time), so
    write roles must NOT list it; spawning is blocked by
    ``allow_subagent_spawn: false``/runtime semantics plus coordinator
    convention instead of an exact deny-union. The validator requires
    ``allow_subagent_spawn: false`` and rejects ``subagent`` in a write
    role's deny list so the limitation stays explicit.
  * councillor definitions omit ``fallback_models`` (exact model references
    are runtime-gated; silent fallback is forbidden)
  * explicit structured exit schemas, with task-fit/partial-work fields on
    write roles
  * profile manifests reference existing roles and valid model references
  * managed hook entries use known events/outcomes and unique storm- names,
    and the continuation script keeps its emit-and-exit choke point
  * no secret values or placeholder credentials in distributed assets
  * asset manifest checksums are in sync (``--refresh`` rewrites them)

Usage:
    validate_polytoken_assets.py [--root DIR] [--refresh]

Exit code 0 means no findings; 1 means at least one finding.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

READ_ONLY_ROLES = {
    "storm-explorer",
    "storm-librarian",
    "storm-oracle",
    "storm-observer",
    "storm-councillor",
}
WRITE_ROLES = {"storm-fixer", "storm-designer"}
ALL_ROLES = READ_ONLY_ROLES | WRITE_ROLES

KNOWN_BUILTIN_TOOLS = {
    "file_read", "file_read_hashline", "file_edit_search_replace",
    "file_edit_hashline", "patch_edit", "file_write", "glob", "grep",
    "flag_important", "shell_exec", "shell_monitor", "pushd", "popd",
    "job_status", "job_block", "job_result", "job_cancel", "subagent",
    "message_subagent", "skill", "todo_create", "todo_update",
    "todo_complete", "todo_delete", "todo_list", "write_plan", "edit_plan",
    "handoff_plan", "propose_goal", "read_goal", "complete_goal",
    "block_goal", "switch_facet", "web_search", "web_fetch",
    "mcp_list_resources", "mcp_read_resource", "ask_user_question",
    "tool_search", "progress_update",
}
TOOL_SHORTHANDS = {"tag!ALL", "tag!ALL_MCP"}

MUTATION_BUILTIN_TOOLS = {
    "file_write", "file_edit_search_replace", "file_edit_hashline",
    "patch_edit", "shell_exec", "shell_monitor",
}

LIFECYCLE_CONTROL_TOOLS = [
    "write_plan", "edit_plan", "handoff_plan", "propose_goal",
    "complete_goal", "block_goal", "switch_facet", "subagent",
    "message_subagent", "todo_create", "todo_update", "todo_complete",
    "todo_delete",
]

# Linear mutations run through linear-cli under the coordinator's shell tool.
# Writer roles deny shell_exec/shell_monitor, so they cannot bypass storm-linear
# with direct tracker calls. No separate tracker tool surface is managed here.
WRITE_ROLE_REQUIRED_DENY = (
    LIFECYCLE_CONTROL_TOOLS + ["shell_exec", "shell_monitor"]
)

# Harness-managed tools that Polytoken 0.5.9 refuses to load in a
# ``tools_deny`` list. Approved operator deviation (2026, live 0.5.9 gate):
# write roles drop ``subagent`` from the deny list and rely on
# ``allow_subagent_spawn: false`` plus runtime semantics and coordinator
# convention. Do not claim an exact deny-union for these tools on 0.5.9.
HARNESS_MANAGED_UNDENIABLE = {"subagent"}

WRITE_ROLE_REQUIRED_DENY = [
    tool for tool in WRITE_ROLE_REQUIRED_DENY
    if tool not in HARNESS_MANAGED_UNDENIABLE
]

MODEL_ALIAS_RE = re.compile(r"^default_model:(full|mini|nano)$")
MODEL_QUALIFIED_RE = re.compile(
    r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._:/-]*"
    r"(\((low|medium|high|xhigh|max|nano|mini|full)\))?$"
)

HOOK_EVENTS = {
    "session_start", "pre_user_prompt", "pre_model_turn", "post_model_turn",
    "pre_tool_use", "post_tool_use", "post_tool_use_failure", "stop",
    "pre_compaction", "post_compaction", "notification", "facet_switch",
    "subagent_start", "subagent_stop",
}

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{12,}"),
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)"
               r"\s*[:=]\s*['\"][A-Za-z0-9/+_=-]{8,}['\"]"),
    # Fragments are concatenated so this file does not match its own pattern.
    re.compile(r"(?i)your[_-]api[_-]key|change[_-]?me|insert[_-]token"
               r"|<api" + r"[_-]key>|<tok" + r"en>"),
]


def parse_frontmatter(path: Path) -> dict:
    """Parse the restricted YAML frontmatter subset used by managed assets.

    Supported shape: top-level ``key: value`` scalars and one nested
    ``polytoken:`` mapping whose values are scalars, ``true``/``false``,
    inline ``[a, b]`` lists, or inline JSON objects. That is the whole
    authored subset; anything else is a finding, not a parse guess.
    """
    text = path.read_text()
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening --- frontmatter delimiter")
    try:
        end = lines[1:].index("---") + 1
    except ValueError:
        raise ValueError("missing closing --- frontmatter delimiter")
    data: dict = {}
    current_section = None
    for raw in lines[1:end]:
        if not raw.strip():
            continue
        if raw.startswith("  ") and current_section:
            key, _, value = raw.strip().partition(":")
            data[current_section][key.strip()] = _parse_value(value.strip())
        elif not raw.startswith(" "):
            key, _, value = raw.partition(":")
            key = key.strip()
            value = value.strip()
            if value == "":
                data[key] = {}
                current_section = key
            else:
                data[key] = _parse_value(value)
                current_section = None
        else:
            raise ValueError(f"unsupported frontmatter line: {raw!r}")
    return data


def _parse_value(value: str):
    if value in ("true", "false"):
        return value == "true"
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [item.strip() for item in inner.split(",")] if inner else []
    if value.startswith("{"):
        return json.loads(value)
    return value


def _is_valid_tool_ref(entry) -> bool:
    if not isinstance(entry, str) or not entry:
        return False
    if entry in KNOWN_BUILTIN_TOOLS or entry in TOOL_SHORTHANDS:
        return True
    if entry.startswith("mcp__") and re.fullmatch(r"mcp__[a-z0-9_]+(__[a-z0-9_]+)?", entry):
        return True
    return False


class Validator:
    def __init__(self, root: Path):
        self.root = root
        self.findings: list[str] = []

    def finding(self, subject: str, message: str) -> None:
        self.findings.append(f"{subject}: {message}")

    def run(self) -> list[str]:
        self.check_subagents()
        self.check_profiles()
        self.check_hooks()
        self.check_manifest()
        self.check_secrets()
        return self.findings

    # -- subagents ---------------------------------------------------------

    def check_subagents(self) -> None:
        directory = self.root / "subagents"
        found = set()
        for path in sorted(directory.glob("*.md")):
            found.add(path.stem)
            self._check_one_subagent(path)
        missing = ALL_ROLES - found
        if missing:
            self.finding("subagents", f"missing role definitions: {sorted(missing)}")

    def _check_one_subagent(self, path: Path) -> None:
        subject = f"subagent {path.stem}"
        try:
            fm = parse_frontmatter(path)
        except (ValueError, json.JSONDecodeError) as exc:
            self.finding(subject, f"frontmatter parse failure: {exc}")
            return
        poly = fm.get("polytoken")
        if not isinstance(poly, dict):
            self.finding(subject, "missing polytoken frontmatter mapping")
            return
        if fm.get("name") != path.stem:
            self.finding(subject, f"name {fm.get('name')!r} != filename {path.stem!r}")
        if not fm.get("description"):
            self.finding(subject, "missing description")

        tools = poly.get("tools", [])
        deny = poly.get("tools_deny", [])
        for label, entries in (("tools", tools), ("tools_deny", deny)):
            if not isinstance(entries, list) or not all(
                _is_valid_tool_ref(e) for e in entries
            ):
                self.finding(subject, f"invalid {label} entries: {entries!r}")
        if "exit_tool" in tools or "exit_tool" in deny:
            self.finding(subject, "exit_tool must never appear in tool lists")
        if path.stem in READ_ONLY_ROLES and poly.get("inherit_tools") is not False:
            self.finding(subject, "read-only roles must set inherit_tools: false")
        if poly.get("allow_subagent_spawn") is not False:
            self.finding(subject, "allow_subagent_spawn must be false")
        if poly.get("fallback_models"):
            self.finding(subject, "managed roles omit fallback_models; exact model "
                                  "references are runtime-gated, never silently substituted")

        if path.stem in READ_ONLY_ROLES:
            bad = set(tools) & (MUTATION_BUILTIN_TOOLS
                                | set(LIFECYCLE_CONTROL_TOOLS))
            if bad:
                self.finding(subject, f"read-only role grants mutating tools: {sorted(bad)}")
        elif path.stem in WRITE_ROLES:
            if poly.get("inherit_tools") is not True:
                self.finding(subject, "write roles must set inherit_tools: true")
            undeniable = [t for t in deny if t in HARNESS_MANAGED_UNDENIABLE]
            if undeniable:
                self.finding(
                    subject,
                    f"tools_deny lists harness-managed {undeniable}: Polytoken "
                    "0.5.9 rejects these at load time; remove them and rely on "
                    "allow_subagent_spawn: false (exact deny-union unavailable)",
                )
            missing = [t for t in WRITE_ROLE_REQUIRED_DENY if t not in deny]
            if missing:
                self.finding(subject, f"write role deny list is missing: {missing}")
            for tool in MUTATION_BUILTIN_TOOLS - {"shell_exec", "shell_monitor"}:
                if tool not in tools:
                    self.finding(subject, f"write role is missing edit tool {tool!r}")

        schema = poly.get("exit_tool_schema")
        if not isinstance(schema, dict) or schema.get("type") != "object":
            self.finding(subject, "exit_tool_schema must be an inline JSON object schema")
        else:
            required = set(schema.get("required", []))
            if not {"success", "summary"} <= required:
                self.finding(subject, "exit schema must require success and summary")
            if path.stem in WRITE_ROLES and not {
                "task_fit", "files_changed", "partial_changes", "blockers"
            } <= required:
                self.finding(subject, "write role exit schema must require task_fit, "
                                      "files_changed, partial_changes, blockers")

    # -- profiles ----------------------------------------------------------

    def check_profiles(self) -> None:
        directory = self.root / "profiles"
        found = set()
        for path in sorted(directory.glob("*.json")):
            found.add(path.stem)
            subject = f"profile {path.stem}"
            try:
                profile = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                self.finding(subject, f"invalid JSON: {exc}")
                continue
            if profile.get("name") != path.stem:
                self.finding(subject, f"name {profile.get('name')!r} != filename {path.stem!r}")
            roles = profile.get("roles")
            if not isinstance(roles, dict):
                self.finding(subject, "missing roles mapping")
                continue
            unknown = set(roles) - ALL_ROLES
            missing = ALL_ROLES - set(roles)
            if unknown:
                self.finding(subject, f"references unknown roles: {sorted(unknown)}")
            if missing:
                self.finding(subject, f"incomplete team; missing roles: {sorted(missing)}")
            for role, spec in roles.items():
                if not isinstance(spec, dict):
                    self.finding(subject, f"role {role} entry must be an object")
                    continue
                if "fallback_models" in spec:
                    self.finding(subject, f"role {role} sets fallback_models; silent "
                                          "fallback is forbidden")
                model = spec.get("model")
                if model is not None and not (
                    MODEL_ALIAS_RE.match(model) or MODEL_QUALIFIED_RE.match(model)
                ):
                    self.finding(subject, f"role {role} has invalid model reference {model!r}")
        for expected in ("quality", "balanced", "economy", "inherit"):
            if expected not in found:
                self.finding("profiles", f"missing built-in profile {expected!r}")

    # -- hooks -------------------------------------------------------------

    def check_hooks(self) -> None:
        fragment = self.root / "hooks" / "hooks.fragment.json"
        try:
            entries = json.loads(fragment.read_text())
        except json.JSONDecodeError as exc:
            self.finding("hooks.fragment.json", f"invalid JSON: {exc}")
            entries = []
        if not isinstance(entries, list):
            self.finding("hooks.fragment.json", "fragment must be a JSON array")
            entries = []
        names = []
        for entry in entries:
            name = entry.get("name", "")
            names.append(name)
            if not name.startswith("storm-"):
                self.finding("hooks.fragment.json", f"managed hook name {name!r} "
                                                    "must be storm- prefixed")
            if entry.get("event") not in HOOK_EVENTS:
                self.finding("hooks.fragment.json", f"unknown event {entry.get('event')!r}")
            bash = entry.get("handler", {}).get("bash", "")
            if "storm-continue-on-idle.sh" not in bash:
                self.finding("hooks.fragment.json", f"hook {name!r} must invoke the "
                                                    "managed continuation script")
        if len(names) != len(set(names)):
            self.finding("hooks.fragment.json", "duplicate managed hook names")

        script_path = self.root / "hooks" / "storm-continue-on-idle.sh"
        script = script_path.read_text()
        for marker in (
            "emit_stop()",
            "POLYTOKEN_GOAL_ACTIVE",
            "POLYTOKEN_FACET_NAME",
            "storm-continue-on-idle.enabled",
            "pre_user_prompt",
            '{"outcome":"stop"}',
            '{"outcome":"continue"',
            "set -C",
        ):
            if marker not in script:
                self.finding("storm-continue-on-idle.sh", f"missing safety marker {marker!r}")
        if script.count('printf \'%s\\n\' "$CONTINUE_LINE"') != 1:
            self.finding("storm-continue-on-idle.sh", "must have exactly one deliberate "
                                                      "continue emission path")
        if re.search(r"exit\s+[1-9]", script):
            self.finding("storm-continue-on-idle.sh", "must exit 0 on every path")

    # -- manifest ----------------------------------------------------------

    def check_manifest(self, refresh: bool = False) -> None:
        manifest_path = self.root / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as exc:
            self.finding("manifest.json", f"invalid JSON: {exc}")
            return
        assets = manifest.get("assets", [])
        covered = set()
        changed = False
        for asset in assets:
            source = asset.get("source", "")
            covered.add(source)
            if asset.get("kind") not in {
                "subagent", "profile", "hook-script", "hook-fragment", "script"
            }:
                self.finding("manifest.json", f"{source}: unknown kind {asset.get('kind')!r}")
            if asset.get("merge") not in {"managed-file", "merge-by-name", "none"}:
                self.finding("manifest.json", f"{source}: unknown merge strategy")
            target = asset.get("target", "")
            if not (target.startswith(".polytoken/") or target == ".polytoken/hooks.json"):
                self.finding("manifest.json", f"{source}: target {target!r} escapes .polytoken/")
            else:
                # Mirror of manage_polytoken_assets.validate_target: the
                # .polytoken/storm tree is reserved for runtime state; only
                # .polytoken/storm/profiles/ is a valid managed target.
                parts = PurePosixPath(target).parts
                if (len(parts) > 1 and parts[1] == "storm"
                        and not (len(parts) > 2 and parts[2] == "profiles")):
                    self.finding("manifest.json", f"{source}: target {target!r} is "
                                                  "reserved for Storm runtime state")
            source_path = self.root / source
            if not source_path.exists():
                self.finding("manifest.json", f"missing source {source!r}")
                continue
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            if refresh:
                if asset.get("sha256") != digest:
                    asset["sha256"] = digest
                    changed = True
            elif asset.get("sha256") != digest:
                self.finding("manifest.json", f"{source}: checksum drift "
                                              "(run --refresh to re-pin)")
        shipped = {
            str(p.relative_to(self.root))
            for base in ("subagents", "profiles", "hooks")
            for p in (self.root / base).glob("*")
            if p.is_file()
        }
        for uncovered in sorted(shipped - covered):
            self.finding("manifest.json", f"shipped asset not in manifest: {uncovered!r}")
        if refresh and changed:
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    # -- secrets -----------------------------------------------------------

    def check_secrets(self) -> None:
        for base in ("subagents", "profiles", "hooks", "scripts"):
            directory = self.root / base
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                text = path.read_text(errors="replace")
                for pattern in SECRET_PATTERNS:
                    if pattern.search(text):
                        self.finding(str(path.relative_to(self.root)),
                                     f"possible secret/placeholder credential: {pattern.pattern!r}")


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1]
    refresh = False
    args = iter(argv[1:])
    for arg in args:
        if arg == "--root":
            root = Path(next(args)).resolve()
        elif arg == "--refresh":
            refresh = True
        else:
            print(f"unknown argument: {arg}", file=sys.stderr)
            return 2
    validator = Validator(root)
    validator.check_subagents()
    validator.check_profiles()
    validator.check_hooks()
    validator.check_manifest(refresh=refresh)
    validator.check_secrets()
    if refresh:
        print("manifest checksums refreshed")
    if validator.findings:
        for finding in validator.findings:
            print(f"FINDING: {finding}")
        return 1
    print(f"OK: {root} assets valid")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
