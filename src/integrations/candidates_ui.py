"""Streamlit UI components for Image Candidates review and Habitat Unknown documents curation."""

from __future__ import annotations

from typing import Any
import streamlit as st

from src.integrations.client import ui_client


def resolve_candidate_api(candidate_id: str, decision: dict[str, Any]) -> dict[str, Any]:
    """Client API call to resolve candidate via KMS persistence API."""
    client = ui_client()
    return client._post(f"/candidates/{candidate_id}/resolve", json=decision)


def set_document_habitat_api(doc_key: str, habitat_payload: dict[str, Any]) -> dict[str, Any]:
    """Client API call to set resolved habitat on an unknown-habitat document."""
    client = ui_client()
    return client._post(f"/documents/{doc_key}/habitat", json=habitat_payload)


def render_candidates_panel(candidates: list[dict[str, Any]] | None = None) -> None:
    """Render candidates queue panel for human researcher review (one-by-one, no clustering)."""
    st.subheader("Antrean Kandidat Varietas Baru (Citra Google Drive)")

    if candidates is None:
        try:
            client = ui_client()
            candidates = client._get("/candidates?status=CANDIDATE")
        except Exception as e:
            st.error(f"Gagal memuat kandidat varietas: {e}")
            return

    if not candidates:
        st.info("Tidak ada kandidat varietas baru yang menunggu peninjauan.")
        return

    st.write(f"Terdapat **{len(candidates)}** kandidat citra varietas baru menunggu keputusan.")

    # Render each candidate individually (D13: no automatic clustering)
    for idx, cand in enumerate(candidates):
        cid = cand["candidate_id"]
        fname = cand.get("source_filename") or cand.get("filename") or "Foto"
        conf = cand.get("confidence", 0.0)

        with st.expander(f"Kandidat #{idx+1}: {fname} (Keyakinan: {conf:.2f})", expanded=True):
            cols = st.columns([1, 2])
            with cols[0]:
                media_url = cand.get("media_url")
                if media_url:
                    st.image(media_url, caption=fname, use_container_width=True)
                else:
                    st.write(f"Asset ID: `{cand.get('asset_id')}`")
                st.write(f"- Organ: **{cand.get('organ_part')}**")
                st.write(f"- Status: `{cand.get('status')}`")

            with cols[1]:
                ev = cand.get("visual_evidence")
                if ev:
                    st.write("**Bukti Visual:**")
                    st.json(ev)

                # Form input kurator
                st.markdown("---")
                reason_input = st.text_input(
                    "Alasan Kurasi (Wajib, minimal 10 karakter):",
                    key=f"reason_{cid}",
                    placeholder="Masukkan alasan ilmiah keputusan kurasi...",
                )
                clean_reason = (reason_input or "").strip()

                tab1, tab2, tab3 = st.tabs(["PROMOTE (Varietas Baru)", "MERGE (Tautkan)", "DISCARD (Abaikan)"])

                with tab1:
                    new_name = st.text_input(
                        "Nama Varietas Baru:",
                        value=cand.get("suggested_name") or "",
                        key=f"name_{cid}",
                    )
                    hab_name = st.text_input(
                        "Nama Habitat Lapangan (Opsional):",
                        key=f"hab_opt_{cid}",
                        placeholder="Biarkan kosong jika lokasi belum diketahui",
                    )

                    if st.button("Angkat Menjadi Varietas Baru (PROMOTE)", key=f"btn_promote_{cid}"):
                        if len(clean_reason) < 10:
                            st.warning("Alasan kurasi minimal 10 karakter wajib diisi.")
                        elif not new_name.strip():
                            st.warning("Nama varietas baru wajib diisi.")
                        else:
                            decision = {
                                "action": "PROMOTE",
                                "new_variety_name": new_name.strip(),
                                "habitat": {"label": hab_name.strip()} if hab_name.strip() else None,
                                "habitat_id": hab_name.strip() if hab_name.strip() else None,
                                "reason": clean_reason,
                            }
                            resolve_candidate_api(cid, decision)
                            st.success(f"Kandidat berhasil diangkat menjadi varietas {new_name}!")
                            st.rerun()

                with tab2:
                    target_doc = st.text_input(
                        "Target Document Key (variety_id:habitat_id):",
                        key=f"target_{cid}",
                        placeholder="Contoh: plant_cabai_rawit:hab_hargobinangun",
                    )
                    if st.button("Tautkan Foto ke Dokumen (MERGE)", key=f"btn_merge_{cid}"):
                        if len(clean_reason) < 10:
                            st.warning("Alasan kurasi minimal 10 karakter wajib diisi.")
                        elif not target_doc.strip():
                            st.warning("Target document key wajib diisi.")
                        else:
                            decision = {
                                "action": "MERGE",
                                "target_doc_key": target_doc.strip(),
                                "reason": clean_reason,
                            }
                            resolve_candidate_api(cid, decision)
                            st.success("Foto berhasil ditautkan ke dokumen varietas!")
                            st.rerun()

                with tab3:
                    if st.button("Tolak dan Abaikan Citra (DISCARD)", key=f"btn_discard_{cid}"):
                        if len(clean_reason) < 10:
                            st.warning("Alasan kurasi minimal 10 karakter wajib diisi.")
                        else:
                            decision = {
                                "action": "DISCARD",
                                "reason": clean_reason,
                            }
                            resolve_candidate_api(cid, decision)
                            st.info("Citra kandidat resmi ditolak dan dicatat di daftar discarded.")
                            st.rerun()


def render_habitat_unknown_documents_panel(documents: list[dict[str, Any]] | None = None) -> None:
    """Render panel for documents created without administrative habitat (D11)."""
    st.subheader("Dokumen Pengetahuan Perlu Habitat (D11)")

    if documents is None:
        try:
            client = ui_client()
            resp = client._get("/documents?habitat_unknown=true")
            documents = resp.get("items", resp) if isinstance(resp, dict) else resp
        except Exception as e:
            st.error(f"Gagal memuat dokumen: {e}")
            return

    if not documents:
        st.info("Semua dokumen telah memiliki lokasi habitat administratif definitif.")
        return

    st.write(f"Terdapat **{len(documents)}** dokumen berstatus `habitat_unknown`.")

    for idx, doc in enumerate(documents):
        doc_key = doc.get("id") or doc.get("doc_id") or f"doc_{idx}"
        vname = doc.get("variety", {}).get("label") or "Varietas"
        media_count = len(doc.get("media_refs") or [])

        with st.expander(f"{vname} (`{doc_key}`) — {media_count} foto terlampir", expanded=True):
            st.write(f"- Varietas: **{vname}**")
            st.write(f"- Status Habitat: `habitat_unknown=true`")

            st.markdown("**Tetapkan Habitat Administratif Definitif:**")
            hab_input = st.text_input("Nama Desa / Wilayah Administratif:", key=f"hab_set_{doc_key}")

            if st.button("Simpan Habitat Definitif", key=f"btn_set_hab_{doc_key}"):
                if not hab_input.strip():
                    st.warning("Nama wilayah administratif wajib diisi.")
                else:
                    payload = {
                        "id": f"hab_{hab_input.strip().lower().replace(' ', '_')}",
                        "label": hab_input.strip(),
                        "definition": "administrative_village_v1",
                        "administrative_path": {
                            "province_name": "Indonesia",
                            "regency_name": "Kabupaten",
                            "district_name": "Kecamatan",
                            "village_name": hab_input.strip(),
                        },
                    }
                    set_document_habitat_api(doc_key, payload)
                    st.success("Habitat definitif berhasil ditetapkan!")
                    st.rerun()
