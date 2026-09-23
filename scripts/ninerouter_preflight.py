"""Opt-in live capability check for the local Windows 9Router instance."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from pydantic import BaseModel

from src.llm.openai_compatible import (
    NINEROUTER_REQUIRED_TEXT_MODEL,
    NINEROUTER_REQUIRED_VISION_MODEL,
    NinerouterConfig,
)
from src.llm.providers import call_ninerouter_text
from src.llm.vision_providers import call_ninerouter_vision
from src.reliability.provider_failures import ProviderCallError, classify_ninerouter_exception

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMAGE_FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "ninerouter_preflight_image.b64"


class TextProbe(BaseModel):
    ok: bool


class VisionProbe(BaseModel):
    image_present: bool


def _diagnostic(label: str, ok: bool, detail: str) -> None:
    print(f"{label}: {'PASS' if ok else 'FAIL'} — {detail}")


def _reachable(url: str, timeout: float) -> bool:
    try:
        with urlopen(url, timeout=timeout):  # noqa: S310 - fixed local URL from validated config
            return True
    except HTTPError:
        # Any HTTP response proves the local TCP/HTTP endpoint is reachable.
        return True
    except (URLError, TimeoutError, OSError):
        return False


def _models(config: NinerouterConfig) -> set[str]:
    request = Request(
        f"{config.base_url}/models",
        headers={"Authorization": f"Bearer {config.api_key}"},
        method="GET",
    )
    with urlopen(request, timeout=config.timeout_seconds) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    return {
        item.get("id")
        for item in payload.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def run_preflight() -> bool:
    load_dotenv(PROJECT_ROOT / ".env")
    try:
        config = NinerouterConfig.from_env()
    except ProviderCallError as exc:
        _diagnostic("configuration", False, exc.failure_kind.value)
        return False

    origin = config.base_url.removesuffix("/v1")
    reachable = _reachable(origin, min(config.timeout_seconds, 5))
    _diagnostic("endpoint_reachable", reachable, origin)
    if not reachable:
        return False

    try:
        models = _models(config)
    except Exception as exc:  # noqa: BLE001 - sanitized live diagnostic boundary
        kind = classify_ninerouter_exception(exc)
        _diagnostic("models_endpoint", False, kind.value)
        return False
    text_model_found = NINEROUTER_REQUIRED_TEXT_MODEL in models
    _diagnostic("text_model", text_model_found, NINEROUTER_REQUIRED_TEXT_MODEL)
    vision_model_found = NINEROUTER_REQUIRED_VISION_MODEL in models
    _diagnostic("vision_model", vision_model_found, NINEROUTER_REQUIRED_VISION_MODEL)
    if not text_model_found or not vision_model_found:
        return False

    try:
        text = call_ninerouter_text(
            response_model=TextProbe,
            messages=[{
                "role": "user",
                "content": "Return structured JSON with ok=true.",
            }],
            max_retries=0,
        )
        text_ok = text.ok is True
        _diagnostic("structured_text", text_ok, "Pydantic validation succeeded" if text_ok else "unexpected value")
    except Exception as exc:  # noqa: BLE001
        kind = getattr(exc, "failure_kind", None)
        detail = kind.value if kind is not None else "invalid_structured_output"
        _diagnostic("structured_text", False, detail)
        return False

    try:
        fixture_b64 = IMAGE_FIXTURE.read_text(encoding="ascii").strip()
        # Decode once to verify the committed fixture itself before sending it.
        base64.b64decode(fixture_b64, validate=True)
        vision = call_ninerouter_vision(
            response_model=VisionProbe,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Return image_present=true if an image is attached."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{fixture_b64}"}},
                ],
            }],
            max_retries=0,
        )
        vision_ok = vision.image_present is True
        _diagnostic("multimodal_vision", vision_ok, "Pydantic validation succeeded" if vision_ok else "image not recognized")
    except Exception as exc:  # noqa: BLE001
        kind = getattr(exc, "failure_kind", None)
        detail = kind.value if kind is not None else "vision_or_structured_output_incompatible"
        _diagnostic("multimodal_vision", False, detail)
        return False
    return True


def main() -> int:
    return 0 if run_preflight() else 1


if __name__ == "__main__":
    sys.exit(main())
