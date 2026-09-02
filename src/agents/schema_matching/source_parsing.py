"""Shared source-spreadsheet parsing helpers — pulled out of
eval/review_schema_matching.py so both that harness and src/ui/ can reuse
the exact same parsing logic rather than maintaining two copies.

Pure I/O + structural parsing, no agent calls: turns a raw source workbook
into a flat list of ParsedAttribute (one per source column/row, with its
structural context and values), for the schema-matching agents to then
retrieve/rerank/normalize against.

`row_values` is positionally aligned across every ParsedAttribute returned
by the SAME call (index i means the same source row for row-oriented, or
the same variety column for transposed) — this is what lets a caller
reconstruct "this specific value belongs to this specific varietas" once
it knows which position maps to which varietas name (the anchor column's
own row_values, for row-oriented; `variety_names` returned directly by
load_transposed_rows, for transposed). `sample_values` (deduplication-free,
None-filtered) stays around for retrieval/rerank prompting, which never
cared about position, only "what values look like".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import openpyxl


@dataclass
class ParsedAttribute:
    attribute_name: str
    structural_context: str | None
    row_values: list[str | None]

    @property
    def sample_values(self) -> list[str]:
        return [v for v in self.row_values if v is not None]


def load_row_oriented_columns(path: Path, sheet_name: str) -> list[ParsedAttribute]:
    """Parse a two-row hierarchical header, row-oriented sheet (see
    docs/PROFILING.md §2.2): row 1 = an optional section header, forward-
    filled across the columns it merges over; row 2 = the real field name;
    data starts row 3. A column with no row-2 sub-header uses its own row-1
    text as the attribute name instead (e.g. "No", "Jenis Cabai").

    `row_values[i]` is the value from the i-th data row (row 3+i) — the
    SAME row index across every returned attribute, including whichever one
    is later identified as the anchor column, so a caller can zip an
    attribute's row_values against the anchor's row_values to know which
    varietas each value belongs to."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))
    section_row, field_row, data_rows = rows[0], rows[1], rows[2:]

    sections: list[str | None] = []
    current: str | None = None
    for cell in section_row:
        if cell is not None:
            current = str(cell).strip()
        sections.append(current)

    n_cols = max(len(section_row), len(field_row))
    attributes = []
    for col_idx in range(n_cols):
        filled_section = sections[col_idx] if col_idx < len(sections) else None
        raw_section = section_row[col_idx] if col_idx < len(section_row) else None
        field = field_row[col_idx] if col_idx < len(field_row) else None

        if field is not None:
            attribute_name, structural_context = str(field).strip(), filled_section
        elif raw_section is not None:
            # Only a column that genuinely HAS its own row-1 text (not one
            # merely inheriting a forward-filled value from an earlier
            # column) counts as a standalone, header-only attribute — this
            # is what keeps trailing empty columns (see docs/PROFILING.md
            # §2.2: cols O-Z are unused) from being misread as more
            # instances of whatever section header came last.
            attribute_name, structural_context = str(raw_section).strip(), None
        else:
            continue  # fully empty column

        row_values = [
            (str(row[col_idx]) if col_idx < len(row) and row[col_idx] is not None else None)
            for row in data_rows
        ]
        attributes.append(ParsedAttribute(attribute_name, structural_context, row_values))
    return attributes


def load_transposed_rows(path: Path, sheet_name: str) -> tuple[list[ParsedAttribute], list[str]]:
    """Parse a transposed sheet (varietas as column headers, characters as
    rows): finds the header row (first row whose first cell is "Karakter"),
    then treats every subsequent row as one attribute — its varietas-column
    values are the row_values, positionally aligned with the returned
    `variety_names` (index i in both refers to the same column)."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(values_only=True))

    header_idx = next(
        (i for i, row in enumerate(rows) if row and str(row[0]).strip() == "Karakter"),
        None,
    )
    if header_idx is None:
        raise ValueError(f'no header row starting with "Karakter" found in {path} sheet {sheet_name!r}')

    header_row = rows[header_idx]
    variety_names = [str(v).strip() for v in header_row[1:] if v is not None]
    n_varieties = len(variety_names)

    attributes = []
    for row in rows[header_idx + 1 :]:
        if not row or row[0] is None:
            continue
        attribute_name = str(row[0]).strip()
        row_values = [
            (str(v) if v is not None else None) for v in list(row[1:])[:n_varieties]
        ]
        row_values += [None] * (n_varieties - len(row_values))  # pad if the row was short
        attributes.append(ParsedAttribute(attribute_name, None, row_values))
    return attributes, variety_names
