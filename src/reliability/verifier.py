"""Verifier/Critic: closed-loop self-correction for any agent call whose
output should validate against a Pydantic contract.

Deliberately generic — it doesn't know anything about schema-matching or
vision classification specifically (those agents' own NULL-mapping /
UNCERTAIN-status handling stays in src/agents/schema_matching/review_queue.py
and is composed on top of this in src/reliability/wrappers.py). This module
is strictly about "the call itself failed to produce anything usable" —
invalid contracts, primarily.

`make_verifier_node` / `make_verifier_router` turn `verify_with_revision`
into an actual LangGraph node + conditional-edge router pair, so this is
provably usable as a real "Verifier/Critic node di orchestrator" — see
tests/test_verifier.py, which builds and runs a small real StateGraph
through it, not just calling the plain function directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, MutableMapping, TypeVar

from pydantic import ValidationError

from src.agents.schema_matching.review_queue import append_error_trace

T = TypeVar("T")

DEFAULT_MAX_REVISIONS = 2

# Deliberately NOT GlobalState: this module is state-schema-agnostic (see
# module docstring), and LangGraph turns out to actively enforce that
# distinction — it introspects a node/edge callable's OWN parameter type
# annotation to decide which state keys to expose to it, filtering down to
# that type's declared fields regardless of what schema the StateGraph
# itself was built with. Annotating these closures as `GlobalState` would
# silently strip any key GlobalState doesn't declare (e.g. a caller's own
# `result` key) before the function ever saw it — a real bug this project
# hit and fixed, not a hypothetical. See tests/test_verifier.py.
AgentState = MutableMapping[str, Any]


@dataclass
class VerificationOutcome:
    accepted: bool
    result: Any | None
    attempts: int
    failure_reasons: list[str] = field(default_factory=list)


def verify_with_revision(
    call: Callable[[], T],
    *,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
    revisable_exceptions: tuple[type[BaseException], ...] = (ValidationError,),
) -> VerificationOutcome:
    """Call `call()`. If it raises one of `revisable_exceptions` (a
    contract failure), call it again — up to `max_revisions` additional
    times ("revise"). Gives up (accepted=False) once that's exhausted;
    every failure's str() is recorded, oldest first."""
    reasons: list[str] = []
    attempt = 0
    for attempt in range(1, max_revisions + 2):  # 1 initial try + max_revisions revisions
        try:
            result = call()
            return VerificationOutcome(accepted=True, result=result, attempts=attempt, failure_reasons=reasons)
        except revisable_exceptions as exc:
            reasons.append(f"percobaan {attempt}: {exc}")
    return VerificationOutcome(accepted=False, result=None, attempts=attempt, failure_reasons=reasons)


def verify_with_trace(
    call: Callable[[], T],
    state: AgentState,
    *,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
    revisable_exceptions: tuple[type[BaseException], ...] = (ValidationError,),
    context: str = "",
) -> tuple[VerificationOutcome, dict[str, Any]]:
    """verify_with_revision, plus a GlobalState.error_trace patch (same
    append-don't-overwrite convention as review_queue.process_mapping) —
    {} if the call was ultimately accepted, otherwise a patch recording
    the escalation to manual_review and every failure reason."""
    outcome = verify_with_revision(call, max_revisions=max_revisions, revisable_exceptions=revisable_exceptions)
    if outcome.accepted:
        return outcome, {}

    prefix = f"{context}: " if context else ""
    reason = (
        f"{prefix}gagal validasi kontrak setelah {outcome.attempts} percobaan "
        f"(maks {max_revisions} revisi) -> manual_review. Alasan: "
        + "; ".join(outcome.failure_reasons)
    )
    return outcome, append_error_trace(state, reason)


# --------------------------------------------------------------------------
# LangGraph integration: agent/verifier NODES + a router, wired the same
# way Fase 2's own route_after_vision already is (src/orchestrator/graph.py)
# — error_trace length as the revise-attempt counter, so a real compiled
# StateGraph can loop agent_node -> verifier_node -> {revise: agent_node,
# manual_review: ..., continue: ...} and this is exactly what
# tests/test_verifier.py builds and runs, not just a bare function call.
# --------------------------------------------------------------------------

VerifierRoute = Literal["revise", "manual_review", "continue"]


def make_agent_node(
    call: Callable[[AgentState], T],
    result_key: str,
) -> Callable[[AgentState], dict[str, Any]]:
    """Wrap any agent call as a graph node: invoke call(state), catching
    ANY exception (a transient failure, or a contract violation the agent
    itself detected and raised) rather than crashing the graph. The
    exception's message is stashed in a private side-channel key for the
    paired verifier node to report — this node itself never writes to
    error_trace, so a failed attempt is recorded exactly once, by the
    verifier, not twice."""

    error_key = agent_error_key(result_key)

    def node(state: AgentState) -> dict[str, Any]:
        try:
            result = call(state)
        except Exception as exc:  # noqa: BLE001 — deliberately broad: this IS the catch boundary
            return {result_key: None, error_key: str(exc)}
        return {result_key: result, error_key: None}

    return node


def agent_error_key(result_key: str) -> str:
    """The side-channel key make_agent_node stashes a failure reason
    under, for make_verifier_node to read. Exposed so a caller's own state
    schema (a graph built with a specific TypedDict, e.g. in a test) can
    declare it explicitly — LangGraph only tracks channels for keys a
    TypedDict state schema actually declares; an undeclared key is
    silently dropped, not an error."""
    return f"_agent_error_{result_key}"


def make_verifier_node(
    result_key: str,
    response_model: type[Any],
) -> Callable[[AgentState], dict[str, Any]]:
    """The actual contract gate — and the SOLE place a failed attempt gets
    recorded to error_trace (exactly once per attempt, whether the agent
    node raised or just handed back the wrong shape). Checks whatever the
    paired agent node (make_agent_node) just produced — or didn't —
    against `response_model`. Decoupled from the agent's own code on
    purpose: this is what makes it a genuine Verifier/Critic step rather
    than the agent grading its own homework."""

    error_key = agent_error_key(result_key)

    def node(state: AgentState) -> dict[str, Any]:
        candidate = state.get(result_key)
        if isinstance(candidate, response_model):
            return {}

        agent_error = state.get(error_key)
        if agent_error:
            reason = f"{result_key}: percobaan gagal — {agent_error}"
        else:
            reason = (
                f"{result_key}: verifier menolak keluaran (tipe={type(candidate).__name__}, "
                f"bukan {response_model.__name__})"
            )
        return append_error_trace(state, reason)

    return node


def make_verifier_router(
    result_key: str,
    response_model: type[Any],
    *,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
) -> Callable[[AgentState], VerifierRoute]:
    """continue once a valid result_key is present; otherwise revise
    (loop back to the agent node) until error_trace has accumulated more
    than max_revisions failures for this pair, then manual_review."""

    def router(state: AgentState) -> VerifierRoute:
        if isinstance(state.get(result_key), response_model):
            return "continue"
        if len(state.get("error_trace", [])) > max_revisions:
            return "manual_review"
        return "revise"

    return router
