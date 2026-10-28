"""Streamlit UI components for Image Candidates review and Habitat Unknown documents curation."""

from __future__ import annotations

from typing import Any
import streamlit as st

from src.integrations.client import ui_client


def validate_curator_reason(reason: str | None) -> bool:
    """Validate curator reason string meets minimum 10 characters requirement."""
    return bool(reason and len(str(reason).strip()) >= 10)


def resolve_candidate_api(arg1: Any, arg2: Any, arg3: Any = None) -> dict[str, Any]:
    """Call KMS API to resolve a candidate."""
    if arg3 is not None:
        client = arg1
        candidate_id = arg2
        decision = arg3
    elif hasattr(arg1, "request"):
        client = arg1
        candidate_id = arg2
        decision = None
    else:
        client = ui_client()
        candidate_id = arg1
        decision = arg2
    return client.request("POST", f"/candidates/{candidate_id}/resolve", json_body=decision)


def set_document_habitat_api(arg1: Any, arg2: Any, arg3: Any = None) -> dict[str, Any]:
    """Call KMS API to set resolved habitat on an unknown-habitat document."""
    if arg3 is not None:
        client = arg1
        doc_key = arg2
        habitat_payload = arg3
    elif hasattr(arg1, "request"):
        client = arg1
        doc_key = arg2
        habitat_payload = None
    else:
        client = ui_client()
        doc_key = arg1
        habitat_payload = arg2
    return client.request("POST", f"/documents/{doc_key}/habitat", json_body=habitat_payload)


def render_candidates_panel(candidates: list[dict[str, Any]] | None = None) -> None:
    """Render candidates queue panel for human researcher review (one-by-one, no clustering)."""
    st.subheader("Antrean Kandidat Varietas Baru (Citra Google Drive)")

    if candidates is None:
        try:
            client = ui_client()
            candidates = client.request("GET", "/candidates", params={"status": "CANDIDATE"})
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
                        "Nama Habitat Lapangan Terdaftar (Opsional):",
                        key=f"hab_opt_{cid}",
                        placeholder="Biarkan kosong jika lokasi belum diketahui",
                    )
                    clean_hab = (hab_name or "").strip()

                    if st.button("Angkat Menjadi Varietas Baru (PROMOTE)", key=f"btn_promote_{cid}"):
                        if not validate_curator_reason(clean_reason):
                            st.warning("Alasan kurasi minimal 10 karakter wajib diisi.")
                        elif not new_name.strip():
                            st.warning("Nama varietas baru wajib diisi.")
                        else:
                            chosen_hid = clean_hab if clean_hab and "unknown" not in clean_hab.lower() else None
                            decision = {
                                "action": "PROMOTE",
                                "new_variety_name": new_name.strip(),
                                "habitat": None,
                                "habitat_id": chosen_hid,
                                "reason": clean_reason,
                            }
                            try:
                                resolve_candidate_api(cid, decision)
                                st.success(f"Kandidat berhasil diangkat menjadi varietas {new_name}!")
                                st.rerun()
                            except Exception as ex:
                                err_msg = str(ex)
                                if "already exists" in err_msg.lower():
                                    st.error(f"Dokumen sudah ada: {err_msg}. Gunakan tab MERGE untuk menautkan foto ke dokumen tersebut!")
                                else:
                                    st.error(f"Gagal mempromosikan kandidat: {ex}")

                with tab2:
                    target_doc = st.text_input(
                        "Target Document Key (variety_id:habitat_id):",
                        key=f"target_{cid}",
                        placeholder="Contoh: plant_cabai_rawit:hab_hargobinangun",
                    )
                    final_target = target_doc.strip()

                    if st.button("Tautkan Foto ke Dokumen (MERGE)", key=f"btn_merge_{cid}"):
                        if not validate_curator_reason(clean_reason):
                            st.warning("Alasan kurasi minimal 10 karakter wajib diisi.")
                        elif not final_target:
                            st.warning("Target document key wajib diisi.")
                        else:
                            decision = {
                                "action": "MERGE",
                                "target_doc_key": final_target,
                                "reason": clean_reason,
                            }
                            try:
                                resolve_candidate_api(cid, decision)
                                st.success("Foto berhasil ditautkan ke dokumen varietas!")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Gagal menautkan foto: {ex}")

                with tab3:
                    if st.button("Tolak dan Abaikan Citra (DISCARD)", key=f"btn_discard_{cid}"):
                        if not validate_curator_reason(clean_reason):
                            st.warning("Alasan kurasi minimal 10 karakter wajib diisi.")
                        else:
                            decision = {
                                "action": "DISCARD",
                                "reason": clean_reason,
                            }
                            try:
                                resolve_candidate_api(cid, decision)
                                st.info("Citra kandidat resmi ditolak dan dicatat di daftar discarded.")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Gagal membuang kandidat: {ex}")


def render_habitat_unknown_documents_panel(documents: list[dict[str, Any]] | None = None) -> None:
    """Render panel for documents created without administrative habitat (D11)."""
    st.subheader("Dokumen Pengetahuan Perlu Habitat (D11)")

    if documents is None:
        try:
            client = ui_client()
            resp = client.request("GET", "/documents", params={"habitat_unknown": "true"})
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
                    hab_id = f"hab_{hab_input.strip().lower().replace(' ', '_')}"
                    payload = {
                        "id": hab_id,
                        "label": f"Desa {hab_input.strip()}",
                        "definition": "administrative_village_v1",
                        "administrative_path": {
                            "province_name": "Indonesia",
                            "regency_name": "Kabupaten",
                            "district_name": "Kecamatan",
                            "village_name": hab_input.strip(),
                        },
                    }
                    try:
                        set_document_habitat_api(doc_key, payload)
                        st.success("Habitat definitif berhasil ditetapkan!")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Gagal menetapkan habitat: {ex}")
