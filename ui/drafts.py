"""Explicit save/restore controls for allowlisted synthetic work only."""
from __future__ import annotations

import streamlit as st

from utils.drafts import capture_synthetic_draft, read_synthetic_draft, restore_synthetic_draft, synthetic_draft_bytes


def _restore_uploaded_draft() -> None:
    upload = st.session_state.get("synthetic_work_draft_upload")
    if upload is None:
        st.session_state["synthetic_work_draft_notice"] = ("error", "เลือกไฟล์ร่างงาน JSON ก่อนนำเข้า")
        return
    try:
        draft = read_synthetic_draft(upload.getvalue())
        restore_synthetic_draft(st.session_state, draft)
    except ValueError as exc:
        st.session_state["synthetic_work_draft_notice"] = ("error", str(exc))
    else:
        st.session_state["synthetic_work_draft_notice"] = (
            "success", "คืนค่าร่างงานสมมติแล้ว ระบบตรวจสอบใหม่จากข้อมูลที่นำเข้า ไม่มีการนำเข้าผลอนุมัติหรือผลประเมินเดิม",
        )


def render_synthetic_draft_controls() -> None:
    """Call after the reporting editor saves its current numeric rows each render.

    Import runs in a callback before the next render, so restored widget state is
    applied before those widgets exist. Downloads use the current saved rows.
    """
    with st.expander("บันทึกและคืนค่าร่างงานสมมติ (JSON)", icon=":material/save:"):
        st.caption("บันทึกเฉพาะรูปแบบรายงาน ตัวเลขสมมติ และหัวข้อบทเรียน สำหรับเปิดต่อใน session ใหม่ ไม่รวมผลประเมินหรือข้อมูลจากโมดูลผู้ป่วย")
        st.warning("ใช้ไฟล์ข้อมูลสมมติเท่านั้น ฟังก์ชันนี้ไม่ใช่การลบข้อมูลระบุตัวบุคคล ไม่ควรใส่ข้อมูลผู้ป่วยจริงในไฟล์หรือชื่อหน่วยงาน")
        try:
            data = synthetic_draft_bytes(capture_synthetic_draft(st.session_state))
        except ValueError as exc:
            st.error(f"ยังบันทึกร่างงานไม่ได้: {exc}")
        else:
            st.download_button("ดาวน์โหลดร่างงานสมมติ", data, "synthetic-work-draft.json", "application/json",
                               key="synthetic_work_draft_download", icon=":material/download:")
        st.file_uploader("ไฟล์ร่างงานสมมติที่บันทึกไว้ (JSON · ไม่เกิน 256 KiB)", type=["json"], key="synthetic_work_draft_upload")
        st.caption("การนำเข้าจะแทนที่เฉพาะร่างงาน Report designer และตัวเลือกบทเรียน ไม่แก้ข้อมูล CBC / PCR / screening หรือกลุ่มงานอื่น")
        st.button("นำเข้าร่างงานสมมติ", key="synthetic_work_draft_restore", on_click=_restore_uploaded_draft, icon=":material/upload:")
        notice = st.session_state.get("synthetic_work_draft_notice")
        if notice:
            getattr(st, notice[0])(notice[1])
