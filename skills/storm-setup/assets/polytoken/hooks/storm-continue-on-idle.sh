#!/usr/bin/env bash
# storm-continue-on-idle — Storm-managed Polytoken hook handler.
#
# Hard contract (do not weaken):
#   * Every code path exits 0.
#   * For the stop event this script emits exactly one JSON outcome line on
#     stdout, and every path except the single deliberate bounded-continuation
#     path at the bottom emits {"outcome":"stop"}. Polytoken treats a handler
#     error on the stop event as blocking the handback — i.e. errors fail
#     TOWARD continuation — so this script must never error, never print
#     malformed JSON, and never print two outcome lines.
#   * For pre_user_prompt it prints nothing and exits 0 (accept). That event
#    fails open by design; the script only resets the one-shot guard there.
#   * Guard state is process-local scratch under TMPDIR keyed by session id.
#     It is never durable authority: restart safety comes from the fresh
#     POLYTOKEN_GOAL_ACTIVE / POLYTOKEN_FACET_NAME values Polytoken sets on
#     each invocation, plus the model-side instruction to verify Linear state
#     through the normal tool path before acting.
#   * The handler is trivial and fast: no network, no MCP, no Linear calls.

set +e

STOP_LINE='{"outcome":"stop"}'
CONTINUE_LINE='{"outcome":"continue","reason":"storm-continue-on-idle: inspect /jobs and /todo, reconcile every terminal specialist result, re-read current Linear issue state through the normal tool path (cached state is not authority), and continue only if safe approved work remains; otherwise stop."}'

emit_stop() { printf '%s\n' "$STOP_LINE"; exit 0; }
trap emit_stop HUP INT TERM

mode="${1:-${POLYTOKEN_HOOK_EVENT:-stop}}"

# Session id is used as a filename component; sanitize or refuse.
session="${POLYTOKEN_SESSION_ID:-unknown}"
case "$session" in
  *[!A-Za-z0-9._-]* | "") session="unknown" ;;
esac
guard_dir="${TMPDIR:-/tmp}/storm-continue-on-idle"
guard="$guard_dir/$session.fired"

# pre_user_prompt: a real user turn. Reset the one-shot guard and accept
# (print nothing, exit 0 — this event fails open by design).
if [ "$mode" = "pre_user_prompt" ] || [ "$mode" = "reset" ]; then
  rm -f -- "$guard" 2>/dev/null
  exit 0
fi

# Any event other than stop has no decision to make here.
if [ "$mode" != "stop" ]; then
  emit_stop
fi

# Drain the event JSON on stdin without ever failing on it.
cat >/dev/null 2>&1

# 1. Default-off: continuation requires the explicit enable marker that
#    storm-setup / storm-team writes only after operator approval, and the
#    environment kill-switch must not be set to off.
project="${POLYTOKEN_PROJECT_DIR:-}"
[ -n "$project" ] || emit_stop
[ -f "$project/.polytoken/hooks/storm-continue-on-idle.enabled" ] || emit_stop
if [ "${STORM_CONTINUE_ON_IDLE:-on}" = "off" ]; then
  emit_stop
fi

# 2. Active-goal and execute-facet gate, from fresh per-invocation env values.
[ "${POLYTOKEN_GOAL_ACTIVE:-false}" = "true" ] || emit_stop
[ "${POLYTOKEN_FACET_NAME:-}" = "execute" ] || emit_stop

# 3. One-shot guard: at most one continuation per real user prompt cycle.
#    If guard state cannot be read or claimed atomically, that is
#    uncertainty — stop.
mkdir -p -- "$guard_dir" 2>/dev/null || emit_stop
[ -f "$guard" ] && emit_stop
( set -C; : > "$guard" ) 2>/dev/null || emit_stop

# 4. Auto-drain ambiguity: Polytoken's documented stop-event surface does not
#    distinguish an auto-drained job-completion turn from a user-driven turn.
#    The one-shot guard bounds continuations to at most one per real user
#    prompt, so a drained turn can at worst consume — never multiply — the
#    single continuation. Any deeper ambiguity resolves to stop by contract.
printf '%s\n' "$CONTINUE_LINE"
exit 0
