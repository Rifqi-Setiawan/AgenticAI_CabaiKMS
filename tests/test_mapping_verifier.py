import pytest

from src.agents.schema_matching.exact_match import (
    ExactNameResolution,
    ExactNameStatus,
    resolve_exact_name,
)
from src.agents.schema_matching.mapping_verifier import (
    combine_mapping_acceptance,
    verify_mapping,
)
from src.agents.schema_matching.review_queue import (
    AcceptanceStatus,
    decide_mapping_acceptance,
)
from src.agents.schema_matching.retrieval import RetrievalHit, SourceAttributeProfile
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import NULL_ROW, SchemaMapping
from src.schema.mapping_verification import MappingVerificationStatus


@pytest.fixture(scope="module")
def schema():
    return CanonicalSchema.from_template()


def _profile(name="Unknown", context=None):
    return SourceAttributeProfile(name, structural_context=context)


def _mapping(target, *, name="Unknown", context=None, source_format="row-oriented", confidence=0.9):
    return SchemaMapping(
        source_attribute=name,
        source_context=context,
        source_format=source_format,
        target_canonical_row=target,
        confidence=confidence,
        reasoning="test proposal",
        normalization_required=True,
    )


def _hits(schema, row_ids=("r_1", "r_2", "r_3"), distances=(0.10, 0.15, 0.40)):
    return [
        RetrievalHit(
            row_id=row_id,
            label=schema.row_by_id(row_id).label,
            domain=schema.row_by_id(row_id).domain,
            distance=distance,
            canonical_key=schema.row_by_id(row_id).canonical_key,
        )
        for row_id, distance in zip(row_ids, distances)
    ]


def _no_match():
    return ExactNameResolution(ExactNameStatus.NO_MATCH, "unknown")


def _verify(schema, mapping, *, profile=None, method="retrieve_rerank", candidates=None,
            resolution=None, source_format="row-oriented", patch=None):
    return verify_mapping(
        profile=profile or _profile(),
        mapping=mapping,
        mapping_method=method,
        schema=schema,
        exact_resolution=resolution or _no_match(),
        candidates=candidates,
        source_format=source_format,
        reliability_patch=patch,
    )


def test_consistent_unique_exact_mapping_passes_without_retrieval(schema):
    row = schema.rows[0]
    profile = _profile(row.label)
    resolution = resolve_exact_name(row.label, schema)
    result = _verify(
        schema,
        _mapping(row.id, name=row.label),
        profile=profile,
        method="exact_name",
        candidates=None,
        resolution=resolution,
    )
    assert result.status is MappingVerificationStatus.PASS
    assert result.retrieval_evidence is None
    assert result.proposed_target_canonical_key == row.canonical_key


def test_exact_target_disagreement_is_rejected(schema):
    resolution = resolve_exact_name(schema.rows[0].label, schema)
    result = _verify(
        schema,
        _mapping(schema.rows[1].id, name=schema.rows[0].label),
        profile=_profile(schema.rows[0].label),
        method="exact_name",
        resolution=resolution,
    )
    assert result.status is MappingVerificationStatus.REJECT
    assert "EXACT_RESOLUTION_TARGET_MISMATCH" in result.hard_issue_codes


def test_exact_method_with_null_target_is_hard_mismatch(schema):
    row = schema.rows[0]
    resolution = resolve_exact_name(row.label, schema)
    result = _verify(
        schema,
        _mapping(NULL_ROW, name=row.label),
        profile=_profile(row.label),
        method="exact_name",
        resolution=resolution,
    )
    assert result.status is MappingVerificationStatus.REJECT
    assert "EXACT_RESOLUTION_TARGET_MISMATCH" in result.hard_issue_codes


def test_top1_target_passes_and_records_full_precision_math(schema):
    result = _verify(schema, _mapping("r_1"), candidates=_hits(schema))
    evidence = result.retrieval_evidence
    assert result.status is MappingVerificationStatus.PASS
    assert evidence.target_rank == 1
    assert evidence.target_distance == 0.10
    assert evidence.top1_distance == 0.10
    assert evidence.top2_distance == 0.15
    assert evidence.top1_top2_margin == pytest.approx(0.05)
    assert evidence.target_vs_top1_distance_gap == pytest.approx(0.0)


def test_lower_rank_target_is_observational_warning_not_review(schema):
    result = _verify(schema, _mapping("r_3"), candidates=_hits(schema))
    assert result.status is MappingVerificationStatus.PASS
    assert "TARGET_NOT_RETRIEVAL_TOP1" in result.warning_codes
    assert result.retrieval_evidence.target_rank == 3
    assert result.retrieval_evidence.target_distance == 0.40
    assert result.retrieval_evidence.target_vs_top1_distance_gap == pytest.approx(0.30)


def test_rank2_distance_gap_definition(schema):
    result = _verify(schema, _mapping("r_2"), candidates=_hits(schema))
    evidence = result.retrieval_evidence
    assert evidence.target_rank == 2
    assert evidence.target_distance == 0.15
    assert evidence.target_vs_top1_distance_gap == pytest.approx(0.05)


def test_target_outside_candidates_is_rejected(schema):
    result = _verify(schema, _mapping("r_40"), candidates=_hits(schema))
    assert result.status is MappingVerificationStatus.REJECT
    assert "TARGET_NOT_IN_RETRIEVED_CANDIDATES" in result.hard_issue_codes
    assert result.retrieval_evidence.target_in_candidates is False


def test_empty_candidates_for_non_null_mapping_is_rejected(schema):
    result = _verify(schema, _mapping("r_1"), candidates=[])
    assert result.status is MappingVerificationStatus.REJECT
    assert result.hard_issue_codes == ["RETRIEVAL_CANDIDATES_EMPTY"]


def test_duplicate_candidate_ids_are_rejected(schema):
    hits = _hits(schema, row_ids=("r_1", "r_1"), distances=(0.1, 0.2))
    result = _verify(schema, _mapping("r_1"), candidates=hits)
    assert result.status is MappingVerificationStatus.REJECT
    assert "DUPLICATE_RETRIEVAL_CANDIDATE" in result.hard_issue_codes


def test_null_target_is_review_without_candidate_checks(schema):
    result = _verify(schema, _mapping(NULL_ROW), candidates=None)
    assert result.status is MappingVerificationStatus.REVIEW
    assert result.warning_codes == ["NULL_TARGET"]
    assert result.retrieval_evidence is None


def test_missing_mapping_is_rejected(schema):
    result = _verify(schema, None, candidates=_hits(schema))
    assert result.status is MappingVerificationStatus.REJECT
    assert result.hard_issue_codes == ["MAPPING_MISSING"]


def test_source_format_mismatch_is_rejected(schema):
    result = _verify(
        schema,
        _mapping("r_1", source_format="transposed"),
        candidates=_hits(schema),
        source_format="row-oriented",
    )
    assert "SOURCE_FORMAT_MISMATCH" in result.hard_issue_codes


def test_source_attribute_mismatch_is_soft_review(schema):
    result = _verify(
        schema,
        _mapping("r_1", name="Different"),
        profile=_profile("Original"),
        candidates=_hits(schema),
    )
    assert result.status is MappingVerificationStatus.REVIEW
    assert "SOURCE_ATTRIBUTE_MISMATCH" in result.warning_codes


@pytest.mark.parametrize(
    "mapping_context,expected",
    [(None, "SOURCE_CONTEXT_DROPPED"), ("Other", "SOURCE_CONTEXT_MISMATCH")],
)
def test_source_context_inconsistency_is_soft_review(schema, mapping_context, expected):
    result = _verify(
        schema,
        _mapping("r_1", context=mapping_context),
        profile=_profile(context="Morphology"),
        candidates=_hits(schema),
    )
    assert result.status is MappingVerificationStatus.REVIEW
    assert expected in result.warning_codes


def test_exact_collision_warning_is_observational(schema):
    resolution = ExactNameResolution(
        ExactNameStatus.AMBIGUOUS,
        "length",
        candidate_row_ids=("r_1", "r_2"),
        candidate_canonical_keys=("first", "second"),
    )
    result = _verify(
        schema,
        _mapping("r_1"),
        candidates=_hits(schema),
        resolution=resolution,
    )
    assert result.status is MappingVerificationStatus.PASS
    assert "EXACT_NAME_COLLISION_RESOLVED_SEMANTICALLY" in result.warning_codes
    assert result.exact_candidate_canonical_keys == ["first", "second"]


def test_reliability_patch_is_review_signal(schema):
    result = _verify(
        schema,
        _mapping("r_1"),
        candidates=_hits(schema),
        patch={"error_trace": ["sanitized issue"]},
    )
    assert result.status is MappingVerificationStatus.REVIEW
    assert "RERANK_RELIABILITY_PATCH" in result.warning_codes


def test_verifier_does_not_mutate_structure_aware_profile(schema):
    profile = SourceAttributeProfile(
        "Unknown",
        structural_context="Morphology",
        header_path=["Morphology", "Unknown"],
        source_value_type="numeric",
        source_attribute_id="Sheet1!COL:D",
    )
    before = (
        profile.attribute_name,
        profile.structural_context,
        list(profile.header_path),
        profile.source_value_type,
        profile.source_attribute_id,
    )
    result = _verify(
        schema,
        _mapping("r_1", context="Morphology"),
        profile=profile,
        candidates=_hits(schema),
    )
    after = (
        profile.attribute_name,
        profile.structural_context,
        list(profile.header_path),
        profile.source_value_type,
        profile.source_attribute_id,
    )
    assert result.source_attribute_id == "Sheet1!COL:D"
    assert after == before


def test_verifier_pass_cannot_override_legacy_low_confidence_review(schema):
    mapping = _mapping("r_1", confidence=0.4)
    verification = _verify(schema, mapping, candidates=_hits(schema))
    current = decide_mapping_acceptance(mapping)
    final = combine_mapping_acceptance(current, verification)
    assert verification.status is MappingVerificationStatus.PASS
    assert current.status is AcceptanceStatus.REVIEW
    assert final.status is AcceptanceStatus.REVIEW


def test_soft_verifier_review_is_shadow_only(schema):
    mapping = _mapping("r_1", name="Different", confidence=0.99)
    verification = _verify(
        schema,
        mapping,
        profile=_profile("Original"),
        candidates=_hits(schema),
    )
    current = decide_mapping_acceptance(mapping)
    final = combine_mapping_acceptance(current, verification)
    assert verification.status is MappingVerificationStatus.REVIEW
    assert current.status is AcceptanceStatus.AUTO_ACCEPT
    assert final.status is AcceptanceStatus.AUTO_ACCEPT


def test_hard_reject_overrides_high_confidence_auto_accept(schema):
    mapping = _mapping("r_40", confidence=0.99)
    verification = _verify(schema, mapping, candidates=_hits(schema))
    final = combine_mapping_acceptance(decide_mapping_acceptance(mapping), verification)
    assert verification.status is MappingVerificationStatus.REJECT
    assert final.status is AcceptanceStatus.NO_WRITE
    assert "TARGET_NOT_IN_RETRIEVED_CANDIDATES" in final.reason
