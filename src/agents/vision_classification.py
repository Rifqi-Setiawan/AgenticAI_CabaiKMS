"""Fase 5 — Vision & Classification Agent: Description-Grounded Visual
Classification.

Given one image (Fase 4's ImageMetadata) and the canonical template's own
existing varietas columns as a DYNAMIC knowledge source (re-read fresh
every new VisionSession — see docs/DESIGN_DECISIONS.md (a) — not cached
across a template edit), asks an LVM to compare the photo's visual
features against each known varietas's morphological description and
decide, in one model call:
  - which plant part is shown (DAUN/BATANG/BUAH/BUNGA), and
  - whether the plant matches a known varietas (KNOWN), looks like an
    unlisted one (OTHER), or the visual evidence is too weak to decide
    (UNCERTAIN).

Filename text is an auxiliary signal ONLY: it's included in the prompt as
extra context the model may weigh however it likes, but nothing in this
module ever inspects the model's output and overrides it based on the
filename. There is structurally no code path that could do that — the
filename signal is consumed only while building the prompt, then discarded
before the LVM call happens.

Prompt caching (batch reuse): VisionSession reads and builds the
varietas-description text ONCE per session (not once per image), and every
image classified through that session reuses the same text — this is the
"dikirim sekali per sesi, dipakai ulang untuk batch" requirement. Note this
is session-scoped reuse in Python, not Gemini's server-side context-cache
API (`cached_content`): that native cache mechanism isn't reachable through
the OpenAI-compatible bridge instructor uses (see
src/llm/vision_providers.py), so using it would mean dropping Instructor
for this one path — a deliberate tradeoff in favor of one consistent,
Instructor-based call pattern across every LLM/LVM provider in this
project, not an oversight.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import openpyxl

from src.schema.canonical import DEFAULT_TEMPLATE_PATH
from src.schema.contracts import ImageMetadata, VisionResult
from src.llm.vision_providers import call_gemini, call_second_voter

LVMCall = Callable[..., VisionResult]

PLANT_PARTS = ("DAUN", "BATANG", "BUAH", "BUNGA")

# Auxiliary filename keyword hints — a simple substring match, deliberately
# not fuzzy: this signal is a booster only, so a missed typo (e.g. a real
# filename spelling a varietas "katokon" instead of the template's
# "Katokkon") is an acceptable, low-stakes miss rather than something worth
# a fuzzy-matching dependency for.
_PART_FILENAME_HINTS: dict[str, tuple[str, ...]] = {
    "DAUN": ("daun", "leaf"),
    "BATANG": ("batang", "stem", "stalk"),
    "BUAH": ("buah", "fruit"),
    "BUNGA": ("bunga", "flower"),
}

SYSTEM_PROMPT_TEMPLATE = """Anda adalah asisten identifikasi visual varietas cabai untuk CABAI-KMS.

Dari SATU foto, tentukan dalam SATU keputusan:
1. Bagian tanaman yang terlihat: DAUN, BATANG, BUAH, atau BUNGA.
2. Apakah foto ini cocok dengan salah satu varietas yang dikenal di bawah,
   berdasarkan perbandingan ciri visual foto terhadap deskripsi morfologi
   tiap varietas (bukan berdasarkan nama berkas).

Daftar varietas yang dikenal (sumber pengetahuan dinamis, dibaca ulang dari
template kanonik setiap sesi baru):
{knowledge_source}

Aturan status klasifikasi:
- KNOWN: ciri visual foto cocok jelas dengan salah satu varietas di atas
  -> isi matched_variety dengan nama varietas tersebut.
- OTHER: foto terlihat seperti tanaman cabai tetapi TIDAK cocok dengan
  varietas manapun di atas (diduga varietas baru/tidak terdaftar) ->
  matched_variety=null.
- UNCERTAIN: bukti visual terlalu lemah atau tidak jelas untuk memutuskan
  (foto buram, bagian tanaman tidak jelas, dll) -> matched_variety=null.

Sinyal dari nama berkas (jika ada) HANYA penguat opsional, BUKAN dasar
utama keputusan — jangan biarkan nama berkas menggantikan bukti visual
jika keduanya bertentangan."""


@dataclass(frozen=True)
class VarietyDescription:
    name: str
    characteristics: dict[str, str]

    def to_prompt_line(self) -> str:
        parts = "; ".join(f"{label}={value}" for label, value in self.characteristics.items() if value)
        return f"- {self.name}: {parts}" if parts else f"- {self.name}: (tidak ada deskripsi tercatat)"


@dataclass(frozen=True)
class FilenameSignal:
    suggested_part: str | None
    suggested_variety: str | None


def load_variety_descriptions(template_path: Path | str = DEFAULT_TEMPLATE_PATH) -> list[VarietyDescription]:
    """The dynamic knowledge source: the canonical template's own already-
    filled-in varietas columns, read fresh from disk every call (never
    cached across calls — only a VisionSession instance caches the *text
    built from* one such read, for its own lifetime)."""
    wb = openpyxl.load_workbook(template_path, data_only=True, read_only=True)
    ws = wb["Sheet1"]
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter)

    varietas_names: list[str] = []
    for cell in header[2:]:
        if cell is None:
            break
        varietas_names.append(str(cell).strip())

    characteristics: dict[str, dict[str, str]] = {name: {} for name in varietas_names}
    for row in rows_iter:
        label = row[1]
        if label is None:
            continue
        label = str(label).strip()
        for name, value in zip(varietas_names, row[2:]):
            if value is not None and str(value).strip():
                characteristics[name][label] = str(value).strip()

    wb.close()
    return [VarietyDescription(name, characteristics[name]) for name in varietas_names]


def build_knowledge_source_text(varieties: list[VarietyDescription]) -> str:
    return "\n".join(v.to_prompt_line() for v in varieties)


def extract_filename_signal(filename: str, known_varieties: list[str]) -> FilenameSignal:
    lowered = filename.lower()

    suggested_part = next(
        (part for part, keywords in _PART_FILENAME_HINTS.items() if any(kw in lowered for kw in keywords)),
        None,
    )
    suggested_variety = next((name for name in known_varieties if name.lower() in lowered), None)

    return FilenameSignal(suggested_part=suggested_part, suggested_variety=suggested_variety)


def _filename_hint_text(signal: FilenameSignal) -> str:
    if not signal.suggested_part and not signal.suggested_variety:
        return "Tidak ada sinyal jelas dari nama berkas."
    hints = []
    if signal.suggested_part:
        hints.append(f"kemungkinan bagian={signal.suggested_part}")
    if signal.suggested_variety:
        hints.append(f"kemungkinan varietas={signal.suggested_variety}")
    return "Sinyal dari nama berkas (penguat, bukan penentu): " + ", ".join(hints)


def build_messages(
    image_bytes: bytes,
    mime_type: str,
    filename: str,
    knowledge_source_text: str,
    filename_signal: FilenameSignal,
) -> list[dict[str, Any]]:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(knowledge_source=knowledge_source_text)
    b64 = base64.b64encode(image_bytes).decode()

    user_text = (
        f"Nama berkas: {filename!r}\n"
        f"{_filename_hint_text(filename_signal)}\n\n"
        "Tentukan bagian tanaman dan kecocokan varietas dari foto berikut."
    )

    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
            ],
        },
    ]


def download_image_bytes(file_id: str, *, service: Any = None) -> bytes:
    from src.agents.drive_crawler import get_drive_service

    service = service or get_drive_service()
    return service.files().get_media(fileId=file_id).execute()


def _combine_consensus(primary: VisionResult, secondary: VisionResult) -> VisionResult:
    """Agreement on both part and variety reinforces the primary result
    (confidence nudged up, capped at 1.0). Disagreement downgrades to
    UNCERTAIN and lowers confidence rather than silently picking whichever
    voter sounds more confident — the primary's part/matched_variety are
    kept as the returned decision (a decision still has to be returned),
    but the mismatch is recorded in visual_evidence for a human reviewer."""
    agree = (
        primary.identified_part == secondary.identified_part
        and primary.matched_variety == secondary.matched_variety
    )
    if agree:
        boosted = min(1.0, (primary.confidence + secondary.confidence) / 2 + 0.05)
        return primary.model_copy(update={"confidence": boosted})

    return primary.model_copy(
        update={
            "classification_status": "UNCERTAIN",
            "confidence": min(primary.confidence, secondary.confidence),
            "visual_evidence": (
                f"{primary.visual_evidence} [consensus mismatch: voter kedua -> "
                f"identified_part={secondary.identified_part}, matched_variety={secondary.matched_variety!r}]"
            ),
        }
    )


def classify_image(
    image: ImageMetadata,
    knowledge_source_text: str,
    varieties: list[VarietyDescription],
    *,
    image_bytes: bytes | None = None,
    drive_service: Any = None,
    lvm_call: LVMCall = call_gemini,
    consensus: bool = False,
    second_voter_call: LVMCall = call_second_voter,
) -> VisionResult:
    """Classify one image. `image_bytes` can be injected directly (tests,
    or a caller that already has the bytes) — otherwise it's downloaded
    from Drive by `image.file_id`."""
    if image_bytes is None:
        image_bytes = download_image_bytes(image.file_id, service=drive_service)

    filename_signal = extract_filename_signal(image.filename, [v.name for v in varieties])
    messages = build_messages(
        image_bytes, image.mime_type, image.filename, knowledge_source_text, filename_signal
    )

    primary = lvm_call(response_model=VisionResult, messages=messages)
    if not isinstance(primary, VisionResult):
        raise TypeError(f"lvm_call must return a VisionResult, got {type(primary)!r}")

    if not consensus:
        return primary

    secondary = second_voter_call(response_model=VisionResult, messages=messages)
    if not isinstance(secondary, VisionResult):
        raise TypeError(f"second_voter_call must return a VisionResult, got {type(secondary)!r}")

    return _combine_consensus(primary, secondary)


class VisionSession:
    """One classification session/batch. Reads the dynamic knowledge
    source exactly once (in __init__), then reuses the resulting text for
    every image classified through this session — see the module
    docstring for why that's the "prompt caching" requirement's real
    functional meaning here."""

    def __init__(
        self,
        template_path: Path | str = DEFAULT_TEMPLATE_PATH,
        *,
        lvm_call: LVMCall = call_gemini,
        consensus: bool = False,
        second_voter_call: LVMCall = call_second_voter,
        drive_service: Any = None,
    ):
        self.varieties = load_variety_descriptions(template_path)
        self.knowledge_source_text = build_knowledge_source_text(self.varieties)
        self.lvm_call = lvm_call
        self.consensus = consensus
        self.second_voter_call = second_voter_call
        self.drive_service = drive_service

    def classify(self, image: ImageMetadata, *, image_bytes: bytes | None = None) -> VisionResult:
        return classify_image(
            image,
            self.knowledge_source_text,
            self.varieties,
            image_bytes=image_bytes,
            drive_service=self.drive_service,
            lvm_call=self.lvm_call,
            consensus=self.consensus,
            second_voter_call=self.second_voter_call,
        )

    def classify_batch(
        self,
        images: list[ImageMetadata],
        *,
        image_bytes_map: dict[str, bytes] | None = None,
    ) -> list[VisionResult]:
        """`image_bytes_map` (keyed by file_id) lets a caller — or a test —
        supply bytes directly for some/all images instead of downloading
        from Drive; any image_id not in the map falls back to a real
        download."""
        image_bytes_map = image_bytes_map or {}
        return [
            self.classify(image, image_bytes=image_bytes_map.get(image.file_id))
            for image in images
        ]
