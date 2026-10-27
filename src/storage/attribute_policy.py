"""Attribute dictionary, semantic matching policy, and update rules for CabaiKMS JSONB storage."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import math
import re
from typing import Any, Literal

from pydantic import Field, field_validator

from src.storage.contracts import Contract
from src.storage.document_contracts import AttributeValue


def _normalize_text(text: str) -> str:
    """Normalize text by collapsing whitespace and lowercasing."""
    return " ".join(text.strip().lower().split())


class AttributeDefinition(Contract):
    """Dynamic attribute definition stored in the catalog."""

    attribute_id: str = Field(min_length=1, max_length=64)
    canonical_key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=256)
    organ: str = Field(min_length=1, max_length=64)
    value_type: str = "text"
    unit: str | None = None
    description: str | None = None
    development_stage: str | None = None
    aliases: list[str] = Field(default_factory=list)

    @field_validator("attribute_id", "canonical_key", "label", "organ", mode="before")
    @classmethod
    def _validate_non_empty(cls, v: Any) -> Any:
        if isinstance(v, str):
            trimmed = v.strip()
            if not trimmed:
                raise ValueError("Attribute string field cannot be empty or whitespace only")
            return trimmed
        return v


class AttributeResolution(Contract):
    """Resolution output of an attribute matching evaluation."""

    status: Literal["AUTO_ACCEPT", "NEEDS_REVIEW", "NEW_ATTRIBUTE_REVIEW"]
    attribute_id: str | None = None
    canonical_key: str | None = None
    matched_label: str | None = None
    organ: str | None = None
    confidence: float = 0.0
    reason: str = ""
    raw_label: str
    is_trusted_alias: bool = False
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class HoldoutEvaluationReport(Contract):
    """Holdout evaluation report gating semantic auto-accept rules."""

    report_id: str = Field(min_length=1, max_length=128)
    total_samples: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    coverage: float = Field(ge=0.0, le=1.0)
    disagreement_per_domain: dict[str, float] = Field(default_factory=dict)
    threshold_evaluated: float = 0.85
    is_approved: bool = False
    evaluated_at: datetime


def evaluate_holdout_gate(report: HoldoutEvaluationReport) -> bool:
    """Evaluate whether holdout gate criteria are approved."""
    return bool(report.is_approved)


_SEED_DEFINITIONS: list[AttributeDefinition] | None = None


def _build_seed_definitions() -> list[AttributeDefinition]:
    """Load canonical rows from canonical schema template as initial catalog seed."""
    from src.schema.canonical import CanonicalSchema

    schema = CanonicalSchema.from_template()
    definitions: list[AttributeDefinition] = []

    for r in schema.rows:
        cleaned_label = _normalize_text(r.label)
        attr_id = f"attr_{r.canonical_key}"

        stage: str | None = None
        label_words = cleaned_label.split()
        if "muda" in label_words:
            stage = "muda"
        elif "masak" in label_words:
            stage = "masak"

        val_type = "text"
        unit: str | None = None

        words_set = set(label_words)
        if any(w in words_set for w in ["tinggi", "panjang", "lebar", "keliling"]):
            val_type = "number"
            unit = "cm"
        elif "luas" in words_set:
            val_type = "number"
            unit = "cm2"
        elif "umur" in words_set:
            val_type = "number"
            unit = "hari"
        elif any(w.startswith("jumlah") for w in words_set):
            val_type = "number"
            unit = None

        aliases = [str(a).strip() for a in r.alt_labels if str(a).strip()]

        defn = AttributeDefinition(
            attribute_id=attr_id,
            canonical_key=r.canonical_key,
            label=cleaned_label,
            organ=r.domain,
            value_type=val_type,
            unit=unit,
            development_stage=stage,
            aliases=aliases,
        )
        definitions.append(defn)

    return definitions


def _get_seed_definitions() -> list[AttributeDefinition]:
    """Retrieve isolated deep copies of canonical seed definitions."""
    global _SEED_DEFINITIONS
    if _SEED_DEFINITIONS is None:
        _SEED_DEFINITIONS = _build_seed_definitions()
    return [copy.deepcopy(d) for d in _SEED_DEFINITIONS]


class AttributeCatalog:
    """Dynamic attribute dictionary supporting registration, alias mapping, and lookup."""

    def __init__(
        self,
        seed_definitions: list[AttributeDefinition] | None = None,
        auto_load_canonical: bool = True,
    ) -> None:
        self._by_id: dict[str, AttributeDefinition] = {}
        self._by_label: dict[str, AttributeDefinition] = {}
        self._by_alias: dict[str, AttributeDefinition] = {}

        if seed_definitions is not None:
            for defn in seed_definitions:
                self.register_attribute(defn)
        elif auto_load_canonical:
            for defn in _get_seed_definitions():
                self.register_attribute(defn)

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self):
        return iter(self._by_id.values())

    def has_attribute(self, attribute_id: str) -> bool:
        """Check whether attribute identifier is registered in catalog."""
        return attribute_id in self._by_id

    def get(self, attribute_id: str) -> AttributeDefinition | None:
        """Retrieve attribute definition by attribute identifier."""
        return self._by_id.get(attribute_id)

    def get_by_label(self, label: str) -> AttributeDefinition | None:
        """Retrieve attribute definition by exact normalized label."""
        return self._by_label.get(_normalize_text(label))

    def get_by_alias(self, alias: str) -> AttributeDefinition | None:
        """Retrieve attribute definition by exact normalized alias."""
        return self._by_alias.get(_normalize_text(alias))

    def lookup(self, key: str) -> AttributeDefinition | None:
        """Find attribute definition by ID, canonical label, or alias."""
        if not key or not key.strip():
            return None
        if key in self._by_id:
            return self._by_id[key]
        norm = _normalize_text(key)
        if norm in self._by_label:
            return self._by_label[norm]
        if norm in self._by_alias:
            return self._by_alias[norm]
        return None

    def register_attribute(self, defn: AttributeDefinition) -> AttributeDefinition:
        """Register novel attribute or idempotently confirm existing attribute definition."""
        attr_id = defn.attribute_id.strip()
        if not attr_id:
            raise ValueError("attribute_id cannot be empty")
        if not defn.label.strip():
            raise ValueError("label cannot be empty")

        norm_label = _normalize_text(defn.label)

        if attr_id in self._by_id:
            existing = self._by_id[attr_id]
            if (
                _normalize_text(existing.label) != norm_label
                or existing.organ.strip().lower() != defn.organ.strip().lower()
            ):
                raise ValueError(
                    f"Conflicting attribute registration for ID '{attr_id}': "
                    f"existing ({existing.label}, {existing.organ}) vs new ({defn.label}, {defn.organ})"
                )
            for alias in defn.aliases:
                self.add_alias(attr_id, alias)
            return existing

        if norm_label in self._by_label:
            existing = self._by_label[norm_label]
            if existing.attribute_id != attr_id:
                raise ValueError(
                    f"Label '{defn.label}' collides with existing attribute '{existing.attribute_id}'"
                )

        clean_defn = defn.model_copy(deep=True)
        clean_defn.attribute_id = attr_id
        clean_defn.label = defn.label.strip()

        self._by_id[attr_id] = clean_defn
        self._by_label[norm_label] = clean_defn

        for alias in defn.aliases:
            norm_alias = _normalize_text(alias)
            self._by_alias[norm_alias] = clean_defn

        return clean_defn

    def add_alias(self, attribute_id: str, alias: str) -> None:
        """Register curated synonym for canonical attribute with collision protection."""
        if not alias or not alias.strip():
            raise ValueError("Alias cannot be empty")

        norm_alias = _normalize_text(alias)

        if attribute_id not in self._by_id:
            raise ValueError(f"Attribute ID '{attribute_id}' not found in catalog")

        target = self._by_id[attribute_id]

        for other_id, other_attr in self._by_id.items():
            if other_id != attribute_id:
                if _normalize_text(other_attr.label) == norm_alias:
                    raise ValueError(
                        f"Alias '{alias}' collides with canonical label of attribute '{other_id}'"
                    )
                for existing_alias in other_attr.aliases:
                    if _normalize_text(existing_alias) == norm_alias:
                        raise ValueError(
                            f"Alias '{alias}' collides with existing alias of attribute '{other_id}'"
                        )

        existing_aliases_norm = [_normalize_text(a) for a in target.aliases]
        if norm_alias not in existing_aliases_norm:
            target.aliases.append(alias.strip())

        self._by_alias[norm_alias] = target


def resolve_attribute(
    raw_label: str,
    context: dict[str, Any] | None = None,
    catalog: AttributeCatalog | None = None,
    policy: AttributePolicy | None = None,
) -> AttributeResolution:
    """Resolve raw input label against catalog and policy rules."""
    if not isinstance(raw_label, str) or not raw_label.strip():
        raise ValueError("Attribute label cannot be empty or whitespace only")

    if catalog is None:
        catalog = AttributeCatalog()

    norm_query = _normalize_text(raw_label)

    # 1. Exact label match check
    exact_match = catalog.get_by_label(norm_query)
    if exact_match is not None:
        if context and "organ" in context:
            ctx_organ = str(context["organ"]).strip().lower()
            if exact_match.organ.strip().lower() != ctx_organ:
                return AttributeResolution(
                    status="NEEDS_REVIEW",
                    attribute_id=None,
                    canonical_key=None,
                    matched_label=exact_match.label,
                    organ=exact_match.organ,
                    confidence=0.0,
                    reason=(
                        f"Organ conflict detected: label indicates organ '{exact_match.organ}' "
                        f"but context specifies '{ctx_organ}'"
                    ),
                    raw_label=raw_label,
                    is_trusted_alias=False,
                    candidates=[
                        {
                            "attribute_id": exact_match.attribute_id,
                            "canonical_key": exact_match.canonical_key,
                            "label": exact_match.label,
                            "organ": exact_match.organ,
                        }
                    ],
                )

        return AttributeResolution(
            status="AUTO_ACCEPT",
            attribute_id=exact_match.attribute_id,
            canonical_key=exact_match.canonical_key,
            matched_label=exact_match.label,
            organ=exact_match.organ,
            confidence=1.0,
            reason=f"Exact match on canonical attribute '{exact_match.label}'",
            raw_label=raw_label,
            is_trusted_alias=False,
        )

    # 2. Curated alias match check
    alias_match = catalog.get_by_alias(norm_query)
    if alias_match is not None:
        if context and "organ" in context:
            ctx_organ = str(context["organ"]).strip().lower()
            if alias_match.organ.strip().lower() != ctx_organ:
                return AttributeResolution(
                    status="NEEDS_REVIEW",
                    attribute_id=None,
                    canonical_key=None,
                    matched_label=alias_match.label,
                    organ=alias_match.organ,
                    confidence=0.0,
                    reason=(
                        f"Organ mismatch on alias: alias maps to organ '{alias_match.organ}' "
                        f"but context specifies '{ctx_organ}'"
                    ),
                    raw_label=raw_label,
                    is_trusted_alias=True,
                    candidates=[
                        {
                            "attribute_id": alias_match.attribute_id,
                            "canonical_key": alias_match.canonical_key,
                            "label": alias_match.label,
                            "organ": alias_match.organ,
                        }
                    ],
                )

        return AttributeResolution(
            status="AUTO_ACCEPT",
            attribute_id=alias_match.attribute_id,
            canonical_key=alias_match.canonical_key,
            matched_label=alias_match.label,
            organ=alias_match.organ,
            confidence=1.0,
            reason=f"Matched trusted curated alias for '{alias_match.label}'",
            raw_label=raw_label,
            is_trusted_alias=True,
        )

    # 3. Contextual disambiguation for generic metrics
    if context:
        ctx_organ = str(context.get("organ", "")).strip().lower()
        ctx_stage = str(context.get("stage", "")).strip().lower()

        if ctx_organ and ctx_stage:
            target_label = f"{norm_query} {ctx_organ} {ctx_stage}"
            target_attr = catalog.get_by_label(target_label)
            if target_attr is not None:
                return AttributeResolution(
                    status="AUTO_ACCEPT",
                    attribute_id=target_attr.attribute_id,
                    canonical_key=target_attr.canonical_key,
                    matched_label=target_attr.label,
                    organ=target_attr.organ,
                    confidence=1.0,
                    reason=(
                        f"Generic metric '{norm_query}' disambiguated by organ '{ctx_organ}' "
                        f"and stage '{ctx_stage}' to '{target_attr.label}'"
                    ),
                    raw_label=raw_label,
                    is_trusted_alias=False,
                )

            # Fallback: exact word set match without sub-organ parts
            exact_set = {norm_query, ctx_organ, ctx_stage}
            for attr in catalog:
                words = set(_normalize_text(attr.label).split())
                if words == exact_set:
                    return AttributeResolution(
                        status="AUTO_ACCEPT",
                        attribute_id=attr.attribute_id,
                        canonical_key=attr.canonical_key,
                        matched_label=attr.label,
                        organ=attr.organ,
                        confidence=1.0,
                        reason=(
                            f"Generic metric '{norm_query}' disambiguated by organ '{ctx_organ}' "
                            f"and stage '{ctx_stage}' to '{attr.label}'"
                        ),
                        raw_label=raw_label,
                        is_trusted_alias=False,
                    )

        if ctx_organ and not ctx_stage:
            primary_label = f"{norm_query} {ctx_organ}"
            target_attr = catalog.get_by_label(primary_label)
            if target_attr is not None:
                return AttributeResolution(
                    status="AUTO_ACCEPT",
                    attribute_id=target_attr.attribute_id,
                    canonical_key=target_attr.canonical_key,
                    matched_label=target_attr.label,
                    organ=target_attr.organ,
                    confidence=1.0,
                    reason=(
                        f"Generic metric '{norm_query}' disambiguated by organ '{ctx_organ}' "
                        f"to '{target_attr.label}'"
                    ),
                    raw_label=raw_label,
                    is_trusted_alias=False,
                )

    # 4. Partial candidate search for ambiguous labels
    query_words = set(norm_query.split())

    matching_candidates: list[AttributeDefinition] = []
    for attr in catalog:
        attr_words = set(_normalize_text(attr.label).split())
        if query_words.issubset(attr_words):
            matching_candidates.append(attr)

    if matching_candidates:
        cand_list = [
            {
                "attribute_id": c.attribute_id,
                "canonical_key": c.canonical_key,
                "label": c.label,
                "organ": c.organ,
                "stage": c.development_stage,
            }
            for c in matching_candidates
        ]
        return AttributeResolution(
            status="NEEDS_REVIEW",
            attribute_id=None,
            canonical_key=None,
            matched_label=None,
            organ=matching_candidates[0].organ if len({c.organ for c in matching_candidates}) == 1 else None,
            confidence=0.5,
            reason=(
                f"Ambiguous attribute match for '{raw_label}': multiple candidates identified, "
                f"human review required"
            ),
            raw_label=raw_label,
            is_trusted_alias=False,
            candidates=cand_list,
        )

    # 5. Overlapping token inspection or novel attribute classification
    biological_anchor_tokens = {
        "panjang", "lebar", "tinggi", "keliling", "luas", "warna", "bentuk",
        "daun", "buah", "bunga", "biji", "batang", "habitus", "umur", "kelopak", "tangkai"
    }

    if query_words & biological_anchor_tokens:
        partial_candidates: list[dict[str, Any]] = []
        for c in catalog:
            c_words = set(_normalize_text(c.label).split())
            if query_words & c_words:
                partial_candidates.append(
                    {
                        "attribute_id": c.attribute_id,
                        "canonical_key": c.canonical_key,
                        "label": c.label,
                        "organ": c.organ,
                        "stage": c.development_stage,
                    }
                )
        return AttributeResolution(
            status="NEEDS_REVIEW",
            attribute_id=None,
            canonical_key=None,
            matched_label=None,
            organ=partial_candidates[0]["organ"] if partial_candidates else None,
            confidence=0.2,
            reason=(
                f"Uncertain attribute match for '{raw_label}': partial tokens detected, "
                f"human review required"
            ),
            raw_label=raw_label,
            is_trusted_alias=False,
            candidates=partial_candidates,
        )

    return AttributeResolution(
        status="NEW_ATTRIBUTE_REVIEW",
        attribute_id=None,
        canonical_key=None,
        matched_label=None,
        organ=None,
        confidence=0.0,
        reason=f"Novel attribute '{raw_label}' not found in canonical catalog: requires dictionary review",
        raw_label=raw_label,
        is_trusted_alias=False,
        candidates=[],
    )


class AttributePolicy:
    """Attribute mapping policy evaluator and overwrite controller."""

    def __init__(
        self,
        semantic_auto_accept_enabled: bool = False,
        holdout_report_approved: bool = False,
        semantic_threshold: float = 0.85,
        catalog: AttributeCatalog | None = None,
    ) -> None:
        if semantic_auto_accept_enabled and not holdout_report_approved:
            raise ValueError(
                "Cannot enable semantic auto accept without approved holdout evaluation report"
            )
        self.semantic_auto_accept_enabled = semantic_auto_accept_enabled
        self.holdout_report_approved = holdout_report_approved
        self.semantic_threshold = semantic_threshold
        self.catalog = catalog or AttributeCatalog()

    def enable_semantic_auto_accept(self, report: HoldoutEvaluationReport) -> None:
        """Activate semantic auto-accept gate upon approved holdout evaluation report."""
        if not report.is_approved:
            raise ValueError(
                f"Cannot enable semantic auto accept: report {report.report_id} is not approved"
            )
        self.holdout_report_approved = True
        self.semantic_auto_accept_enabled = True
        self.semantic_threshold = report.threshold_evaluated

    def evaluate(
        self,
        raw_label: str,
        catalog: AttributeCatalog | None = None,
        semantic_score: float | None = None,
        context: dict[str, Any] | None = None,
    ) -> AttributeResolution:
        """Evaluate raw label against exact catalog, alias index, and semantic holdout gate."""
        cat = catalog or self.catalog
        direct_res = resolve_attribute(raw_label, context=context, catalog=cat)

        if direct_res.status == "AUTO_ACCEPT":
            return direct_res

        # Gate check for semantic similarity scoring
        if not (self.semantic_auto_accept_enabled and self.holdout_report_approved):
            return AttributeResolution(
                status="NEEDS_REVIEW",
                attribute_id=None,
                canonical_key=None,
                matched_label=None,
                organ=None,
                confidence=float(semantic_score)
                if (semantic_score is not None and isinstance(semantic_score, (int, float)) and not math.isnan(semantic_score) and semantic_score >= 0)
                else 0.0,
                reason=(
                    "Semantic auto-accept held in review: holdout evaluation report gate "
                    "is not approved (HITL required)"
                ),
                raw_label=raw_label,
                is_trusted_alias=False,
                candidates=direct_res.candidates,
            )

        # Fail closed on invalid score
        if (
            semantic_score is None
            or not isinstance(semantic_score, (int, float))
            or math.isnan(semantic_score)
            or semantic_score < 0
        ):
            return AttributeResolution(
                status="NEEDS_REVIEW",
                attribute_id=None,
                canonical_key=None,
                matched_label=None,
                organ=None,
                confidence=0.0,
                reason="Evaluator anomaly: semantic score is invalid, missing, or negative (fail-closed to review)",
                raw_label=raw_label,
                is_trusted_alias=False,
                candidates=direct_res.candidates,
            )

        if semantic_score >= self.semantic_threshold:
            best_cand = self._find_best_candidate(raw_label, cat, context=context)
            if best_cand is not None:
                return AttributeResolution(
                    status="AUTO_ACCEPT",
                    attribute_id=best_cand.attribute_id,
                    canonical_key=best_cand.canonical_key,
                    matched_label=best_cand.label,
                    organ=best_cand.organ,
                    confidence=float(semantic_score),
                    reason=(
                        f"Semantic match auto-accepted (score {semantic_score:.2f} >= "
                        f"threshold {self.semantic_threshold:.2f})"
                    ),
                    raw_label=raw_label,
                    is_trusted_alias=False,
                )

        return AttributeResolution(
            status="NEEDS_REVIEW",
            attribute_id=None,
            canonical_key=None,
            matched_label=None,
            organ=None,
            confidence=float(semantic_score),
            reason=(
                f"Semantic match score {semantic_score:.2f} below auto-accept "
                f"threshold {self.semantic_threshold:.2f}"
            ),
            raw_label=raw_label,
            is_trusted_alias=False,
            candidates=direct_res.candidates,
        )

    def _find_best_candidate(
        self,
        raw_label: str,
        catalog: AttributeCatalog,
        context: dict[str, Any] | None = None,
    ) -> AttributeDefinition | None:
        """Identify closest matching attribute from catalog for semantic alignment."""
        norm_query = _normalize_text(raw_label)
        query_words = set(norm_query.split())

        candidates = list(catalog)
        if context and "organ" in context:
            ctx_organ = str(context["organ"]).strip().lower()
            filtered = [c for c in candidates if c.organ.lower() == ctx_organ]
            if filtered:
                candidates = filtered

        best_attr: AttributeDefinition | None = None
        best_score = -1.0

        for attr in candidates:
            attr_words = set(_normalize_text(attr.label).split())
            for alias in attr.aliases:
                attr_words.update(_normalize_text(alias).split())

            intersection = query_words & attr_words
            if intersection:
                score = len(intersection) / len(query_words | attr_words)
                if attr.organ.lower() in query_words:
                    score += 0.5
                if score > best_score:
                    best_score = score
                    best_attr = attr

        return best_attr

    def overwrite_block_reason(
        self, existing: AttributeValue, incoming: AttributeValue
    ) -> str | None:
        """Evaluate why incoming measurement cannot overwrite existing current value."""
        if incoming.resolution != "AUTO_ACCEPT":
            return "INCOMING_NOT_AUTO_ACCEPT"

        if existing.resolution != "AUTO_ACCEPT":
            return "EXISTING_HUMAN_PROTECTED"

        if existing.value_type != incoming.value_type:
            return "TYPE_MISMATCH"

        if existing.unit is not None and incoming.unit is not None:
            if not self._units_compatible(existing.unit, incoming.unit):
                return "UNIT_INCOMPATIBLE"

        if not self._attributes_compatible(existing.label, incoming.label):
            return "LABEL_INCOMPATIBLE"

        return None

    def can_overwrite(self, existing: AttributeValue, incoming: AttributeValue) -> bool:
        """Evaluate whether incoming measurement can overwrite existing current value."""
        return self.overwrite_block_reason(existing, incoming) is None

    @staticmethod
    def _units_compatible(u1: str, u2: str) -> bool:
        """Check compatibility between dimension measurement units."""
        norm1 = u1.strip().lower()
        norm2 = u2.strip().lower()
        if norm1 == norm2:
            return True

        length_units = {"cm", "mm", "m", "meter", "centimeter", "millimeter"}
        mass_units = {"kg", "g", "gram", "mg", "kilogram", "milligram"}
        percent_units = {"%"}
        temp_units = {"oc", "c", "celcius", "celsius", "°c"}
        spad_units = {"spad"}

        categories = [length_units, mass_units, percent_units, temp_units, spad_units]
        for cat in categories:
            if norm1 in cat and norm2 in cat:
                return True
            if (norm1 in cat and norm2 not in cat) or (norm2 in cat and norm1 not in cat):
                return False

        return norm1 == norm2

    def _attributes_compatible(self, label1: str, label2: str) -> bool:
        """Check whether two attribute labels resolve to identical canonical identity."""
        if _normalize_text(label1) == _normalize_text(label2):
            return True

        res1 = resolve_attribute(label1, catalog=self.catalog)
        res2 = resolve_attribute(label2, catalog=self.catalog)

        if res1.attribute_id and res2.attribute_id:
            return res1.attribute_id == res2.attribute_id

        return False


def can_overwrite_attribute_value(
    existing: AttributeValue,
    incoming: AttributeValue,
    policy: AttributePolicy | None = None,
) -> bool:
    """Module-level function evaluating whether incoming value can overwrite existing value."""
    if policy is None:
        policy = AttributePolicy()
    return policy.can_overwrite(existing, incoming)


def overwrite_block_reason(
    existing: AttributeValue,
    incoming: AttributeValue,
    policy: AttributePolicy | None = None,
) -> str | None:
    """Module-level function evaluating why incoming value cannot overwrite existing value."""
    if policy is None:
        policy = AttributePolicy()
    return policy.overwrite_block_reason(existing, incoming)
