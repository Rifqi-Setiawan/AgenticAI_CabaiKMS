from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Sha256 = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Key = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_]{0,159}$')]
Organ = Literal['habitus', 'daun', 'batang', 'bunga', 'buah', 'biji']
ValueType = Literal['text', 'number', 'range', 'boolean', 'list']


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def normalize_identity(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, validate_assignment=True)


class CharacteristicInput(Contract):
    canonical_key: Key
    label_id: str = Field(min_length=1, max_length=256)
    organ_domain: Organ | None = None
    source_domain: str = Field(min_length=1, max_length=64)
    data_type: Literal['text', 'number', 'boolean', 'image', 'location'] = 'text'
    standard_unit: str | None = Field(default=None, max_length=32)
    description: str = Field(default='', max_length=4000)


class VarietyInput(Contract):
    canonical_name: str = Field(min_length=1, max_length=256)
    local_aliases: list[str] = Field(default_factory=list, max_length=100)
    origin_region: str | None = Field(default=None, max_length=256)
    acquisition_date: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator('canonical_name')
    @classmethod
    def normalized_name(cls, value: str) -> str:
        value = normalize_identity(value)
        if not value:
            raise ValueError('Empty variety identity.')
        return value


class ValueInput(Contract):
    variety_name: str
    canonical_key: Key
    normalized_value: Any
    raw_source_value: Any
    value_type: ValueType = 'text'
    is_multi_value: bool = False
    confidence_score: float = Field(ge=0, le=1)
    status: Literal['AUTO_ACCEPT', 'HUMAN_REVIEW']
    provenance: list[dict[str, Any]] = Field(min_length=1, max_length=10000)

    @field_validator('variety_name')
    @classmethod
    def identity(cls, value: str) -> str:
        return normalize_identity(value)

    @model_validator(mode='after')
    def value_shape(self) -> 'ValueInput':
        value = self.normalized_value
        is_number = lambda x: type(x) in (int, float) and math.isfinite(x)
        valid = {
            'text': lambda: isinstance(value, str) and bool(value.strip()),
            'number': lambda: is_number(value),
            'boolean': lambda: type(value) is bool,
            'range': lambda: isinstance(value, dict) and set(value) == {'min', 'max'}
            and is_number(value['min']) and is_number(value['max']) and value['min'] <= value['max'],
            'list': lambda: isinstance(value, list) and len(value) > 0
            and all(isinstance(v, (str, int, float, bool)) and (not isinstance(v, float) or math.isfinite(v)) for v in value),
        }[self.value_type]()
        if not valid or self.is_multi_value != (self.value_type == 'list'):
            raise ValueError('normalized_value/value_type/is_multi_value mismatch.')
        canonical_json(self.model_dump(mode='json'))
        return self


class ReviewInput(Contract):
    item_id: str = Field(min_length=1, max_length=256)
    source_label: str = Field(min_length=1, max_length=1024)
    source_context: str = Field(default='', max_length=4096)
    status: Literal['pending', 'approved', 'revised', 'no_match']
    final_canonical_key: Key | None = None
    proposed_canonical_key: Key | None = None
    reported_reviewer: str | None = None
    notes: str | None = Field(default=None, max_length=8192)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def target_required(self) -> 'ReviewInput':
        if self.status in {'approved', 'revised'} and self.final_canonical_key is None:
            raise ValueError('Resolved positive review needs a canonical key.')
        if self.status in {'pending', 'no_match'} and self.final_canonical_key is not None:
            raise ValueError('Pending / NO_MATCH must not have a final target.')
        return self


class ImageInput(Contract):
    variety_name: str
    organ_part: Organ
    asset_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    vision_confidence: float = Field(ge=0, le=1)
    vision_evidence: dict[str, Any] = Field(default_factory=dict)
    classification_status: Literal['KNOWN'] = 'KNOWN'

    @field_validator('variety_name')
    @classmethod
    def identity(cls, value: str) -> str:
        return normalize_identity(value)


class RunDraft(Contract):
    run_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,160}$')
    source_filename: str = Field(min_length=1, max_length=512)
    file_sha256: Sha256
    source_uri: str | None = None
    source_scope: str = Field(min_length=1, max_length=160)
    schema_version: str = Field(min_length=1, max_length=128)
    template_hash: Sha256
    config_fingerprint: str = Field(min_length=1, max_length=256)
    executed_at: datetime | None = None
    execution_duration_ms: int | None = Field(default=None, ge=0)
    total_attributes: int = Field(ge=0)
    auto_accepted_count: int = Field(ge=0)
    reviewed_count: int = Field(ge=0)
    characteristics: list[CharacteristicInput] = Field(min_length=1, max_length=5000)
    varieties: list[VarietyInput] = Field(min_length=1, max_length=10000)
    values: list[ValueInput] = Field(default_factory=list, max_length=100000)
    reviews: list[ReviewInput] = Field(default_factory=list, max_length=10000)
    images: list[ImageInput] = Field(default_factory=list, max_length=10000)
    # Trusted source summaries, not arbitrary logs / provider API responses.
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def referential_integrity(self) -> 'RunDraft':
        catalog = {x.canonical_key: x for x in self.characteristics}
        names = {x.canonical_name for x in self.varieties}
        if len(catalog) != len(self.characteristics) or len(names) != len(self.varieties):
            raise ValueError('Duplicate canonical keys or normalized variety names.')
        pairs = [(x.variety_name, x.canonical_key) for x in self.values]
        if len(pairs) != len(set(pairs)):
            raise ValueError('Aggregate one current projection per variety/character before staging.')
        if len({r.item_id for r in self.reviews}) != len(self.reviews):
            raise ValueError('Duplicate review item IDs.')
        for value in self.values:
            if value.variety_name not in names or value.canonical_key not in catalog:
                raise ValueError('Value references an unknown variety or characteristic.')
            data_type = catalog[value.canonical_key].data_type
            if data_type == 'image':
                raise ValueError('Images belong in plant_images, not the value table.')
            if data_type == 'number' and value.value_type not in {'number', 'range', 'list'}:
                raise ValueError('Numeric characteristic needs a typed numeric value.')
            if data_type == 'number' and value.value_type == 'list' and not all(type(v) in (int, float) for v in value.normalized_value):
                raise ValueError('Numeric lists must contain only numbers.')
            if data_type == 'boolean' and value.value_type != 'boolean':
                raise ValueError('Boolean characteristic needs a boolean value.')
        for review in self.reviews:
            if review.final_canonical_key and review.final_canonical_key not in catalog:
                raise ValueError('Review target absent from active schema.')
        if any(image.variety_name not in names for image in self.images):
            raise ValueError('Image references an unknown variety.')
        if self.reviewed_count != sum(review.status != 'pending' for review in self.reviews):
            raise ValueError('reviewed_count must match resolved review decisions.')
        if self.auto_accepted_count + self.reviewed_count > self.total_attributes:
            raise ValueError('Run counters exceed total attributes.')
        if self.executed_at and self.executed_at.tzinfo is None:
            raise ValueError('executed_at must be timezone-aware; do not invent timestamps.')
        canonical_json(self.model_dump(mode='json'))
        return self

    def ordered_payload(self) -> dict[str, Any]:
        result = self.model_dump(mode='json')
        for field, key in [('characteristics', 'canonical_key'), ('varieties', 'canonical_name'), ('reviews', 'item_id')]:
            result[field] = sorted(result[field], key=lambda item: item[key])
        result['values'] = sorted(result['values'], key=lambda item: (item['variety_name'], item['canonical_key']))
        result['images'] = sorted(result['images'], key=lambda item: (item['variety_name'], item['organ_part'], item['asset_id']))
        return result

    def fingerprint(self) -> str:
        return digest_json(self.ordered_payload())


class StageRequest(Contract):
    draft: RunDraft
    expected_revision: int = Field(default=0, ge=0)


class CommitRequest(Contract):
    expected_revision: int = Field(ge=1)
    payload_sha256: Sha256


class RebaseRequest(Contract):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=10, max_length=2000)


class PromoteAliasRequest(Contract):
    gold_id: str
    evaluation_reference: str = Field(min_length=10, max_length=1000)
    reason: str = Field(min_length=10, max_length=2000)
