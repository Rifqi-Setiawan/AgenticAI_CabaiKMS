"""Curator panel for canonical rows acquired by the dynamic schema (review, approve, merge, discard)."""

from __future__ import annotations

import hashlib
from typing import Any

import streamlit as st

from src.integrations.client import ui_client
from src.schema.canonical import CanonicalSchema
from src.schema.dynamic import dynamic_schema_enabled


def _post(client: Any, key: str, action: str, body: dict[str, Any]) -> None:
    client.request("POST", f"/attributes/schema-rows/{key}/{action}", json=body)


def render_schema_rows_panel(client: Any | None = None) -> None:
    st.subheader("Baris Kanonik Baru (skema dinamis)")
    st.caption(
        "Atribut tanpa padanan yang diakuisisi sebagai baris kanonik tambahan. Status provisional berarti baris sudah ikut "
        "ke keluaran Excel; kurator dapat menyetujui, menggabungkan dengan baris yang bermakna sama, atau membuangnya. "
        + ("Akuisisi AKTIF." if dynamic_schema_enabled() else "Akuisisi sedang NONAKTIF (KMS_DYNAMIC_SCHEMA).")
    )
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
                _post(client, row["canonical_key"], "approve", {"reason": reason})
                st.rerun()
            options = {f"{label} [{k}]": k for label, k in template if k != row["canonical_key"]}
            options.update({f"{r['label']} [{r['canonical_key']}]": r["canonical_key"] for r in active
                            if r["canonical_key"] != row["canonical_key"]})
            target = st.selectbox("Gabungkan ke baris", sorted(options), key=f"sr_target_{key}")
            if st.button("Gabungkan (jadikan alias)", key=f"sr_merge_{key}", disabled=not ok):
                _post(client, row["canonical_key"], "merge", {"reason": reason, "into_key": options[target]})
                st.rerun()
            if st.button("Buang dan ingat", key=f"sr_drop_{key}", disabled=not ok):
                _post(client, row["canonical_key"], "discard", {"reason": reason})
                st.rerun()
