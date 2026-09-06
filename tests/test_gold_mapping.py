from copy import deepcopy

import pytest
from pydantic import ValidationError

from src.schema.canonical import CanonicalSchema
from src.schema.gold_mapping import (
    GoldAnnotationSet,
    GoldMappingAnnotation,
    GoldMappingStatus,
    build_mapping_item_id,
    build_mapping_item_identities,
    build_mapping_item_ids,
    compare_annotators,
    create_adjudication_template,
    merge_adjudicated_gold,
    validate_gold_annotations,
)


def _annotation(schema, *, item="item-1", status=GoldMappingStatus.ONE_TO_ONE, keys=None, annotator="annotator_A"):
    return GoldMappingAnnotation(
        mapping_item_id=item, source_file_name="source.xlsx", source_file_sha256="a" * 64,
        source_sheet="Sheet1", source_format="row-oriented", source_attribute_id="Sheet1!COL:B",
        source_attribute_display="Height", source_attribute="Height", gold_status=status,
        gold_canonical_keys=[schema.rows[0].canonical_key] if keys is None else keys,
        annotator_id=annotator, annotation_round=1,
    )


@pytest.fixture(scope="module")
def schema():
    return CanonicalSchema.from_template()


def test_gold_status_cardinality_and_schema_validation(schema):
    assert _annotation(schema).calibration_eligible is True
    assert _annotation(schema, status=GoldMappingStatus.NO_MATCH, keys=[]).calibration_eligible is True
    assert _annotation(schema, status=GoldMappingStatus.COMPOSITE, keys=[schema.rows[0].canonical_key, schema.rows[1].canonical_key]).calibration_eligible is False
    for status, keys in [
        (GoldMappingStatus.ONE_TO_ONE, []), (GoldMappingStatus.ONE_TO_ONE, ["a", "b"]),
        (GoldMappingStatus.NO_MATCH, [schema.rows[0].canonical_key]), (GoldMappingStatus.COMPOSITE, [schema.rows[0].canonical_key]),
    ]:
        with pytest.raises(ValidationError):
            _annotation(schema, status=status, keys=keys)
    with pytest.raises(ValueError, match="unknown canonical key"):
        validate_gold_annotations([_annotation(schema, keys=["not_a_key"])], schema)


def test_annotation_set_rejects_duplicate_item_and_blank_annotator(schema):
    with pytest.raises(ValidationError, match="duplicate mapping_item_id"):
        GoldAnnotationSet(annotations=[_annotation(schema), _annotation(schema, annotator="annotator_B")])
    with pytest.raises(ValidationError):
        _annotation(schema, annotator=" ")


def test_mapping_item_id_is_stable_and_prediction_independent():
    identity = dict(source_file_sha256="a" * 64, source_sheet="Sheet1", source_format="row-oriented", source_attribute_id="Sheet1!COL:D")
    first = build_mapping_item_id(**identity)
    assert first == build_mapping_item_id(**identity)
    assert first != build_mapping_item_id(**{**identity, "source_file_sha256": "b" * 64})
    assert build_mapping_item_ids(
        source_file_sha256="a" * 64, source_sheet="Sheet1", source_format="row-oriented",
        source_items=[(None, "Height"), (None, "Height")],
    ) == [None, None]


def test_identity_selection_is_per_display_group_and_cross_backend_stable():
    common = dict(source_file_sha256="a" * 64, source_sheet="Sheet1", source_format="row-oriented")
    before = build_mapping_item_identities(**common, source_items=[(None, "A"), (None, "B")])
    after = build_mapping_item_identities(**common, source_items=[
        (None, "A"), (None, "B"), ("col:C1", "C"), ("col:C2", "C"),
    ])
    assert [item.mapping_item_id for item in before] == [item.mapping_item_id for item in after[:2]]
    assert [item.identity_kind.value for item in after] == [
        "source_attribute_display", "source_attribute_display",
        "source_attribute_id", "source_attribute_id",
    ]
    legacy = build_mapping_item_identities(**common, source_items=[(None, "A")])[0]
    source_ir = build_mapping_item_identities(**common, source_items=[("Sheet1!COL:D", "A")])[0]
    assert legacy.mapping_item_id == source_ir.mapping_item_id


def test_annotator_comparison_kappa_and_adjudication_template(schema):
    a1 = _annotation(schema, item="one")
    a2 = _annotation(schema, item="two", status=GoldMappingStatus.NO_MATCH, keys=[])
    b1 = deepcopy(a1).model_copy(update={"annotator_id": "annotator_B"})
    b2 = _annotation(schema, item="two", annotator="annotator_B")
    table, metrics = compare_annotators([a1, a2], [b2, b1])
    assert metrics.number_compared == 2
    assert metrics.raw_agreement == 0.5
    assert table.set_index("mapping_item_id").loc["two", "disagreement_type"] == "STATUS"
    template = create_adjudication_template([a1, a2], [b1, b2])
    assert template.mapping_item_id.tolist() == ["two"]
    assert template.loc[template.index[0], "adjudicated_status"] == ""
    with pytest.raises(ValueError, match="explicit adjudicated"):
        merge_adjudicated_gold([a1, a2], [b1, b2])
    resolution = _annotation(schema, item="two", status=GoldMappingStatus.NO_MATCH, keys=[], annotator="adjudicator")
    resolution = resolution.model_copy(update={"annotation_source": "adjudicated"})
    merged = merge_adjudicated_gold([a1, a2], [b1, b2], [resolution])
    assert merged[0].agreement is True
    assert merged[1].adjudicated is True
    assert merged[1].annotation_a.annotator_id == "annotator_A"
