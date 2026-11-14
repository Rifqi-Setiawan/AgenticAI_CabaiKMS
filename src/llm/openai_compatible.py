"""Shared configuration and client construction for OpenAI-compatible APIs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Mapping
from urllib.parse import urlparse

from src.reliability.provider_failures import ProviderCallError, ProviderFailureKind

NINEROUTER_DEFAULT_BASE_URL = "http://127.0.0.1:20128/v1"
NINEROUTER_REQUIRED_TEXT_MODEL = "ag/gemini-3.8-flash-medium"
NINEROUTER_REQUIRED_VISION_MODEL = "ag/gemini-3.8-flash-high"
NINEROUTER_DEFAULT_TIMEOUT_SECONDS = 60.0
# Evaluation only: compare other vision models on the same harness (D26). Production never sets it.
EVAL_VISION_MODEL_VARIABLE = "CABAI_KMS_EVAL_VISION_MODEL"
# Evaluation only: send vision calls to another OpenAI-compatible gateway (base URL + key of its own).
EVAL_VISION_BASE_URL_VARIABLE = "CABAI_KMS_EVAL_VISION_BASE_URL"
EVAL_VISION_API_KEY_VARIABLE = "CABAI_KMS_EVAL_VISION_API_KEY"

ProviderMode = Literal["9router", "legacy"]


def provider_mode(variable: str, environ: Mapping[str, str] | None = None) -> ProviderMode:
    """Read an explicit provider mode; 9Router is the reproducible default."""
    source = os.environ if environ is None else environ
    value = source.get(variable, "9router").strip().lower()
    if value not in {"9router", "legacy"}:
        raise ProviderCallError(
            f"{variable} must be '9router' or 'legacy'",
            failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
        )
    return value  # type: ignore[return-value]


def eval_vision_model_override(environ: Mapping[str, str] | None = None) -> str:
    """Return the evaluation-only vision model override, or an empty string."""
    source = os.environ if environ is None else environ
    return source.get(EVAL_VISION_MODEL_VARIABLE, "").strip()


def eval_vision_base_url(environ: Mapping[str, str] | None = None) -> str:
    source = os.environ if environ is None else environ
    return source.get(EVAL_VISION_BASE_URL_VARIABLE, "").strip()


def effective_vision_model(environ: Mapping[str, str] | None = None) -> str:
    return eval_vision_model_override(environ) or NINEROUTER_REQUIRED_VISION_MODEL


def _validated_base_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != "/v1"
    ):
        raise ProviderCallError(
            "NINEROUTER_BASE_URL must be an http(s) URL ending in /v1 without credentials or query data",
            failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
        )
    return value.rstrip("/")


@dataclass(frozen=True)
class NinerouterConfig:
    base_url: str
    api_key: str
    text_model: str
    vision_model: str
    timeout_seconds: float

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        require_role: Literal["text", "vision", "both"] = "both",
    ) -> "NinerouterConfig":
        source = os.environ if environ is None else environ
        api_key = source.get("NINEROUTER_API_KEY", "").strip()
        if not api_key:
            raise ProviderCallError(
                "NINEROUTER_API_KEY is not set",
                failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
            )

        models: dict[str, str] = {}
        required_roles = {
            "text": ("TEXT",),
            "vision": ("VISION",),
            "both": ("TEXT", "VISION"),
        }[require_role]
        required_models = {
            "TEXT": NINEROUTER_REQUIRED_TEXT_MODEL,
            "VISION": NINEROUTER_REQUIRED_VISION_MODEL,
        }
        for role in ("TEXT", "VISION"):
            variable = f"NINEROUTER_{role}_MODEL"
            model = source.get(variable, "").strip()
            if not model and role in required_roles:
                raise ProviderCallError(
                    f"{variable} is not set",
                    failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
                )
            required_model = required_models[role]
            if model and model != required_model:
                raise ProviderCallError(
                    f"{variable} must be {required_model}",
                    failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
                )
            models[role] = model
        override = eval_vision_model_override(source)
        if override:
            models["VISION"] = override
        base_url = source.get("NINEROUTER_BASE_URL", NINEROUTER_DEFAULT_BASE_URL).strip()
        eval_base = eval_vision_base_url(source)
        if eval_base and require_role == "vision":
            if not override:
                raise ProviderCallError(
                    f"{EVAL_VISION_BASE_URL_VARIABLE} needs {EVAL_VISION_MODEL_VARIABLE}",
                    failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
                )
            api_key = source.get(EVAL_VISION_API_KEY_VARIABLE, "").strip()
            if not api_key:
                raise ProviderCallError(
                    f"{EVAL_VISION_API_KEY_VARIABLE} is not set",
                    failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
                )
            base_url = eval_base

        raw_timeout = source.get(
            "NINEROUTER_TIMEOUT_SECONDS", str(int(NINEROUTER_DEFAULT_TIMEOUT_SECONDS))
        )
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ProviderCallError(
                "NINEROUTER_TIMEOUT_SECONDS must be a positive number",
                failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
            ) from exc
        if timeout <= 0:
            raise ProviderCallError(
                "NINEROUTER_TIMEOUT_SECONDS must be a positive number",
                failure_kind=ProviderFailureKind.NON_RETRYABLE_CONFIGURATION,
            )

        return cls(
            base_url=_validated_base_url(base_url),
            api_key=api_key,
            text_model=models["TEXT"],
            vision_model=models["VISION"],
            timeout_seconds=timeout,
        )


def openai_instructor_client(*, base_url: str, api_key: str, timeout_seconds: float):
    """Build one OpenAI-compatible Instructor client with SDK retries disabled.

    9Router models may wrap otherwise-valid JSON in a Markdown ``json``
    code block. ``MD_JSON`` extracts that block before Pydantic validation
    while retaining the same structured-output contract.
    """
    import instructor
    from openai import OpenAI

    raw_client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout_seconds,
        max_retries=0,
    )
    return instructor.from_openai(raw_client, mode=instructor.Mode.MD_JSON)


def ninerouter_instructor_client(config: NinerouterConfig | None = None):
    resolved = config or NinerouterConfig.from_env()
    return openai_instructor_client(
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        timeout_seconds=resolved.timeout_seconds,
    )
