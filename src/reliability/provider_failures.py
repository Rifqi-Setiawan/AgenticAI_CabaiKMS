"""Small, provider-neutral failure taxonomy for application-level retries."""

from __future__ import annotations

from enum import Enum


class ProviderFailureKind(str, Enum):
    RETRYABLE_TRANSIENT = "retryable_transient"
    NON_RETRYABLE_CONFIGURATION = "non_retryable_configuration"
    NON_RETRYABLE_REQUEST = "non_retryable_request"


class ProviderCallError(Exception):
    """A sanitized provider failure with an explicit retry contract."""

    def __init__(
        self,
        message: str,
        *,
        failure_kind: ProviderFailureKind = ProviderFailureKind.NON_RETRYABLE_REQUEST,
    ) -> None:
        super().__init__(message)
        self.failure_kind = failure_kind

    @property
    def retryable(self) -> bool:
        return self.failure_kind is ProviderFailureKind.RETRYABLE_TRANSIENT

    @property
    def terminal_reason(self) -> str:
        if self.retryable:
            return "provider_retry_exhausted"
        if self.failure_kind is ProviderFailureKind.NON_RETRYABLE_CONFIGURATION:
            return "provider_configuration_error"
        return "provider_request_error"


def _status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return status if isinstance(status, int) else None


def classify_provider_exception(exc: BaseException) -> ProviderFailureKind:
    """Classify using structured exception data, conservatively by default."""
    if isinstance(exc, ProviderCallError):
        return exc.failure_kind
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return ProviderFailureKind.RETRYABLE_TRANSIENT

    # OpenAI-compatible and HTTP client SDKs do not consistently inherit
    # from the built-in connection/timeout exceptions. Their exception
    # classes are still structured signals and avoid parsing error text.
    exception_types = {cls.__name__ for cls in type(exc).__mro__}
    if exception_types & {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
    }:
        return ProviderFailureKind.RETRYABLE_TRANSIENT

    status = _status_code(exc)
    if status in {408, 409, 429} or (status is not None and status >= 500):
        return ProviderFailureKind.RETRYABLE_TRANSIENT
    if status in {401, 403, 404}:
        return ProviderFailureKind.NON_RETRYABLE_CONFIGURATION
    return ProviderFailureKind.NON_RETRYABLE_REQUEST


def combine_failure_kinds(kinds: list[ProviderFailureKind]) -> ProviderFailureKind:
    """A fallback chain is retryable only when every failed path is transient."""
    if kinds and all(kind is ProviderFailureKind.RETRYABLE_TRANSIENT for kind in kinds):
        return ProviderFailureKind.RETRYABLE_TRANSIENT
    if ProviderFailureKind.NON_RETRYABLE_CONFIGURATION in kinds:
        return ProviderFailureKind.NON_RETRYABLE_CONFIGURATION
    return ProviderFailureKind.NON_RETRYABLE_REQUEST


def provider_error_summary(provider: str, exc: BaseException) -> str:
    """Return useful structured context without provider payloads or credentials."""
    if isinstance(exc, ProviderCallError):
        detail = str(exc)
    else:
        status = _status_code(exc)
        detail = type(exc).__name__
        if status is not None:
            detail += f" (status={status})"
    return f"{provider}: {detail}"
