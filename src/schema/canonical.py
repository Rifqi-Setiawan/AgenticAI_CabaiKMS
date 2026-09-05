"""Canonical schema S = (R, V, D) — see docs/DESIGN_DECISIONS.md.

R (rows) comes from data/canonical/template_kanonik.xlsx. N = len(R) is read
dynamically every time this module loads a template; nothing here may assume
N == 60. V (varietas being processed in the current acquisition run) and D
(the cell matrix for that run) start empty — they are NOT the 10 varietas
already filled in in the template file. Those existing filled cells are only
used as a source of `contoh_nilai` (example values) for prompting.
"""

from __future__ import annotations

import hashlib
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openpyxl
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_PATH = PROJECT_ROOT / "data" / "canonical" / "template_kanonik.xlsx"
DEFAULT_ROW_DOMAINS_PATH = Path(__file__).resolve().parent / "row_domains.yaml"
DEFAULT_ROW_ALIASES_PATH = Path(__file__).resolve().parent / "row_aliases.yaml"
DEFAULT_ROW_KEYS_PATH = Path(__file__).resolve().parent / "row_keys.yaml"

UNASSIGNED_DOMAIN = "unassigned"
SEPARATOR = " ⊕ "  # "⊕", explicit separator for rich-text row serialization
CANONICAL_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class CanonicalMetadataError(ValueError):
    """Canonical identity metadata is missing, ambiguous, or invalid."""


def _load_label_keyed_yaml(path: Path, list_key: str, value_key: str) -> dict[str, Any]:
    """Read a `{list_key}: [{label, value_key}, ...]` yaml file into a
    `{trimmed_label: value}` dict. Returns {} if the file doesn't exist yet
    (row_aliases.yaml is user-maintained and may not exist until filled in).
    """
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    out: dict[str, Any] = {}
    for entry in data.get(list_key, []) or []:
        label = str(entry["label"]).strip()
        out[label] = entry.get(value_key)
    return out


@dataclass(frozen=True)
class CanonicalRow:
    id: str  # positional/template identifier; changes when rows are reordered
    canonical_key: str  # durable semantic identity from row_keys.yaml
    label: str  # trimmed human-readable display/matching label
    domain: str
    contoh_nilai: tuple[str, ...] = ()
    alt_labels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not CANONICAL_KEY_RE.fullmatch(self.canonical_key):
            raise CanonicalMetadataError(
                f"invalid canonical_key {self.canonical_key!r} for row {self.id!r}"
            )

    def serialize(self) -> str:
        """repr(r) = label ⊕ domain ⊕ contoh_nilai ⊕ altLabels."""
        contoh = ", ".join(self.contoh_nilai) if self.contoh_nilai else "-"
        alts = ", ".join(self.alt_labels) if self.alt_labels else "-"
        return SEPARATOR.join([self.label, self.domain, contoh, alts])


@dataclass
class CanonicalSchema:
    rows: list[CanonicalRow]
    template_hash: str
    template_path: Path
    # Synthetic/manual schemas may omit this; from_template() never does.
    schema_version: str = "unspecified"
    varietas: list[str] = field(default_factory=list)  # V, starts empty
    cells: dict[tuple[str, str], Any] = field(default_factory=dict)  # D, starts empty

    def __post_init__(self) -> None:
        keys = [row.canonical_key for row in self.rows]
        if len(keys) != len(set(keys)):
            raise CanonicalMetadataError("CanonicalSchema rows contain duplicate canonical keys")

    # -- R: lookups -----------------------------------------------------

    def row_by_id(self, row_id: str) -> CanonicalRow | None:
        return next((r for r in self.rows if r.id == row_id), None)

    def row_by_label(self, label: str) -> CanonicalRow | None:
        label = label.strip()
        return next((r for r in self.rows if r.label == label), None)

    def row_by_key(self, canonical_key: str) -> CanonicalRow | None:
        return next((r for r in self.rows if r.canonical_key == canonical_key), None)

    @property
    def row_ids(self) -> frozenset[str]:
        return frozenset(r.id for r in self.rows)

    @property
    def row_keys(self) -> frozenset[str]:
        return frozenset(r.canonical_key for r in self.rows)

    @property
    def domains(self) -> frozenset[str]:
        """The valid domain set, derived — never a hardcoded enum."""
        return frozenset(r.domain for r in self.rows)

    @property
    def unassigned_labels(self) -> list[str]:
        return [r.label for r in self.rows if r.domain == UNASSIGNED_DOMAIN]

    # -- V, D: this run's varietas and cell matrix -----------------------

    def add_varietas(self, name: str) -> None:
        if name not in self.varietas:
            self.varietas.append(name)

    def set_cell(self, row_id: str, varietas: str, value: Any) -> None:
        if row_id not in self.row_ids:
            raise KeyError(f"unknown canonical row id: {row_id!r}")
        if varietas not in self.varietas:
            raise KeyError(f"varietas not registered, call add_varietas first: {varietas!r}")
        self.cells[(row_id, varietas)] = value

    def get_cell(self, row_id: str, varietas: str) -> Any:
        return self.cells.get((row_id, varietas))

    # -- drift detection (full re-index lands in Fase 3a) ----------------

    def has_drifted(self, template_path: Path | None = None) -> bool:
        template_path = template_path or self.template_path
        _, _, fresh_hash = _read_template_labels(template_path)
        return fresh_hash != self.template_hash

    @classmethod
    def from_template(
        cls,
        template_path: Path | str = DEFAULT_TEMPLATE_PATH,
        row_domains_path: Path | str = DEFAULT_ROW_DOMAINS_PATH,
        row_aliases_path: Path | str = DEFAULT_ROW_ALIASES_PATH,
        row_keys_path: Path | str = DEFAULT_ROW_KEYS_PATH,
    ) -> CanonicalSchema:
        template_path = Path(template_path)
        labels, examples_by_label, template_hash = _read_template_labels(template_path)
        schema_version, keys = _load_row_keys(Path(row_keys_path), labels)

        domains = _load_label_keyed_yaml(Path(row_domains_path), "rows", "domain")
        aliases = _load_label_keyed_yaml(Path(row_aliases_path), "rows", "alt_labels")

        rows: list[CanonicalRow] = []
        for i, label in enumerate(labels, start=1):
            domain = domains.get(label)
            if domain is None:
                warnings.warn(
                    f"canonical row {i} ({label!r}) has no domain in "
                    f"{row_domains_path} — marking {UNASSIGNED_DOMAIN!r}. "
                    "Raise this in docs/OPEN_QUESTIONS.md.",
                    stacklevel=2,
                )
                domain = UNASSIGNED_DOMAIN
            rows.append(
                CanonicalRow(
                    id=f"r_{i}",
                    canonical_key=keys[label],
                    label=label,
                    domain=domain,
                    contoh_nilai=tuple(examples_by_label.get(label, ())),
                    alt_labels=tuple(aliases.get(label, ()) or ()),
                )
            )

        return cls(
            rows=rows,
            schema_version=schema_version,
            template_hash=template_hash,
            template_path=template_path,
        )


def _load_row_keys(path: Path, template_labels: list[str]) -> tuple[str, dict[str, str]]:
    """Load explicit stable identities and require exact template coverage."""
    if not path.exists():
        raise CanonicalMetadataError(f"canonical key metadata file not found: {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    schema_version = data.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise CanonicalMetadataError("row_keys.yaml must define a non-empty schema_version")
    entries = data.get("rows")
    if not isinstance(entries, list):
        raise CanonicalMetadataError("row_keys.yaml must define rows as a list")

    keys_by_label: dict[str, str] = {}
    labels_seen: set[str] = set()
    keys_seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise CanonicalMetadataError(f"row_keys.yaml rows[{index}] must be a mapping")
        label = str(entry.get("label", "")).strip()
        key = str(entry.get("canonical_key", "")).strip()
        if not label:
            raise CanonicalMetadataError(f"row_keys.yaml rows[{index}] has an empty label")
        if label in labels_seen:
            raise CanonicalMetadataError(f"duplicate canonical metadata label: {label!r}")
        if not CANONICAL_KEY_RE.fullmatch(key):
            raise CanonicalMetadataError(
                f"invalid canonical_key {key!r} for label {label!r}; "
                "expected lowercase snake_case"
            )
        if key in keys_seen:
            raise CanonicalMetadataError(f"duplicate canonical_key: {key!r}")
        labels_seen.add(label)
        keys_seen.add(key)
        keys_by_label[label] = key

    template_set = set(template_labels)
    missing = template_set - labels_seen
    extra = labels_seen - template_set
    if missing or extra or len(template_labels) != len(template_set):
        details = []
        if missing:
            details.append(f"missing labels: {sorted(missing)}")
        if extra:
            details.append(f"unknown labels: {sorted(extra)}")
        if len(template_labels) != len(template_set):
            details.append("template contains duplicate labels")
        raise CanonicalMetadataError("canonical key metadata does not exactly cover template; " + "; ".join(details))
    return schema_version.strip(), keys_by_label


def _read_template_labels(
    template_path: Path,
) -> tuple[list[str], dict[str, list[str]], str]:
    """Read Sheet1 of the canonical template.

    Returns (labels in row order, {label: example values from the template's
    own filled cells}, sha256 hash of the (position, label) sequence).
    """
    wb = openpyxl.load_workbook(template_path, data_only=True, read_only=True)
    ws = wb["Sheet1"]

    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter)
    # varietas columns: everything from column C onward, stopping at the
    # first empty header cell (the template has a trailing unused column).
    n_varietas_cols = 0
    for cell in header[2:]:
        if cell is None:
            break
        n_varietas_cols += 1

    labels: list[str] = []
    examples_by_label: dict[str, list[str]] = {}
    for row in rows_iter:
        nomor, label = row[0], row[1]
        if nomor is None or label is None:
            continue
        label = str(label).strip()
        labels.append(label)

        seen: list[str] = []
        for cell in row[2 : 2 + n_varietas_cols]:
            if cell is None:
                continue
            text = str(cell).strip()
            if not text:
                continue
            if text not in seen:
                seen.append(text)
        examples_by_label[label] = seen

    wb.close()

    digest_source = "|".join(f"{i}:{lbl}" for i, lbl in enumerate(labels, start=1))
    template_hash = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    return labels, examples_by_label, template_hash
