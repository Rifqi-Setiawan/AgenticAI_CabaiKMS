"""Typed accessors for st.session_state — keeps the three pages from
scattering raw string-keyed session_state access, and gives each page a
single place to check "has a pipeline run happened yet".
"""

from __future__ import annotations

from typing import Any

import streamlit as st

_RESULT_KEY = "cabai_kms_pipeline_result"
_LOG_KEY = "cabai_kms_log"
_RUNNING_KEY = "cabai_kms_running"
_INPUTS_KEY = "cabai_kms_inputs"


def has_result() -> bool:
    return _RESULT_KEY in st.session_state


def get_result() -> Any | None:
    return st.session_state.get(_RESULT_KEY)


def set_result(result: Any) -> None:
    st.session_state[_RESULT_KEY] = result


def clear_result() -> None:
    st.session_state.pop(_RESULT_KEY, None)


def get_log() -> list[str]:
    return st.session_state.setdefault(_LOG_KEY, [])


def append_log(message: str) -> None:
    get_log().append(message)


def clear_log() -> None:
    st.session_state[_LOG_KEY] = []


def is_running() -> bool:
    return bool(st.session_state.get(_RUNNING_KEY, False))


def set_running(value: bool) -> None:
    st.session_state[_RUNNING_KEY] = value


def get_last_inputs() -> dict[str, Any]:
    return st.session_state.get(_INPUTS_KEY, {})


def set_last_inputs(**kwargs: Any) -> None:
    st.session_state[_INPUTS_KEY] = kwargs
