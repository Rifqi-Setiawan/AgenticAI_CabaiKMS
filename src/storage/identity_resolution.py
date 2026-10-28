"""Administrative region and habitat resolution for CabaiKMS JSONB storage."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Literal

from src.storage.document_contracts import (
    AdministrativePath,
    HabitatIdentity,
    PlantIdentity,
    SamplingLocationDetail,
)


@dataclass(frozen=True)
class LocationResolution:
    """Result of administrative location resolution."""

    status: Literal["RESOLVED", "AMBIGUOUS", "UNRESOLVED", "CONFLICT"]
    habitat: HabitatIdentity | None
    candidates: list[HabitatIdentity]
    reason: str
    raw_address: str
    hamlet: str | None
    sampling_marker: str | None


@dataclass(frozen=True)
class PlantResolution:
    """Result of taxonomic plant identity resolution."""

    status: Literal["RESOLVED", "AMBIGUOUS", "UNRESOLVED"]
    plant: PlantIdentity | None
    candidates: list[PlantIdentity]
    reason: str
    raw_label: str


def _clean_token(text: str) -> str:
    """Normalize text token for comparison."""
    cleaned = re.sub(
        r"^(?:kabupaten|kab\.?|kecamatan|kec\.?|desa|ds\.?|kelurahan|kel\.?|dusun|dsn\.?|provinsi|prov\.?)\s+",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", cleaned).strip().lower()
    return cleaned


def _slugify(text: str) -> str:
    """Convert text into standard URL/identifier slug."""
    text_no_parens = re.sub(r"\([^)]*\)", "", text).strip()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text_no_parens.lower()).strip("-")
    return slug


def extract_address_components(raw_address: str) -> dict[str, Any]:
    """Parse raw Indonesian address into administrative tiers and metadata."""
    result: dict[str, Any] = {
        "raw_address": raw_address,
        "hamlet": None,
        "village": None,
        "district": None,
        "regency": None,
        "province": None,
        "sampling_marker": None,
    }

    if not raw_address or not raw_address.strip():
        return result

    working_text = raw_address

    # Extract sampling or location marker in parentheses
    marker_match = re.search(
        r"\(([^)]*(?:sampling|lokasi)[^)]*)\)", working_text, flags=re.IGNORECASE
    )
    if marker_match:
        result["sampling_marker"] = marker_match.group(1).strip()
        working_text = (
            working_text[: marker_match.start()] + " " + working_text[marker_match.end() :]
        )
    else:
        generic_marker = re.search(r"\(([^)]+)\)", working_text)
        if generic_marker:
            inner = generic_marker.group(1).strip()
            if re.search(r"\b(?:sampling|lokasi)\b", inner, flags=re.IGNORECASE):
                result["sampling_marker"] = inner
                working_text = (
                    working_text[: generic_marker.start()]
                    + " "
                    + working_text[generic_marker.end() :]
                )

    # Strip postal code and country
    clean_text = re.sub(r"\b\d{5}\b", "", working_text)
    clean_text = re.sub(r"\bIndonesia\b", "", clean_text, flags=re.IGNORECASE)

    parts = [p.strip() for p in clean_text.split(",") if p.strip()]

    extracted_hamlet: str | None = None
    extracted_village: str | None = None
    extracted_district: str | None = None
    extracted_regency: str | None = None
    extracted_province: str | None = None

    # Pass 1: match explicitly prefixed components
    unprefixed_parts: list[str] = []
    for part in parts:
        part_clean = part.strip()
        if not part_clean:
            continue

        # Hamlet
        m_hamlet = re.match(r"^(?:dusun|dsn\.?)\s+(.+)$", part_clean, re.IGNORECASE)
        if m_hamlet and extracted_hamlet is None:
            extracted_hamlet = f"Dusun {m_hamlet.group(1).strip()}"
            continue

        # Village
        m_village = re.match(
            r"^(?:desa|ds\.?|kelurahan|kel\.?)\s+(.+)$", part_clean, re.IGNORECASE
        )
        if m_village and extracted_village is None:
            extracted_village = f"Desa {m_village.group(1).strip()}"
            continue

        # District
        m_district = re.match(r"^(?:kecamatan|kec\.?)\s+(.+)$", part_clean, re.IGNORECASE)
        if m_district and extracted_district is None:
            extracted_district = f"Kecamatan {m_district.group(1).strip()}"
            continue

        # Regency
        m_regency = re.match(r"^(?:kabupaten|kab\.?)\s+(.+)$", part_clean, re.IGNORECASE)
        if m_regency and extracted_regency is None:
            extracted_regency = f"Kabupaten {m_regency.group(1).strip()}"
            continue

        m_city = re.match(r"^(?:kota)\s+(.+)$", part_clean, re.IGNORECASE)
        if m_city and extracted_regency is None:
            extracted_regency = f"Kota {m_city.group(1).strip()}"
            continue

        # Province
        m_prov = re.match(r"^(?:provinsi|prov\.?)\s+(.+)$", part_clean, re.IGNORECASE)
        if m_prov and extracted_province is None:
            val = m_prov.group(1).strip()
            if re.search(r"yogyakarta|diy|d\.?i\.?\s*yogyakarta", val, re.IGNORECASE):
                extracted_province = "Daerah Istimewa Yogyakarta"
            else:
                extracted_province = val
            continue

        unprefixed_parts.append(part_clean)

    # Pass 2: match unprefixed components (ignoring streets, areas, etc.)
    for part_clean in unprefixed_parts:
        # Ignore street or generic area designations
        if re.match(r"^(?:jl\.?|jalan|area|lahan)\b", part_clean, re.IGNORECASE):
            continue

        lower_part = part_clean.lower()
        if re.search(r"\b(?:yogyakarta|diy|d\.?i\.?\s*yogyakarta)\b", lower_part):
            if extracted_province is None:
                extracted_province = "Daerah Istimewa Yogyakarta"
        elif re.search(r"\bjawa\s+tengah\b", lower_part):
            if extracted_province is None:
                extracted_province = "Jawa Tengah"
        elif re.search(r"\bjawa\s+barat\b", lower_part):
            if extracted_province is None:
                extracted_province = "Jawa Barat"
        elif re.search(r"\bsleman\b", lower_part):
            if extracted_regency is None:
                extracted_regency = "Kabupaten Sleman"
        elif re.search(r"\btemanggung\b", lower_part):
            if extracted_regency is None:
                extracted_regency = "Kabupaten Temanggung"
        elif re.search(r"\bwonosobo\b", lower_part):
            if extracted_regency is None:
                extracted_regency = "Kabupaten Wonosobo"
        elif re.search(r"\bpurbalingga\b", lower_part):
            if extracted_regency is None:
                extracted_regency = "Kabupaten Purbalingga"
        elif re.search(r"\bmajalengka\b", lower_part):
            if extracted_regency is None:
                extracted_regency = "Kabupaten Majalengka"
        elif re.search(r"\bpakem\b", lower_part):
            if extracted_district is None:
                extracted_district = "Kecamatan Pakem"
        elif re.search(r"\bparakan\b", lower_part):
            if extracted_district is None:
                extracted_district = "Kecamatan Parakan"
        elif re.search(r"\bkedu\b", lower_part):
            if extracted_district is None:
                extracted_district = "Kecamatan Kedu"
        elif re.search(r"\bkalikajar\b", lower_part):
            if extracted_district is None:
                extracted_district = "Kecamatan Kalikajar"
        elif re.search(r"\bkejobong\b", lower_part):
            if extracted_district is None:
                extracted_district = "Kecamatan Kejobong"
        elif re.search(r"\bargapura\b", lower_part):
            if extracted_district is None:
                extracted_district = "Kecamatan Argapura"

    result["hamlet"] = extracted_hamlet
    result["village"] = extracted_village
    result["district"] = extracted_district
    result["regency"] = extracted_regency
    result["province"] = extracted_province

    return result


class AdministrativeRegistry:
    """Curated local administrative registry for dataset sampling locations."""

    def __init__(self, data_path: str | Path | None = None) -> None:
        if data_path is None:
            resolved_path = (
                Path(__file__).parent / "registries" / "administrative_regions.json"
            )
        else:
            resolved_path = Path(data_path)

        with open(resolved_path, "r", encoding="utf-8") as f:
            raw_entries: list[dict[str, Any]] = json.load(f)

        self._entries: list[dict[str, Any]] = raw_entries
        self._habitats: list[HabitatIdentity] = []

        for entry in self._entries:
            path = AdministrativePath(
                province_id=entry.get("province_id", ""),
                regency_id=entry.get("regency_id", ""),
                district_id=entry.get("district_id", ""),
                village_id=entry.get("village_id", ""),
                province_name=entry["province_name"],
                regency_name=entry["regency_name"],
                district_name=entry["district_name"],
                village_name=entry["village_name"],
            )
            hab = HabitatIdentity(
                id=entry["habitat_id"],
                definition="administrative_village_v1",
                administrative_path=path,
                label=(
                    f"{path.village_name}, {path.district_name}, "
                    f"{path.regency_name}, {path.province_name}"
                ),
            )
            self._habitats.append(hab)

    def lookup(
        self,
        province: str,
        regency: str,
        district: str,
        village: str,
    ) -> HabitatIdentity | None:
        """Find habitat matching exact administrative hierarchy."""
        norm_prov = _clean_token(province)
        norm_reg = _clean_token(regency)
        norm_dist = _clean_token(district)
        norm_vill = _clean_token(village)

        for hab in self._habitats:
            path = hab.administrative_path
            p_prov = _clean_token(path.province_name)
            p_reg = _clean_token(path.regency_name)
            p_dist = _clean_token(path.district_name)
            p_vill = _clean_token(path.village_name)

            # Check province match with alias handling
            prov_match = (
                norm_prov == p_prov
                or ("yogyakarta" in norm_prov and "yogyakarta" in p_prov)
            )
            reg_match = norm_reg == p_reg
            dist_match = norm_dist == p_dist
            vill_match = norm_vill == p_vill

            if prov_match and reg_match and dist_match and vill_match:
                return hab

        return None

    def match_hierarchy(self, extracted: dict[str, Any]) -> LocationResolution:
        """Resolve administrative hierarchy against curated entries."""
        raw_address = extracted.get("raw_address", "")
        hamlet = extracted.get("hamlet")
        sampling_marker = extracted.get("sampling_marker")

        if not raw_address or not raw_address.strip():
            return LocationResolution(
                status="UNRESOLVED",
                habitat=None,
                candidates=[],
                reason="Address is empty or whitespace",
                raw_address=raw_address,
                hamlet=hamlet,
                sampling_marker=sampling_marker,
            )

        # Check for ambiguity markers or alternative villages
        lower_addr = raw_address.lower()
        if re.search(r"\batau\b", lower_addr):
            # Address explicitly presents alternatives
            matching_alts: list[HabitatIdentity] = []
            for hab in self._habitats:
                v_clean = _clean_token(hab.administrative_path.village_name)
                if re.search(rf"\b{re.escape(v_clean)}\b", lower_addr):
                    matching_alts.append(hab)
            return LocationResolution(
                status="AMBIGUOUS",
                habitat=None,
                candidates=matching_alts,
                reason="Address contains alternative village designations",
                raw_address=raw_address,
                hamlet=hamlet,
                sampling_marker=sampling_marker,
            )

        # Determine target village
        extracted_village = extracted.get("village")
        target_village_token: str | None = None
        if extracted_village:
            target_village_token = _clean_token(extracted_village)
        else:
            # Check if any known village in registry is mentioned in address
            for hab in self._habitats:
                v_token = _clean_token(hab.administrative_path.village_name)
                if re.search(rf"\b{re.escape(v_token)}\b", lower_addr):
                    target_village_token = v_token
                    break

        if not target_village_token:
            return LocationResolution(
                status="UNRESOLVED",
                habitat=None,
                candidates=[],
                reason="No recognized administrative village found in address",
                raw_address=raw_address,
                hamlet=hamlet,
                sampling_marker=sampling_marker,
            )

        # Find all habitat entries matching the target village
        village_matches = [
            hab
            for hab in self._habitats
            if _clean_token(hab.administrative_path.village_name) == target_village_token
        ]

        if not village_matches:
            return LocationResolution(
                status="UNRESOLVED",
                habitat=None,
                candidates=[],
                reason=f"Village '{target_village_token}' not found in registry",
                raw_address=raw_address,
                hamlet=hamlet,
                sampling_marker=sampling_marker,
            )

        # Check for explicit contradiction in hierarchy
        extracted_regency = extracted.get("regency")
        extracted_district = extracted.get("district")
        extracted_province = extracted.get("province")

        if extracted_regency:
            norm_ext_reg = _clean_token(extracted_regency)
            reg_matches = [
                hab
                for hab in village_matches
                if _clean_token(hab.administrative_path.regency_name) == norm_ext_reg
            ]
            if not reg_matches:
                return LocationResolution(
                    status="CONFLICT",
                    habitat=None,
                    candidates=[],
                    reason=(
                        f"Village '{target_village_token}' does not belong to "
                        f"regency '{extracted_regency}'"
                    ),
                    raw_address=raw_address,
                    hamlet=hamlet,
                    sampling_marker=sampling_marker,
                )
            village_matches = reg_matches

        if extracted_district:
            norm_ext_dist = _clean_token(extracted_district)
            dist_matches = [
                hab
                for hab in village_matches
                if _clean_token(hab.administrative_path.district_name) == norm_ext_dist
            ]
            if not dist_matches:
                return LocationResolution(
                    status="CONFLICT",
                    habitat=None,
                    candidates=[],
                    reason=(
                        f"Village '{target_village_token}' does not belong to "
                        f"district '{extracted_district}'"
                    ),
                    raw_address=raw_address,
                    hamlet=hamlet,
                    sampling_marker=sampling_marker,
                )
            village_matches = dist_matches

        if extracted_province:
            norm_ext_prov = _clean_token(extracted_province)
            prov_matches = [
                hab
                for hab in village_matches
                if (
                    _clean_token(hab.administrative_path.province_name) == norm_ext_prov
                    or (
                        "yogyakarta" in norm_ext_prov
                        and "yogyakarta"
                        in _clean_token(hab.administrative_path.province_name)
                    )
                )
            ]
            if not prov_matches:
                return LocationResolution(
                    status="CONFLICT",
                    habitat=None,
                    candidates=[],
                    reason=(
                        f"Village '{target_village_token}' does not belong to "
                        f"province '{extracted_province}'"
                    ),
                    raw_address=raw_address,
                    hamlet=hamlet,
                    sampling_marker=sampling_marker,
                )
            village_matches = prov_matches

        # Evaluation of candidates
        if len(village_matches) > 1:
            return LocationResolution(
                status="AMBIGUOUS",
                habitat=None,
                candidates=village_matches,
                reason=(
                    f"Ambiguous village '{target_village_token}': "
                    f"{len(village_matches)} candidates match provided context"
                ),
                raw_address=raw_address,
                hamlet=hamlet,
                sampling_marker=sampling_marker,
            )

        if len(village_matches) == 1:
            # If village was matched alone without any regency, district, or province qualification
            if not extracted_regency and not extracted_district and not extracted_province:
                # Isolated village name without administrative context
                # Check if multiple homonyms exist in broader geography
                all_homonyms = [
                    hab
                    for hab in self._habitats
                    if _clean_token(hab.administrative_path.village_name)
                    == target_village_token
                ]
                if len(all_homonyms) >= 2:
                    return LocationResolution(
                        status="AMBIGUOUS",
                        habitat=None,
                        candidates=all_homonyms,
                        reason="Isolated village name with multiple homonymous candidates",
                        raw_address=raw_address,
                        hamlet=hamlet,
                        sampling_marker=sampling_marker,
                    )

            resolved_habitat = village_matches[0]
            return LocationResolution(
                status="RESOLVED",
                habitat=resolved_habitat,
                candidates=village_matches,
                reason="Successfully resolved administrative village hierarchy",
                raw_address=raw_address,
                hamlet=hamlet,
                sampling_marker=sampling_marker,
            )

        return LocationResolution(
            status="UNRESOLVED",
            habitat=None,
            candidates=[],
            reason="Unable to resolve location to a single habitat",
            raw_address=raw_address,
            hamlet=hamlet,
            sampling_marker=sampling_marker,
        )


AdministrativeRegionRegistry = AdministrativeRegistry


class PlantCatalog:
    """Curated taxonomic catalog for chili plant categories and cultivars."""

    def __init__(self, data_path: str | Path | None = None) -> None:
        if data_path is None:
            resolved_path = Path(__file__).parent / "registries" / "plants.json"
        else:
            resolved_path = Path(data_path)

        with open(resolved_path, "r", encoding="utf-8") as f:
            raw_entries: list[dict[str, Any]] = json.load(f)

        self._entries: list[dict[str, Any]] = raw_entries
        self._plants: list[PlantIdentity] = []

        for entry in self._entries:
            p = PlantIdentity(
                id=entry["id"],
                label=entry["label"],
                identity_level=entry["identity_level"],
                scientific_name=entry.get("scientific_name"),
                source_category=entry.get("source_category"),
            )
            self._plants.append(p)

    def resolve(self, raw_label: str) -> PlantResolution:
        """Resolve taxonomic label to plant identity."""
        if not raw_label or not raw_label.strip():
            return PlantResolution(
                status="UNRESOLVED",
                plant=None,
                candidates=[],
                reason="Plant label is empty or whitespace",
                raw_label=raw_label,
            )

        lower_label = raw_label.strip().lower()

        # Check for ambiguity (multiple chili types in label)
        has_rawit = "rawit" in lower_label or "frutescens" in lower_label
        has_besar = (
            "besar" in lower_label
            or "annum" in lower_label
            or "annuum" in lower_label
            or "merah" in lower_label
        )

        if has_rawit and has_besar:
            plant_rawit = PlantIdentity(
                id="plant_cabai_rawit",
                label="Cabai rawit",
                identity_level="source_category",
                scientific_name="Capsicum frutescens L",
                source_category="Cabai rawit",
            )
            plant_besar = PlantIdentity(
                id="plant_cabai_besar",
                label="Cabai besar",
                identity_level="source_category",
                scientific_name="Capsicum annum L",
                source_category="Cabai besar",
            )
            return PlantResolution(
                status="AMBIGUOUS",
                plant=None,
                candidates=[plant_rawit, plant_besar],
                reason="Label contains multiple conflicting plant varieties",
                raw_label=raw_label,
            )

        # Check for explicit cultivars
        if "maruti" in lower_label:
            plant = PlantIdentity(
                id="plant_cultivar_maruti",
                label="Cabai Rawit Merah Maruti",
                identity_level="cultivar",
                scientific_name="Capsicum frutescens L",
                source_category="Cabai rawit",
            )
            return PlantResolution(
                status="RESOLVED",
                plant=plant,
                candidates=[plant],
                reason="Resolved to cultivar Maruti",
                raw_label=raw_label,
            )

        if "hiyung" in lower_label:
            plant = PlantIdentity(
                id="plant_cultivar_hiyung",
                label="Cabai Rawit Hiyung",
                identity_level="cultivar",
                scientific_name="Capsicum frutescens L",
                source_category="Cabai rawit",
            )
            return PlantResolution(
                status="RESOLVED",
                plant=plant,
                candidates=[plant],
                reason="Resolved to cultivar Hiyung",
                raw_label=raw_label,
            )

        # Check generic source categories
        if has_rawit:
            plant = PlantIdentity(
                id="plant_cabai_rawit",
                label="Cabai rawit",
                identity_level="source_category",
                scientific_name="Capsicum frutescens L",
                source_category="Cabai rawit",
            )
            return PlantResolution(
                status="RESOLVED",
                plant=plant,
                candidates=[plant],
                reason="Resolved to source category Cabai rawit",
                raw_label=raw_label,
            )

        if has_besar:
            scientific_name = "Capsicum annum L"
            if "annuum" in lower_label:
                scientific_name = "Capsicum annuum L"
            plant = PlantIdentity(
                id="plant_cabai_besar",
                label="Cabai besar",
                identity_level="source_category",
                scientific_name=scientific_name,
                source_category="Cabai besar",
            )
            return PlantResolution(
                status="RESOLVED",
                plant=plant,
                candidates=[plant],
                reason="Resolved to source category Cabai besar",
                raw_label=raw_label,
            )

        return PlantResolution(
            status="UNRESOLVED",
            plant=None,
            candidates=[],
            reason=f"Unrecognized plant variety label: {raw_label}",
            raw_label=raw_label,
        )


_DEFAULT_REGISTRY: AdministrativeRegistry | None = None
_DEFAULT_CATALOG: PlantCatalog | None = None


def _get_default_registry() -> AdministrativeRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = AdministrativeRegistry()
    return _DEFAULT_REGISTRY


def _get_default_catalog() -> PlantCatalog:
    global _DEFAULT_CATALOG
    if _DEFAULT_CATALOG is None:
        _DEFAULT_CATALOG = PlantCatalog()
    return _DEFAULT_CATALOG


def resolve_location(
    raw_address: str,
    registry: AdministrativeRegistry | None = None,
) -> LocationResolution:
    """Resolve raw address to LocationResolution contract."""
    reg = registry or _get_default_registry()
    extracted = extract_address_components(raw_address)
    return reg.match_hierarchy(extracted)


def resolve_plant(
    raw_label: str,
    catalog: PlantCatalog | None = None,
) -> PlantResolution:
    """Resolve raw plant label to PlantResolution contract."""
    cat = catalog or _get_default_catalog()
    return cat.resolve(raw_label)


def resolve_sampling_location(
    raw_address: str,
    context: dict[str, Any] | None = None,
    registry: AdministrativeRegistry | None = None,
) -> tuple[HabitatIdentity | None, SamplingLocationDetail, list[str]]:
    """Resolve sampling location and return detail with validation issues."""
    ctx = context or {}
    res = resolve_location(raw_address, registry=registry)
    habitat = res.habitat

    issues: list[str] = []
    if res.status != "RESOLVED":
        issues.append(f"UNRESOLVED_LOCATION: {res.reason}")

    location_ref = ctx.get("location_ref") or (habitat.id if habitat else "loc_unresolved")

    elevation = ctx.get("elevation_mdpl")
    if elevation is None:
        elevation = ctx.get("elevation")

    soil_ph = ctx.get("soil_ph")
    if soil_ph is None:
        soil_ph = ctx.get("ph")

    coordinates = ctx.get("coordinates")

    detail = SamplingLocationDetail(
        location_ref=location_ref,
        raw_address=res.raw_address,
        hamlet=res.hamlet,
        sampling_marker=res.sampling_marker,
        coordinates=coordinates,
        elevation_mdpl=float(elevation) if elevation is not None else None,
        soil_ph=float(soil_ph) if soil_ph is not None else None,
    )

    return habitat, detail, issues


def resolve_plant_identity(
    raw_name: str,
    detected_category: str | None = None,
    catalog: PlantCatalog | None = None,
) -> PlantIdentity:
    """Resolve taxonomic identity or raise ValueError."""
    cat = catalog or _get_default_catalog()
    res = cat.resolve(raw_name)
    if res.status == "RESOLVED" and res.plant is not None:
        return res.plant

    if detected_category:
        res_cat = cat.resolve(detected_category)
        if res_cat.status == "RESOLVED" and res_cat.plant is not None:
            return res_cat.plant

    raise ValueError(f"Unable to resolve plant identity for: {raw_name} ({res.reason})")


def build_document_identity(
    variety: PlantIdentity,
    habitat: HabitatIdentity | None,
) -> str:
    """Formulate deterministic document ID from variety and habitat identity."""
    if variety.source_category:
        var_text = variety.source_category
    else:
        var_text = variety.label

    var_slug = _slugify(var_text)

    if habitat is None:
        return f"doc_{var_slug}_unassigned"

    path = habitat.administrative_path
    reg_clean = re.sub(
        r"^(?:kabupaten|kota)\s+", "", path.regency_name, flags=re.IGNORECASE
    )
    dist_clean = re.sub(
        r"^(?:kecamatan)\s+", "", path.district_name, flags=re.IGNORECASE
    )
    vill_clean = re.sub(
        r"^(?:desa|kelurahan)\s+", "", path.village_name, flags=re.IGNORECASE
    )

    reg_slug = _slugify(reg_clean)
    dist_slug = _slugify(dist_clean)
    vill_slug = _slugify(vill_clean)

    hab_slug = f"{reg_slug}-{dist_slug}-{vill_slug}"
    return f"doc_{var_slug}_{hab_slug}"
