from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.agents.schema_matching.reranking import build_messages, rerank
from src.agents.schema_matching.retrieval import RetrievalHit, SourceAttributeProfile
from pathlib import Path

from src.schema.canonical import CanonicalRow, CanonicalSchema
from src.schema.contracts import NULL_ROW, SchemaMapping


@pytest.fixture(scope="module")
def schema() -> CanonicalSchema:
    return CanonicalSchema.from_template()


def _candidates(schema: CanonicalSchema, row_ids: list[str]) -> list[RetrievalHit]:
    hits = []
    for i, row_id in enumerate(row_ids):
        row = schema.row_by_id(row_id)
        hits.append(RetrievalHit(row_id=row.id, label=row.label, domain=row.domain, distance=0.1 * i))
    return hits


def _mock_llm(raw: dict):
    """Stands in for a real instructor-backed LLM call: takes the raw dict
    the "model produced" and constructs the response_model from it — which
    is exactly where real Pydantic validation (and instructor's
    retry-on-ValidationError loop) actually happens. A bad target row fails
    right here, same as it would against a real provider."""

    def _call(*, response_model, messages):
        return response_model(**raw)

    return _call


class TestRerank:
    def test_exact_curated_alias_maps_without_calling_llm(self, schema):
        profile = SourceAttributeProfile(
            attribute_name="Seeds per mature fruit",
            structural_context="Mature Fruit",
            sample_values=["35", "42", "50"],
        )

        def must_not_call_llm(**kwargs):
            pytest.fail("Exact curated aliases must not depend on an LLM call")

        mapping = rerank(
            profile, [], source_format="row-oriented", schema=schema, llm_call=must_not_call_llm
        )

        target = schema.row_by_id(mapping.target_canonical_row)
        assert target.label == "jumlah biji/buah masak"
        assert mapping.source_context == "Mature Fruit"
        assert mapping.confidence == 1.0

    def test_ambiguous_exact_alias_falls_through_to_llm(self):
        ambiguous_schema = CanonicalSchema(
            rows=[
                CanonicalRow("r_1", "first", "First", "test", alt_labels=("Length",)),
                CanonicalRow("r_2", "second", "Second", "test", alt_labels=("length",)),
            ],
            template_hash="synthetic",
            template_path=Path("synthetic.xlsx"),
        )
        called = []

        def llm_call(*, response_model, messages):
            called.append(messages)
            return response_model(
                source_attribute="LENGTH",
                source_format="row-oriented",
                target_canonical_row="r_2",
                confidence=0.8,
                reasoning="Context resolves the ambiguous explicit name.",
                normalization_required=True,
            )

        mapping = rerank(
            SourceAttributeProfile("LENGTH", structural_context="Mature Fruit"),
            [],
            source_format="row-oriented",
            schema=ambiguous_schema,
            llm_call=llm_call,
        )
        assert called
        assert mapping.target_canonical_row == "r_2"

    def test_valid_llm_output_becomes_a_validated_schema_mapping(self, schema):
        profile = SourceAttributeProfile(
            attribute_name="Tinggi Tanaman (cm)", sample_values=["60 - 89 cm"]
        )
        candidates = _candidates(schema, ["r_2", "r_1"])
        llm_call = _mock_llm(
            {
                "source_attribute": profile.attribute_name,
                "source_context": None,
                "source_format": "transposed",
                "target_canonical_row": "r_2",
                "confidence": 0.93,
                "reasoning": "label cocok langsung dengan 'tinggi tanaman'",
                "normalization_required": True,
            }
        )

        mapping = rerank(
            profile, candidates, source_format="transposed", schema=schema, llm_call=llm_call
        )

        assert isinstance(mapping, SchemaMapping)
        assert mapping.target_canonical_row == "r_2"
        assert mapping.target_domain == "vegetatif"

    def test_null_target_is_accepted_when_llm_is_unconfident(self, schema):
        profile = SourceAttributeProfile(attribute_name="Nama Kolektor")
        candidates = _candidates(schema, ["r_1", "r_2"])
        llm_call = _mock_llm(
            {
                "source_attribute": profile.attribute_name,
                "source_format": "row-oriented",
                "target_canonical_row": NULL_ROW,
                "confidence": 0.99,
                "reasoning": "tidak ada baris kanonik yang relevan untuk nama kolektor",
                "normalization_required": False,
            }
        )

        mapping = rerank(profile, candidates, source_format="row-oriented", schema=schema, llm_call=llm_call)

        assert mapping.target_canonical_row == NULL_ROW
        assert mapping.target_domain is None

    def test_out_of_set_target_row_is_rejected(self, schema):
        """The core constrained-decoding guarantee: whatever the LLM
        outputs, target_canonical_row outside {r_1..r_N, NULL} never
        survives as a valid SchemaMapping."""
        profile = SourceAttributeProfile(attribute_name="???")
        candidates = _candidates(schema, ["r_1"])
        llm_call = _mock_llm(
            {
                "source_attribute": profile.attribute_name,
                "source_format": "row-oriented",
                "target_canonical_row": "r_9999",
                "confidence": 0.5,
                "reasoning": "halusinasi baris yang tidak ada",
                "normalization_required": False,
            }
        )

        with pytest.raises(ValidationError):
            rerank(profile, candidates, source_format="row-oriented", schema=schema, llm_call=llm_call)

    def test_out_of_range_confidence_is_rejected(self, schema):
        profile = SourceAttributeProfile(attribute_name="x")
        candidates = _candidates(schema, ["r_1"])
        llm_call = _mock_llm(
            {
                "source_attribute": "x",
                "source_format": "row-oriented",
                "target_canonical_row": "r_1",
                "confidence": 1.4,
                "reasoning": "overconfident",
                "normalization_required": False,
            }
        )

        with pytest.raises(ValidationError):
            rerank(profile, candidates, source_format="row-oriented", schema=schema, llm_call=llm_call)

    def test_llm_call_must_return_a_schema_mapping(self, schema):
        profile = SourceAttributeProfile(attribute_name="x")
        candidates = _candidates(schema, ["r_1"])

        def bad_llm_call(*, response_model, messages):
            return {"not": "a SchemaMapping"}

        with pytest.raises(TypeError):
            rerank(profile, candidates, source_format="row-oriented", schema=schema, llm_call=bad_llm_call)


class TestBuildMessages:
    def test_legacy_prompt_is_byte_for_byte_unchanged(self, schema):
        profile = SourceAttributeProfile(attribute_name="x")
        messages = build_messages(profile, [], schema, "row-oriented")
        assert messages[1]["content"] == (
            'Atribut sumber: "x"\n'
            "Konteks struktural: -\n"
            "Contoh nilai: -\n"
            "Tipe data terdeteksi: tekstual\n"
            "Format sumber: row-oriented\n\n"
            "Kandidat baris kanonik:\n(tidak ada kandidat)\n\n"
            'Jika tidak ada kandidat yang cocok, set target_canonical_row="NULL".'
        )

    def test_verified_structure_is_added_only_when_available(self, schema):
        profile = SourceAttributeProfile(
            attribute_name="Length",
            header_path=["Morphology", "Mature Fruit", "Length"],
            source_value_type="numeric",
            source_attribute_id="Sheet1!COL:D",
        )
        user_text = build_messages(profile, [], schema, "row-oriented")[1]["content"]
        assert "Morphology > Mature Fruit > Length" in user_text
        assert "Tipe sumber terverifikasi: numeric" in user_text
        assert "Sheet1!COL:D" not in user_text
    def test_messages_mention_attribute_candidates_and_null_option(self, schema):
        profile = SourceAttributeProfile(
            attribute_name="Tinggi Tanaman (cm)",
            structural_context="Karakter",
            sample_values=["60 - 89 cm"],
        )
        candidates = _candidates(schema, ["r_2", "r_1"])
        messages = build_messages(profile, candidates, schema, "transposed")

        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        user_text = messages[1]["content"]
        assert "Tinggi Tanaman (cm)" in user_text
        assert "Karakter" in user_text
        assert "60 - 89 cm" in user_text
        assert "r_2" in user_text and "tinggi tanaman" in user_text
        assert "r_1" in user_text and "habitus" in user_text
        assert NULL_ROW in user_text

    def test_empty_candidates_still_produces_valid_messages(self, schema):
        profile = SourceAttributeProfile(attribute_name="x")
        messages = build_messages(profile, [], schema, "row-oriented")
        assert "tidak ada kandidat" in messages[1]["content"]
