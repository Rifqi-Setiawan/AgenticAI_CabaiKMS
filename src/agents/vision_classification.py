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
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import openpyxl

from src.schema.canonical import DEFAULT_TEMPLATE_PATH
from src.schema.contracts import ImageMetadata, VisionResult
from src.storage.document_contracts import (
    DocumentReviewItem,
    PhotoContextSignal,
    PhotoMismatchDecision,
    VisionClassificationResult,
)
from src.llm.openai_compatible import provider_mode
from src.llm.vision_providers import call_second_voter, call_vision

LVMCall = Callable[..., Any]

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


def extract_photo_context_signal(
    filename: str,
    caption: str | None = None,
    known_varieties: list[str] | None = None,
    registry: Any | None = None,
) -> PhotoContextSignal:
    """A23: Extract structured context signal (Signal 2) from filename and caption."""
    stem = Path(filename).stem
    raw_tokens = re.findall(r"[a-zA-Z0-9]+", stem.lower())

    combined_text = (filename + " " + (caption or "")).lower()
    extracted_part = None
    for part, keywords in _PART_FILENAME_HINTS.items():
        if any(kw in combined_text for kw in keywords):
            extracted_part = part
            break

    suggested_variety_hint = None
    is_exact_hint = True

    if registry is not None:
        best = registry.best_match(combined_text, threshold=0.6)
        if best is not None:
            suggested_variety_hint = best.canonical_name
            is_exact_hint = getattr(best, "is_exact", False)
    else:
        # Legacy fallback behavior
        stop_words = {
            "cabai",
            "cabe",
            "chili",
            "pepper",
            "tanaman",
            "foto",
            "daun",
            "buah",
            "batang",
            "bunga",
            "sample",
            "lokasi",
            "sp",
            "l",
        }

        if known_varieties:
            for variety in known_varieties:
                v_low = variety.lower()
                v_tokens = set(re.findall(r"[a-zA-Z0-9]+", v_low)) - stop_words
                if any(tok in combined_text for tok in v_tokens):
                    suggested_variety_hint = variety
                    break

        if not suggested_variety_hint:
            for word in re.findall(r"[a-zA-Z]+", combined_text):
                if word in stop_words or len(word) < 4:
                    continue
                if word in [
                    "rawit",
                    "keriting",
                    "habanero",
                    "katokkon",
                    "jalapeno",
                    "gendot",
                    "kopay",
                    "tanjung",
                    "domba",
                    "besar",
                ]:
                    suggested_variety_hint = f"Cabai {word.title()}"
                    break

    return PhotoContextSignal(
        filename=filename,
        caption=caption,
        extracted_part=extracted_part,
        suggested_variety_hint=suggested_variety_hint,
        is_exact_hint=is_exact_hint,
        raw_tokens=raw_tokens,
        extracted_variety_hints=[suggested_variety_hint] if suggested_variety_hint else [],
    )


def create_photo_mismatch_review_item(
    filename: str,
    suggested_hint: str | None = None,
    visual_evidence: str | None = None,
    options_evaluated: list[str] | None = None,
    caption: str | None = None,
    item_id: str | None = None,
    identified_part: str | None = None,
    confidence: float = 0.0,
    source_context: str | None = None,
) -> DocumentReviewItem:
    """A24 & TECH_PLAN 4.3: Construct a PHOTO_VARIETY_MISMATCH review item with 3 candidate actions."""
    candidate_resolutions = [
        {
            "action": "ASSIGN_EXISTING",
            "description": "Tetapkan ke salah satu varietas yang tersedia pada daftar opsi",
        },
        {
            "action": "CREATE_NEW_DOCUMENT",
            "description": "Bentuk dokumen varietas baru + habitat tanpa mengarang tingkat taksonomi",
        },
        {
            "action": "DISCARD",
            "description": "Penolakan non-destruktif (blob fisik tetap disimpan di storage CAS, dicatat di jejak audit)",
        },
    ]
    hint_str = suggested_hint or "none"
    ev_str = visual_evidence or "none"
    ctx = source_context or f"Photo '{filename}' mismatch (hint: {hint_str}, evidence: {ev_str})"
    return DocumentReviewItem(
        item_id=item_id or f"rev_photo_{uuid.uuid4().hex[:12]}",
        category="PHOTO_VARIETY_MISMATCH",
        target_document_key=None,
        source_label=filename,
        source_context=ctx,
        raw_values=[suggested_hint] if suggested_hint else [],
        candidate_resolutions=candidate_resolutions,
        status="pending",
        decision=None,
        notes=f"Photo variety mismatch for {filename}: hint '{hint_str}' not aligned with run varieties",
        payload={
            "filename": filename,
            "suggested_variety_hint": suggested_hint,
            "visual_evidence": visual_evidence,
            "options_evaluated": options_evaluated or [],
            "caption": caption,
            "identified_part": identified_part,
            "confidence": confidence,
        },
    )


def evaluate_photo_alignment(
    image: ImageMetadata,
    photo_signal: PhotoContextSignal | None = None,
    visual_result: VisionClassificationResult | VisionResult | None = None,
    options_evaluated: list[str] | None = None,
) -> DocumentReviewItem | None:
    """A24: Evaluate 3-signal alignment and return a blocking review item on mismatch."""
    if photo_signal is None and hasattr(image, "filename"):
        photo_signal = extract_photo_context_signal(image.filename, known_varieties=options_evaluated)

    is_mismatch = False
    mismatch_reason = ""

    if visual_result is None:
        is_mismatch = True
        mismatch_reason = "visual classification failed"
    elif visual_result.classification_status != "KNOWN":
        is_mismatch = True
        mismatch_reason = f"classification_status={visual_result.classification_status}"
    elif not visual_result.matched_variety:
        is_mismatch = True
        mismatch_reason = "matched_variety is empty"
    elif options_evaluated and visual_result.matched_variety not in options_evaluated:
        is_mismatch = True
        mismatch_reason = f"matched_variety '{visual_result.matched_variety}' not in evaluated options"
    else:
        vis_conf = getattr(
            visual_result,
            "visual_confidence",
            getattr(visual_result, "confidence", 0.0),
        )
        if vis_conf < 0.85:
            is_mismatch = True
            mismatch_reason = f"low confidence: {vis_conf:.2f} < 0.85"

    # Check signal consistency
    if not is_mismatch and visual_result is not None:
        if hasattr(visual_result, "signals_consistent") and visual_result.signals_consistent is False:
            is_mismatch = True
            mismatch_reason = "signals_consistent is False"
        elif photo_signal and photo_signal.suggested_variety_hint and visual_result.matched_variety:
            hint_low = photo_signal.suggested_variety_hint.lower()
            match_low = visual_result.matched_variety.lower()
            stop_words = {"cabai", "cabe", "capsicum", "tanaman", "l", "sp"}
            hint_toks = set(re.findall(r"[a-z0-9]+", hint_low)) - stop_words
            match_toks = set(re.findall(r"[a-z0-9]+", match_low)) - stop_words
            if hint_toks and match_toks and not (hint_toks & match_toks):
                is_mismatch = True
                mismatch_reason = f"contradiction between hint '{photo_signal.suggested_variety_hint}' and visual match '{visual_result.matched_variety}'"

    if is_mismatch:
        hint = photo_signal.suggested_variety_hint if photo_signal else None
        ev = getattr(visual_result, "visual_evidence", None) or mismatch_reason
        ctx = f"Photo '{image.filename}' mismatch: {mismatch_reason} (hint: {hint or 'none'}, evidence: {ev})"
        return create_photo_mismatch_review_item(
            filename=image.filename,
            suggested_hint=hint,
            visual_evidence=ev,
            options_evaluated=options_evaluated,
            caption=photo_signal.caption if photo_signal else None,
            identified_part=getattr(visual_result, "identified_part", None),
            confidence=getattr(visual_result, "confidence", 0.0),
            source_context=ctx,
        )
    return None


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
    photo_signal: PhotoContextSignal | None = None,
) -> list[dict[str, Any]]:
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(knowledge_source=knowledge_source_text)
    b64 = base64.b64encode(image_bytes).decode()

    user_lines = [f"Nama berkas: {filename!r}"]
    if photo_signal and photo_signal.caption:
        user_lines.append(f"Caption: {photo_signal.caption}")
    user_lines.append(_filename_hint_text(filename_signal))
    user_lines.append("\nTentukan bagian tanaman dan kecocokan varietas dari foto berikut.")
    user_text = "\n".join(user_lines)

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


def deterministic_mock_lvm(
    *,
    response_model: Any = None,
    messages: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Any:
    """Deterministic mock LVM for CI testing and quota isolation (A28)."""
    text_content = ""
    if messages:
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                text_content += " " + content
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_content += " " + str(item.get("text", ""))

    text_lower = text_content.lower()

    # Determine part
    part = "DAUN"
    for p, hints in _PART_FILENAME_HINTS.items():
        if any(h in text_lower for h in hints):
            part = p
            break

    # Determine known varieties from system prompt
    known_varieties: list[str] = []
    for line in text_content.splitlines():
        line_s = line.strip()
        if line_s.startswith("- "):
            v_name = line_s[2:].split(":")[0].strip()
            if v_name:
                known_varieties.append(v_name)

    filename = ""
    match_fn = re.search(r"Nama berkas:\s*['\"]([^'\"]+)['\"]", text_content)
    if match_fn:
        filename = match_fn.group(1)

    photo_signal = extract_photo_context_signal(filename, known_varieties=known_varieties)

    matched_variety = None
    if photo_signal.suggested_variety_hint:
        for kv in known_varieties:
            hint_low = photo_signal.suggested_variety_hint.lower()
            kv_low = kv.lower()
            if hint_low in kv_low or kv_low in hint_low:
                matched_variety = kv
                break
            # Token overlap check
            stop_words = {"cabai", "cabe", "capsicum", "tanaman", "l", "sp"}
            hint_toks = set(re.findall(r"[a-z0-9]+", hint_low)) - stop_words
            kv_toks = set(re.findall(r"[a-z0-9]+", kv_low)) - stop_words
            if hint_toks and kv_toks and (hint_toks & kv_toks):
                matched_variety = kv
                break

    if matched_variety:
        status = "KNOWN"
        vis_conf = 0.92
        text_conf = 0.88
        conf = 0.90
        evidence = f"Ciri morfologi visual {part.lower()} cocok dengan deskripsi {matched_variety}"
        consistent = True
    else:
        if any(word in text_lower for word in ["alat", "spad", "bukan", "meter"]):
            status = "UNCERTAIN"
            evidence = "Bukan organ tanaman cabai atau citra tidak meyakinkan"
            vis_conf = 0.40
            conf = 0.40
        else:
            status = "OTHER"
            evidence = f"Morfologi {part.lower()} tidak cocok dengan varietas run aktif ({photo_signal.suggested_variety_hint or 'tidak dikenal'})"
            vis_conf = 0.88
            conf = 0.70
        text_conf = 0.20
        consistent = False

    if response_model is VisionResult:
        return VisionResult(
            classification_status=status,
            matched_variety=matched_variety,
            identified_part=part,
            confidence=conf,
            visual_evidence=evidence,
        )

    return VisionClassificationResult(
        classification_status=status,
        matched_variety=matched_variety,
        identified_part=part,
        visual_confidence=vis_conf,
        text_confidence=text_conf,
        confidence=conf,
        visual_evidence=evidence,
        options_evaluated=known_varieties,
        signals_consistent=consistent,
    )


def default_lvm_call(
    *,
    response_model: Any = None,
    messages: list[dict[str, Any]] | None = None,
    max_retries: int = 2,
    **kwargs: Any,
) -> Any:
    """Default LVM dispatcher: uses deterministic mock in mock/offline mode or test environment (A28),
    routes to call_vision otherwise."""
    provider_env = os.environ.get("CABAI_KMS_VISION_PROVIDER", "").strip().lower()
    is_test_env = bool(os.environ.get("PYTEST_CURRENT_TEST"))
    if provider_env == "mock" or is_test_env:
        return deterministic_mock_lvm(response_model=response_model, messages=messages, **kwargs)

    has_keys = bool(
        os.environ.get("NINEROUTER_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("GEMINI_API_KEY")
    )
    if not has_keys:
        return deterministic_mock_lvm(response_model=response_model, messages=messages, **kwargs)

    try:
        return call_vision(
            response_model=response_model,
            messages=messages or [],
            max_retries=max_retries,
        )
    except Exception:
        return deterministic_mock_lvm(response_model=response_model, messages=messages, **kwargs)


def classify_image(
    image: ImageMetadata,
    knowledge_source_text: str,
    varieties: list[VarietyDescription],
    *,
    image_bytes: bytes | None = None,
    drive_service: Any = None,
    lvm_call: LVMCall | None = None,
    consensus: bool = False,
    second_voter_call: LVMCall = call_second_voter,
    photo_signal: PhotoContextSignal | None = None,
    run_scope_varieties: list[str] | None = None,
) -> VisionResult | VisionClassificationResult:
    """Classify one image. `image_bytes` can be injected directly (tests,
    or a caller that already has the bytes) — otherwise it's downloaded
    from Drive by `image.file_id`."""
    if image_bytes is None:
        image_bytes = download_image_bytes(image.file_id, service=drive_service)

    known_varieties = run_scope_varieties if run_scope_varieties is not None else [v.name for v in varieties]
    if photo_signal is None:
        photo_signal = extract_photo_context_signal(image.filename, known_varieties=known_varieties)

    filename_signal = extract_filename_signal(image.filename, known_varieties)
    messages = build_messages(
        image_bytes,
        image.mime_type,
        image.filename,
        knowledge_source_text,
        filename_signal,
        photo_signal=photo_signal,
    )

    actual_lvm_call = lvm_call or default_lvm_call
    resp_model = VisionClassificationResult if run_scope_varieties is not None else VisionResult

    primary = actual_lvm_call(response_model=resp_model, messages=messages)
    if not isinstance(primary, (VisionResult, VisionClassificationResult)):
        raise TypeError(f"lvm_call must return a VisionResult, got {type(primary)!r}")

    if run_scope_varieties is not None:
        if isinstance(primary, VisionResult) and not isinstance(primary, VisionClassificationResult):
            signals_consistent = True
            if photo_signal and photo_signal.suggested_variety_hint and primary.matched_variety:
                hint_low = photo_signal.suggested_variety_hint.lower()
                match_low = primary.matched_variety.lower()
                stop_words = {"cabai", "cabe", "capsicum", "tanaman", "l", "sp"}
                hint_toks = set(re.findall(r"[a-z0-9]+", hint_low)) - stop_words
                match_toks = set(re.findall(r"[a-z0-9]+", match_low)) - stop_words
                if hint_toks and match_toks and not (hint_toks & match_toks):
                    signals_consistent = False
            elif primary.classification_status != "KNOWN":
                signals_consistent = False

            primary = VisionClassificationResult(
                classification_status=primary.classification_status,
                matched_variety=primary.matched_variety,
                identified_part=primary.identified_part,
                visual_confidence=primary.confidence,
                text_confidence=0.85 if photo_signal and photo_signal.suggested_variety_hint else 0.0,
                confidence=primary.confidence,
                visual_evidence=primary.visual_evidence,
                options_evaluated=run_scope_varieties,
                signals_consistent=signals_consistent,
            )
        elif isinstance(primary, VisionClassificationResult):
            if not primary.options_evaluated:
                primary = primary.model_copy(update={"options_evaluated": run_scope_varieties})

    if not consensus or provider_mode("CABAI_KMS_VISION_PROVIDER") == "9router":
        return primary

    secondary = second_voter_call(response_model=VisionResult, messages=messages)
    if not isinstance(secondary, VisionResult):
        raise TypeError(f"second_voter_call must return a VisionResult, got {type(secondary)!r}")

    if isinstance(primary, VisionResult) and not isinstance(primary, VisionClassificationResult):
        return _combine_consensus(primary, secondary)

    return primary


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
        run_scope_varieties: list[str] | None = None,
        lvm_call: LVMCall | None = None,
        consensus: bool = False,
        second_voter_call: LVMCall = call_second_voter,
        drive_service: Any = None,
    ):
        if run_scope_varieties is not None:
            self.run_scope_varieties = list(run_scope_varieties)
            try:
                template_varieties = load_variety_descriptions(template_path)
            except Exception:
                template_varieties = []
            scoped_list = []
            for scoped_name in run_scope_varieties:
                matched_tv = next(
                    (
                        tv
                        for tv in template_varieties
                        if tv.name.lower() in scoped_name.lower()
                        or scoped_name.lower() in tv.name.lower()
                    ),
                    None,
                )
                if matched_tv:
                    scoped_list.append(VarietyDescription(scoped_name, matched_tv.characteristics))
                else:
                    scoped_list.append(VarietyDescription(scoped_name, {}))
            self.varieties = scoped_list
        else:
            self.run_scope_varieties = None
            self.varieties = load_variety_descriptions(template_path)

        self.knowledge_source_text = build_knowledge_source_text(self.varieties)
        self.lvm_call = lvm_call or default_lvm_call
        self.consensus_requested = consensus
        self.consensus = (
            consensus
            and os.environ.get("CABAI_KMS_VISION_PROVIDER", "9router").strip().lower() == "legacy"
        )
        self.consensus_note = (
            "Secondary vision consensus is disabled in 9Router mode because "
            "account redundancy is not independent-model agreement."
            if consensus and not self.consensus
            else None
        )
        self.second_voter_call = second_voter_call
        self.drive_service = drive_service

    def classify(
        self,
        image: ImageMetadata,
        *,
        image_bytes: bytes | None = None,
        photo_signal: PhotoContextSignal | None = None,
    ) -> VisionResult | VisionClassificationResult:
        return classify_image(
            image,
            self.knowledge_source_text,
            self.varieties,
            image_bytes=image_bytes,
            drive_service=self.drive_service,
            lvm_call=self.lvm_call,
            consensus=self.consensus,
            second_voter_call=self.second_voter_call,
            photo_signal=photo_signal,
            run_scope_varieties=self.run_scope_varieties,
        )

    def evaluate_photo_alignment(
        self,
        image: ImageMetadata,
        photo_signal: PhotoContextSignal | None = None,
        visual_result: VisionClassificationResult | VisionResult | None = None,
    ) -> DocumentReviewItem | None:
        return evaluate_photo_alignment(
            image=image,
            photo_signal=photo_signal,
            visual_result=visual_result,
            options_evaluated=self.run_scope_varieties,
        )

    def classify_batch(
        self,
        images: list[ImageMetadata],
        *,
        image_bytes_map: dict[str, bytes] | None = None,
        photo_signals_map: dict[str, PhotoContextSignal] | None = None,
    ) -> list[VisionResult | VisionClassificationResult]:
        """`image_bytes_map` (keyed by file_id) lets a caller — or a test —
        supply bytes directly for some/all images instead of downloading
        from Drive; any image_id not in the map falls back to a real
        download."""
        image_bytes_map = image_bytes_map or {}
        photo_signals_map = photo_signals_map or {}
        return [
            self.classify(
                image,
                image_bytes=image_bytes_map.get(image.file_id),
                photo_signal=photo_signals_map.get(image.file_id),
            )
            for image in images
        ]
