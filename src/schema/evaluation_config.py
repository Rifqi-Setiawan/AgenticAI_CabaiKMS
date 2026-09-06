"""Frozen, secret-free identity for one mapping evaluation configuration."""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field


class EvaluationRunConfig(BaseModel):
    source_backend: str = Field(min_length=1)
    retrieval_backend: str = Field(min_length=1)
    retrieval_k: int = Field(ge=1)
    canonical_schema_version: str = Field(min_length=1)
    canonical_template_hash: str = Field(min_length=1)
    mapping_verification_version: str = Field(min_length=1)
    embedding_model_name: str | None = None

    @property
    def fingerprint(self) -> str:
        serialized = json.dumps(
            self.model_dump(mode="json"), ensure_ascii=False,
            sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_evaluation_config_fingerprint(**kwargs: object) -> str:
    return EvaluationRunConfig(**kwargs).fingerprint


def validate_evaluation_config_fingerprint(fingerprint: str, **kwargs: object) -> None:
    expected = build_evaluation_config_fingerprint(**kwargs)
    if fingerprint != expected:
        raise ValueError("evaluation_config_fingerprint does not match recorded run configuration")
