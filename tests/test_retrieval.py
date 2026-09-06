from __future__ import annotations

import pytest

from src.agents.schema_matching import indexing
from src.agents.schema_matching.exact_retrieval import build_exact_index, retrieve_exact
from src.agents.schema_matching.retrieval import (
    DEFAULT_K,
    MAX_K,
    MIN_K,
    RetrievalHit,
    SourceAttributeProfile,
    detect_data_type,
    retrieve,
)
from src.schema.canonical import CanonicalSchema

pytestmark = pytest.mark.indexing  # needs network on first run (HF model download)


@pytest.fixture(scope="module")
def schema() -> CanonicalSchema:
    return CanonicalSchema.from_template()


@pytest.fixture(scope="module")
def client(tmp_path_factory, schema):
    c = indexing.get_client(tmp_path_factory.mktemp("chroma"))
    indexing.ensure_indexed(schema, client=c)
    return c


@pytest.fixture(scope="module")
def exact_index(schema):
    return build_exact_index(schema)


RETRIEVAL_CASES = [
    ("panjang daun", None, ["10,5 - 14 cm", "8-10cm", "±12 cm"], "r_8"),
    ("warna biji", None, ["yellow", "kuning", "yellow-orange group 23 C"], "r_54"),
    (
        "warna daun",
        None,
        ["green group 137 A", "hijau tua", "green group 137 A; green group 138 B"],
        "r_7",
    ),
    (
        "Lokasi",
        None,
        ["Desa Contoh, Kec. Sintetis (7.1234, 110.5678, 500 mdpl)", "Kebun Percobaan A"],
        "r_56",
    ),
    ("bentuk bunga", None, ["seperti bintang", "seperti bintang*", "-"], "r_23"),
    (
        "Ketinggian Lahan Sampling (mdpl = meter diatas permukaan laut)",
        "Lokasi Sampling",
        ["573", "598", "758", "719", "705"],
        "r_56",
    ),
]


class TestDetectDataType:
    def test_numeric_range_samples(self):
        assert detect_data_type(["10,5 - 14 cm", "8-10cm", "±12 cm"]) == "numerik"

    def test_categorical_low_cardinality_samples(self):
        assert detect_data_type(["cup", "cup", "united", "cup"]) == "kategorik"

    def test_free_text_high_cardinality_samples(self):
        values = [
            "Dusun Randu, Desa Hargobinangun, Area Sawah",
            "Dusun Tenen, Desa Hargobinangun, Jl. Boyong",
            "Dusun Jatisuko, Desa Campursalam, Kec. Parakan",
        ]
        assert detect_data_type(values) == "tekstual"

    def test_empty_samples_default_to_tekstual(self):
        assert detect_data_type([]) == "tekstual"


class TestSourceAttributeProfile:
    def test_caps_sample_values_to_ten(self):
        profile = SourceAttributeProfile(
            attribute_name="x", sample_values=[str(i) for i in range(20)]
        )
        assert len(profile.sample_values) == 10

    def test_auto_detects_type_when_not_given(self):
        profile = SourceAttributeProfile(attribute_name="tinggi", sample_values=["60 - 89 cm"])
        assert profile.data_type == "numerik"

    def test_explicit_type_is_not_overridden(self):
        profile = SourceAttributeProfile(
            attribute_name="tinggi", sample_values=["60 - 89 cm"], data_type="tekstual"
        )
        assert profile.data_type == "tekstual"

    def test_build_query_includes_all_parts(self):
        profile = SourceAttributeProfile(
            attribute_name="panjang daun",
            structural_context="Karakter",
            sample_values=["10,5 - 14 cm"],
        )
        query = profile.build_query()
        assert "panjang daun" in query
        assert "Karakter" in query
        assert "10,5 - 14 cm" in query
        assert "numerik" in query


class TestRetrieve:
    def test_k_out_of_range_raises(self, schema, client):
        profile = SourceAttributeProfile(attribute_name="x")
        with pytest.raises(ValueError):
            retrieve(profile, k=MIN_K - 1, schema=schema, client=client)
        with pytest.raises(ValueError):
            retrieve(profile, k=MAX_K + 1, schema=schema, client=client)

    def test_default_k_matches_spec(self):
        assert DEFAULT_K == 8

    def test_returns_k_hits_ranked_by_distance(self, schema, client):
        profile = SourceAttributeProfile(
            attribute_name="panjang daun", sample_values=["10,5 - 14 cm", "8-10cm", "±12 cm"]
        )
        hits = retrieve(profile, k=8, schema=schema, client=client)
        assert len(hits) == 8
        assert all(isinstance(h, RetrievalHit) for h in hits)
        distances = [h.distance for h in hits]
        assert distances == sorted(distances)

    # Each case validated empirically against the real/synthetic samples in
    # data/samples/ before this test was written — see PROFILING.md and
    # sample_transposed_sintetis.xlsx for where these values come from.
    @pytest.mark.parametrize(
        "attribute_name,structural_context,sample_values,expected_row_id",
        RETRIEVAL_CASES,
    )
    def test_correct_row_appears_in_top_k(
        self, schema, client, attribute_name, structural_context, sample_values, expected_row_id
    ):
        profile = SourceAttributeProfile(
            attribute_name=attribute_name,
            structural_context=structural_context,
            sample_values=sample_values,
        )
        hits = retrieve(profile, k=8, schema=schema, client=client)
        assert expected_row_id in [h.row_id for h in hits]


class TestExactRetrieveEmpirical:
    @pytest.mark.parametrize(
        "attribute_name,structural_context,sample_values,expected_row_id",
        RETRIEVAL_CASES,
    )
    def test_expected_row_appears_in_exact_top_k(
        self,
        schema,
        exact_index,
        attribute_name,
        structural_context,
        sample_values,
        expected_row_id,
    ):
        profile = SourceAttributeProfile(
            attribute_name=attribute_name,
            structural_context=structural_context,
            sample_values=sample_values,
        )
        hits = retrieve(
            profile, k=8, schema=schema, backend="exact", exact_index=exact_index
        )
        assert expected_row_id in [hit.row_id for hit in hits]

    def test_representative_canonical_self_query_returns_itself_top1(
        self, schema, exact_index
    ):
        for row in (schema.rows[0], schema.rows[len(schema.rows) // 2], schema.rows[-1]):
            class RawQuery:
                def build_query(self):
                    return row.serialize()

            hits = retrieve_exact(RawQuery(), k=1, exact_index=exact_index)
            assert hits[0].canonical_key == row.canonical_key
