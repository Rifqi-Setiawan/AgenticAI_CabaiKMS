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

UNASSIGNED_DOMAIN = "unassigned"
SEPARATOR = " ⊕ "  # "⊕", explicit separator for rich-text row serialization


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
    id: str  # "r_1".."r_N", position in the template as of this load
    label: str  # trimmed "Karakter" text — the stable matching key
    domain: str
    contoh_nilai: tuple[str, ...] = ()
    alt_labels: tuple[str, ...] = ()

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
    varietas: list[str] = field(default_factory=list)  # V, starts empty
    cells: dict[tuple[str, str], Any] = field(default_factory=dict)  # D, starts empty

    # -- R: lookups -----------------------------------------------------

    def row_by_id(self, row_id: str) -> CanonicalRow | None:
        return next((r for r in self.rows if r.id == row_id), None)

    def row_by_label(self, label: str) -> CanonicalRow | None:
        label = label.strip()
        return next((r for r in self.rows if r.label == label), None)

    @property
    def row_ids(self) -> frozenset[str]:
        return frozenset(r.id for r in self.rows)

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
    ) -> CanonicalSchema:
        template_path = Path(template_path)
        labels, examples_by_label, template_hash = _read_template_labels(template_path)

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
                    label=label,
                    domain=domain,
                    contoh_nilai=tuple(examples_by_label.get(label, ())),
                    alt_labels=tuple(aliases.get(label, ()) or ()),
                )
            )

        return cls(rows=rows, template_hash=template_hash, template_path=template_path)


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
