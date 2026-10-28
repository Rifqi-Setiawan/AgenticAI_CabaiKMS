"""Streamlit UI components for Image Candidates review and Habitat Unknown documents curation."""

from __future__ import annotations

from typing import Any
import streamlit as st

from src.integrations.client import ui_client
from src.storage.document_contracts import AdministrativePath
from src.storage.identity_resolution import compute_habitat_id


def validate_curator_reason(reason: str | None) -> bool:
    """Validate curator reason string meets minimum 10 characters requirement."""
    return bool(reason and len(str(reason).strip()) >= 10)


def resolve_candidate_api(candidate_id: str, decision: dict[str, Any], *, client: Any | None = None) -> dict[str, Any]:
    """Call KMS API to resolve a candidate (httpx ``json`` kwarg)."""
    c = client or ui_client()
    return c.request("POST", f"/candidates/{candidate_id}/resolve", json=decision)


def set_document_habitat_api(doc_key: str, habitat_payload: dict[str, Any], *, client: Any | None = None) -> dict[str, Any]:
    """Call KMS API to set the resolved habitat of an unknown-habitat document (httpx ``json`` kwarg)."""
    c = client or ui_client()
    return c.request("POST", f"/documents/{doc_key}/habitat", json=habitat_payload)


def load_all_documents(client: Any, page_size: int = 200, **params: Any) -> list[dict[str, Any]]:
    """Load every committed document page by page; raises on failure (callers must surface it)."""
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        resp = client.request("GET", "/documents", params={**params, "limit": page_size, "offset": offset})
        page = resp.get("items", resp) if isinstance(resp, dict) else resp
        if not isinstance(page, list):
            break
        items.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return items


def render_candidates_panel(candidates: list[dict[str, Any]] | None = None) -> None:
    """Render candidates queue panel for human researcher review (one-by-one, no clustering)."""
    st.subheader("Antrean Kandidat Varietas Baru (Citra Google Drive)")

    client = ui_client()
    if candidates is None:
        try:
            candidates = client.request("GET", "/candidates", params={"status": "CANDIDATE"})
        except Exception as e:
            st.error(f"Gagal memuat kandidat varietas: {e}")
            return

    if not candidates:
        st.info("Tidak ada kandidat varietas baru yang menunggu peninjauan.")
        return

    # Fetch registered documents to extract authentic habitats and existing documents for MERGE
    existing_habitats: dict[str, str] = {}
    registered_docs: dict[str, dict[str, Any]] = {}
    try:
        for d in load_all_documents(client):
            d_id = d.get("id") or d.get("doc_id")
            if d_id:
                registered_docs[d_id] = d
            hab = d.get("habitat")
            if hab and isinstance(hab, dict) and hab.get("id") and hab.get("id") != "habitat_unknown":
                existing_habitats[hab["id"]] = f"{hab.get('label', hab['id'])} ({hab['id']})"
        st.caption(f"{len(registered_docs)} dokumen terdaftar dimuat untuk pilihan habitat dan MERGE.")
    except Exception as exc:
        st.warning(f"Daftar dokumen/habitat gagal dimuat; pilihan habitat dan MERGE tidak lengkap: {exc}")

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
                    hab_options = ["(Habitat Belum Diketahui - D11)"] + list(existing_habitats.keys())
                    selected_hab_id = st.selectbox(
                        "Pilih Habitat Terdaftar:",
                        options=hab_options,
                        format_func=lambda k: existing_habitats.get(k, k),
                        key=f"hab_sel_{cid}",
                    )
                    hab_name = st.text_input(
                        "Atau Nama Habitat Lapangan Terdaftar (Opsional):",
                        key=f"hab_opt_{cid}",
                        placeholder="Biarkan kosong jika lokasi belum diketahui",
                    )
                    clean_hab = (hab_name or "").strip()
                    if clean_hab and "unknown" not in clean_hab.lower():
                        chosen_hid = clean_hab
                    elif selected_hab_id and selected_hab_id != "(Habitat Belum Diketahui - D11)":
                        chosen_hid = selected_hab_id
                    else:
                        chosen_hid = None

                    if st.button("Angkat Menjadi Varietas Baru (PROMOTE)", key=f"btn_promote_{cid}"):
                        if not validate_curator_reason(clean_reason):
                            st.warning("Alasan kurasi minimal 10 karakter wajib diisi.")
                        elif not new_name.strip():
                            st.warning("Nama varietas baru wajib diisi.")
                        else:
                            decision = {
                                "action": "PROMOTE",
                                "new_variety_name": new_name.strip(),
                                "habitat": None,
                                "habitat_id": chosen_hid,
                                "reason": clean_reason,
                            }
                            try:
                                resolve_candidate_api(cid, decision, client=client)
                                st.success(f"Kandidat berhasil diangkat menjadi varietas {new_name}!")
                                st.rerun()
                            except Exception as ex:
                                err_msg = str(ex)
                                if "already exists" in err_msg.lower():
                                    st.error(f"Dokumen sudah ada: {err_msg}. Gunakan tab MERGE untuk menautkan foto ke dokumen tersebut!")
                                else:
                                    st.error(f"Gagal mempromosikan kandidat: {ex}")

                with tab2:
                    target_doc_options = [""] + list(registered_docs.keys())
                    target_doc_sel = st.selectbox(
                        "Pilih Dokumen Target (Varietas Terdaftar):",
                        options=target_doc_options,
                        format_func=lambda k: f"{registered_docs[k].get('variety', {}).get('label', k)} ({k}) [v{registered_docs[k].get('version', 1)}]" if k in registered_docs else "-- Pilih Dokumen --",
                        key=f"target_sel_{cid}",
                    )
                    target_doc_man = st.text_input(
                        "Atau Target Document Key manual:",
                        key=f"target_{cid}",
                        placeholder="Contoh: plant_cabai_rawit:hab_hargobinangun",
                    )
                    final_target = target_doc_man.strip() or target_doc_sel.strip()
                    expected_v = registered_docs.get(final_target, {}).get("version")

                    if st.button("Tautkan Foto ke Dokumen (MERGE)", key=f"btn_merge_{cid}"):
                        if not validate_curator_reason(clean_reason):
                            st.warning("Alasan kurasi minimal 10 karakter wajib diisi.")
                        elif not final_target:
                            st.warning("Target document key wajib dipilih atau diisi.")
                        else:
                            decision = {
                                "action": "MERGE",
                                "target_doc_key": final_target,
                                "expected_version": expected_v,
                                "reason": clean_reason,
                            }
                            try:
                                resolve_candidate_api(cid, decision, client=client)
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
                                resolve_candidate_api(cid, decision, client=client)
                                st.info("Citra kandidat resmi ditolak dan dicatat di daftar discarded.")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Gagal membuang kandidat: {ex}")


def render_habitat_unknown_documents_panel(documents: list[dict[str, Any]] | None = None) -> None:
    """Render panel for documents created without administrative habitat (D11)."""
    st.subheader("Dokumen Pengetahuan Perlu Habitat (D11)")

    client = ui_client()
    if documents is None:
        try:
            resp = client.request("GET", "/documents", params={"habitat_unknown": "true"})
            documents = resp.get("items", resp) if isinstance(resp, dict) else resp
        except Exception as e:
            st.error(f"Gagal memuat dokumen: {e}")
            return

    if not documents:
        st.info("Semua dokumen telah memiliki lokasi habitat administratif definitif.")
        return

    st.write(f"Terdapat **{len(documents)}** dokumen berstatus `habitat_unknown`.")

    # Fetch existing habitats for dropdown
    existing_habitats: dict[str, dict[str, Any]] = {}
    try:
        for d in load_all_documents(client):
            hab = d.get("habitat")
            if hab and isinstance(hab, dict) and hab.get("id") and hab.get("id") != "habitat_unknown":
                existing_habitats[hab["id"]] = hab
    except Exception as exc:
        st.warning(f"Daftar habitat terdaftar gagal dimuat; hanya input 4 tingkat yang tersedia: {exc}")

    for idx, doc in enumerate(documents):
        doc_key = doc.get("id") or doc.get("doc_id") or f"doc_{idx}"
        vname = doc.get("variety", {}).get("label") or "Varietas"
        media_count = len(doc.get("media_refs") or [])

        with st.expander(f"{vname} (`{doc_key}`) — {media_count} foto terlampir", expanded=True):
            st.write(f"- Varietas: **{vname}**")
            st.write(f"- Status Habitat: `habitat_unknown=true`")

            st.markdown("**Tetapkan Habitat Administratif Definitif:**")

            mode = st.radio(
                "Pilihan Sumber Habitat:",
                ["Definisikan Wilayah Administratif Baru (4 Tingkat)", "Pilih dari Habitat Terdaftar"],
                key=f"mode_{doc_key}",
            )

            if mode == "Pilih dari Habitat Terdaftar" and existing_habitats:
                sel_hid = st.selectbox(
                    "Pilih Habitat Terdaftar:",
                    options=list(existing_habitats.keys()),
                    format_func=lambda k: f"{existing_habitats[k].get('label', k)} ({k})",
                    key=f"sel_hab_{doc_key}",
                )
                if st.button("Terapkan Habitat Terdaftar", key=f"btn_apply_existing_{doc_key}"):
                    payload = existing_habitats[sel_hid]
                    try:
                        set_document_habitat_api(doc_key, payload, client=client)
                        st.success("Habitat definitif berhasil ditetapkan!")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Gagal menetapkan habitat: {ex}")
            else:
                col_p, col_r = st.columns(2)
                with col_p:
                    prov = st.text_input("Provinsi:", key=f"prov_{doc_key}", placeholder="Nama provinsi")
                    kab = st.text_input("Kabupaten/Kota:", key=f"kab_{doc_key}", placeholder="Nama kabupaten/kota")
                with col_r:
                    kec = st.text_input("Kecamatan:", key=f"kec_{doc_key}", placeholder="Nama kecamatan")
                    desa = st.text_input("Desa/Kelurahan:", key=f"desa_{doc_key}", placeholder="Pananjung")

                if st.button("Simpan Habitat Definitif", key=f"btn_set_hab_{doc_key}"):
                    # All four administrative tiers come from the curator; nothing is defaulted.
                    p_val = prov.strip()
                    k_val = kab.strip()
                    kc_val = kec.strip()
                    d_val = desa.strip()

                    if not p_val or not k_val or not kc_val or not d_val:
                        st.warning("Seluruh jenjang administratif (Provinsi, Kabupaten, Kecamatan, Desa) wajib diisi.")
                    elif any(v.lower() in ("unknown", "tidak diketahui") for v in (p_val, k_val, kc_val, d_val)):
                        st.warning("Wilayah administratif tidak boleh bernilai 'Unknown'.")
                    else:
                        admin_path = AdministrativePath(
                            province_name=p_val,
                            regency_name=k_val,
                            district_name=kc_val,
                            village_name=d_val,
                        )
                        hid = compute_habitat_id(admin_path)
                        payload = {
                            "id": hid,
                            "label": f"Desa {d_val}",
                            "definition": "administrative_village_v1",
                            "administrative_path": admin_path.model_dump(mode="json"),
                        }
                        try:
                            set_document_habitat_api(doc_key, payload, client=client)
                            st.success("Habitat definitif berhasil ditetapkan!")
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Gagal menetapkan habitat: {ex}")
