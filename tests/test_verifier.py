from __future__ import annotations

from typing import Any, TypedDict

import pytest
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ValidationError

from src.reliability.verifier import (
    agent_error_key,
    make_agent_node,
    make_verifier_node,
    make_verifier_router,
    verify_with_revision,
    verify_with_trace,
)


class _Dummy(BaseModel):
    value: int


class _DemoState(TypedDict, total=False):
    """LangGraph only tracks channels for keys a TypedDict state schema
    actually declares (an undeclared key a node returns is silently
    dropped, not an error) — so the demo graph below needs its own schema
    declaring `result` and its agent_error_key sidecar, rather than
    reusing production GlobalState (which has neither, since the verifier
    module is deliberately state-schema-agnostic)."""

    result: Any
    error_trace: list[str]
    _agent_error_result: str


def _bad_validation_error() -> ValidationError:
    return ValidationError.from_exception_data("Dummy", [])


class TestVerifyWithRevision:
    def test_accepted_on_first_try(self):
        outcome = verify_with_revision(lambda: _Dummy(value=1))
        assert outcome.accepted is True
        assert outcome.attempts == 1
        assert outcome.failure_reasons == []

    def test_revise_triggered_and_succeeds_within_max_revisions(self):
        calls = []

        def call():
            calls.append(1)
            if len(calls) < 3:
                raise _bad_validation_error()
            return _Dummy(value=42)

        outcome = verify_with_revision(call, max_revisions=3)
        assert outcome.accepted is True
        assert outcome.result == _Dummy(value=42)
        assert outcome.attempts == 3
        assert len(outcome.failure_reasons) == 2

    def test_unrecoverable_case_gives_up_after_max_revisions(self):
        calls = []

        def always_fails():
            calls.append(1)
            raise _bad_validation_error()

        outcome = verify_with_revision(always_fails, max_revisions=2)
        assert outcome.accepted is False
        assert outcome.result is None
        assert outcome.attempts == 3  # 1 initial + 2 revisions
        assert len(outcome.failure_reasons) == 3
        assert len(calls) == 3

    def test_non_revisable_exception_propagates_immediately(self):
        calls = []

        def raises_unrelated():
            calls.append(1)
            raise RuntimeError("not a contract failure")

        with pytest.raises(RuntimeError):
            verify_with_revision(raises_unrelated, max_revisions=5)
        assert len(calls) == 1  # never revised — wrong exception type


class TestVerifyWithTrace:
    def test_success_produces_empty_patch(self):
        state = {"error_trace": []}
        outcome, patch = verify_with_trace(lambda: _Dummy(value=1), state)
        assert outcome.accepted is True
        assert patch == {}

    def test_failure_records_reason_with_manual_review_mention(self):
        state = {"error_trace": ["prior"]}

        def always_fails():
            raise _bad_validation_error()

        outcome, patch = verify_with_trace(always_fails, state, max_revisions=1, context="atribut='X'")
        assert outcome.accepted is False
        assert "manual_review" in patch["error_trace"][-1]
        assert "atribut='X'" in patch["error_trace"][-1]
        assert patch["error_trace"][0] == "prior"  # existing trace preserved
        assert state["error_trace"] == ["prior"]  # original not mutated


class TestVerifierAsARealLangGraphNode:
    """Proves make_agent_node/make_verifier_node/make_verifier_router work
    as an actual Verifier/Critic node pair inside a compiled StateGraph —
    not just as bare function calls."""

    def _build_demo_graph(self, agent_call, *, max_revisions: int = 2, result_key: str = "result"):
        graph = StateGraph(_DemoState)
        graph.add_node("agent", make_agent_node(agent_call, result_key))
        graph.add_node("verifier", make_verifier_node(result_key, _Dummy))
        graph.add_node("manual_review", lambda state: {})

        graph.set_entry_point("agent")
        graph.add_edge("agent", "verifier")
        graph.add_conditional_edges(
            "verifier",
            make_verifier_router(result_key, _Dummy, max_revisions=max_revisions),
            {"revise": "agent", "manual_review": "manual_review", "continue": END},
        )
        graph.add_edge("manual_review", END)
        return graph.compile()

    def test_revise_loop_re_invokes_agent_node_and_eventually_succeeds(self):
        calls = []

        def flaky_agent(state: _DemoState):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("simulated transient failure")
            return _Dummy(value=42)

        app = self._build_demo_graph(flaky_agent, max_revisions=3)
        final_state = app.invoke({"error_trace": []})

        assert len(calls) == 3  # agent node really was revisited by the graph
        assert final_state["result"] == _Dummy(value=42)
        assert len(final_state["error_trace"]) == 2  # one entry per failed attempt

    def test_unrecoverable_case_falls_to_manual_review_with_reason_recorded(self):
        calls = []

        def always_fails(state: _DemoState):
            calls.append(1)
            raise RuntimeError("permanently broken")

        app = self._build_demo_graph(always_fails, max_revisions=2)
        final_state = app.invoke({"error_trace": []})

        assert final_state.get("result") is None  # never produced a valid result
        assert len(calls) == 3  # 1 initial + 2 revisions, then gave up
        assert len(final_state["error_trace"]) == 3
        assert all("percobaan gagal" in reason for reason in final_state["error_trace"])

    def test_contract_violation_without_an_exception_also_triggers_revise(self):
        """The agent node can also "succeed" (no exception) but hand back
        something that fails the verifier's isinstance check — e.g. a bad
        constrained-decoding result that didn't raise. That must revise
        too, driven by the verifier node, not the agent node."""
        calls = []

        def wrong_type_then_right(state: _DemoState):
            calls.append(1)
            if len(calls) < 2:
                return {"not": "a Dummy"}
            return _Dummy(value=7)

        app = self._build_demo_graph(wrong_type_then_right, max_revisions=2)
        final_state = app.invoke({"error_trace": []})

        assert len(calls) == 2
        assert final_state["result"] == _Dummy(value=7)
        assert len(final_state["error_trace"]) == 1
        assert "verifier menolak" in final_state["error_trace"][0]
