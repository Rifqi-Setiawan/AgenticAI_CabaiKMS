"""Curator panel for canonical rows acquired by the dynamic schema (review, approve, merge, discard)."""

from __future__ import annotations

import hashlib
from typing import Any

import streamlit as st

from src.integrations.client import ui_client
from src.schema.canonical import CanonicalSchema
from src.schema.dynamic import dynamic_schema_enabled


def _post(client: Any, key: str, action: str, body: dict[str, Any]) -> bool:
    """POST a curation action; show a readable message (not a traceback) when it is refused. True on success."""
    try:
        client.request("POST", f"/attributes/schema-rows/{key}/{action}", json=body)
    except Exception as exc:  # noqa: BLE001 - surfaced to the curator, never a stack trace
        if "403" in str(exc):
            st.error("Aksi kurasi ditolak: perlu token berperan curator. Buka 'Masuk sebagai kurator' di atas tabel dan isi token kurator.")
        else:
            st.error(f"Aksi kurasi gagal: {exc}")
        return False
    return True


def _curator_login() -> None:
    """The server-side token has the reviewer role; curation needs the curator token, held only in this browser session."""
    from src.storage.config import get_settings

    if get_settings().kms_api_token is None:
        return  # the page already asks for a token
    with st.expander("Masuk sebagai kurator (diperlukan untuk Setujui, Gabungkan, Buang)", expanded=False):
        st.text_input("Token kurator KMS", type="password", key="kms_reviewer_token",
                      help="Hanya disimpan di sesi browser ini; tidak ditulis ke URL, berkas, atau basis data.")
        st.caption("Kosongkan untuk kembali ke akses baca dan reviewer.")


def render_schema_rows_panel(client: Any | None = None) -> None:
    st.subheader("Baris Kanonik Baru (skema dinamis)")
    st.caption(
        "Atribut tanpa padanan yang diakuisisi sebagai baris kanonik tambahan. Status provisional berarti baris sudah ikut "
        "ke keluaran Excel; kurator dapat menyetujui, menggabungkan dengan baris yang bermakna sama, atau membuangnya. "
        + ("Akuisisi AKTIF." if dynamic_schema_enabled() else "Akuisisi sedang NONAKTIF (KMS_DYNAMIC_SCHEMA).")
    )
    if client is None:
        _curator_login()
    try:
        client = client or ui_client()
        rows = client.request("GET", "/attributes/schema-rows/all").get("rows", [])
    except Exception as exc:  # noqa: BLE001 - the panel must never break the page
        st.info(f"Daftar baris kanonik baru tidak dapat dimuat: {exc}")
        return
    if not rows:
        st.info("Belum ada baris kanonik hasil akuisisi.")
        return

    st.dataframe(
        [{"Label": r["label"], "Kunci": r["canonical_key"], "Domain": r["domain"], "Status": r["status"],
          "Gabung ke": r.get("merged_into_key") or "", "Sumber": r.get("source_label") or "",
          "Run": r.get("created_from_run") or "", "Contoh": ", ".join(map(str, r.get("examples") or []))} for r in rows],
        width="stretch",
    )
    active = [r for r in rows if r["status"] in ("provisional", "approved")]
    template = [(r.label, r.canonical_key) for r in CanonicalSchema.from_template().rows if r.domain != "lokasi"]
    for row in [r for r in rows if r["status"] == "provisional"]:
        key = hashlib.sha256(row["canonical_key"].encode("utf-8")).hexdigest()[:10]
        with st.expander(f"{row['label']} ({row['domain']}) - provisional", expanded=False):
            reason = st.text_input("Alasan kurasi (wajib, min 10 karakter)", key=f"sr_reason_{key}")
            ok = len((reason or "").strip()) >= 10
            if st.button("Setujui", key=f"sr_ok_{key}", disabled=not ok):
                if _post(client, row["canonical_key"], "approve", {"reason": reason}):
                    st.rerun()
            options = {f"{label} [{k}]": k for label, k in template if k != row["canonical_key"]}
            options.update({f"{r['label']} [{r['canonical_key']}]": r["canonical_key"] for r in active
                            if r["canonical_key"] != row["canonical_key"]})
            target = st.selectbox("Gabungkan ke baris", sorted(options), key=f"sr_target_{key}")
            if st.button("Gabungkan (jadikan alias)", key=f"sr_merge_{key}", disabled=not ok):
                if _post(client, row["canonical_key"], "merge", {"reason": reason, "into_key": options[target]}):
                    st.rerun()
            if st.button("Buang dan ingat", key=f"sr_drop_{key}", disabled=not ok):
                if _post(client, row["canonical_key"], "discard", {"reason": reason}):
                    st.rerun()
