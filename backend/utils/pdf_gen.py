import os
from datetime import datetime, timezone
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas


def _draw_wrapped_lines(c: canvas.Canvas, lines: list[str], start_y: float, width: float, margin_x: int = 50) -> float:
    """Draw wrapped lines with automatic pagination so long values never clip off-page."""
    max_width = width - (margin_x * 2)
    text_y = start_y
    for raw_line in lines:
        if raw_line == "":
            text_y -= 15
            if text_y < 140:
                c.showPage()
                c.setFont("Helvetica", 11)
                text_y = letter[1] - 50
            continue

        wrapped = simpleSplit(str(raw_line), "Helvetica", 11, max_width)
        for seg in wrapped:
            if text_y < 140:
                c.showPage()
                c.setFont("Helvetica", 11)
                text_y = letter[1] - 50
            c.drawString(margin_x, text_y, seg)
            text_y -= 15
    return text_y


def generate_request_pdf(request_data: dict, case_data: dict, officer_name: str, output_path: str):
    """Generates an official police request letter for CAF/CDR under Section 94 BNSS, 2023."""
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 50, "OFFICIAL POLICE REQUEST")

    c.setFont("Helvetica", 12)
    c.drawCentredString(width / 2, height - 70, "Cyber Crime Cell / Police Station")

    # Date & Ref
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 120, f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    c.drawString(360, height - 120, f"Ref No: {str(case_data['fir_number'])[:32]}/REQ/{request_data['id']}")

    # To Address
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 160, "To,")
    c.drawString(50, height - 175, "The Nodal Officer,")
    c.drawString(50, height - 190, "Telecom Service Provider (TSP)")

    # Subject (wrapped)
    c.setFont("Helvetica-Bold", 12)
    subject_lines = simpleSplit(
        f"Subject: Urgent Request for {request_data['request_type']} under Section 94 BNSS, 2023",
        "Helvetica-Bold",
        12,
        width - 100,
    )
    subj_y = height - 230
    for sline in subject_lines:
        c.drawString(50, subj_y, sline)
        subj_y -= 16

    # Body
    c.setFont("Helvetica", 11)
    mobiles = [m.strip() for m in str(request_data["mobile_number"]).split(",") if m.strip()]

    lines = [
        "Respected Sir/Madam,",
        "",
        f"This is in reference to FIR No. {case_data['fir_number']} registered at {case_data['police_station']}.",
        f"For the purpose of investigation under Section 94 of the Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023, we urgently require the {request_data['request_type']} details for the following mobile number(s):",
        "",
    ]
    for i, mobile in enumerate(mobiles, 1):
        lines.append(f"{i}. {mobile}")

    lines.extend([
        "",
        f"Reason: {request_data['reason']}",
        "",
        "Please provide the requested data in a secure digital format (CSV/PDF) with a Section 63 BSA, 2023 certificate at the earliest.",
        "Your cooperation in this investigation is highly appreciated.",
    ])

    text_y = _draw_wrapped_lines(c, lines, subj_y - 14, width)

    if text_y < 140:
        c.showPage()
        text_y = height - 60

    # Footer / Sign
    c.setFont("Helvetica-Bold", 11)
    c.drawString(400, text_y - 35, "Sincerely,")
    c.drawString(400, text_y - 60, f"{officer_name}")
    c.drawString(400, text_y - 75, "Investigating Officer")
    c.drawString(400, text_y - 90, f"Station: {case_data['police_station']}")

    # Footnote
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(width / 2, 30, "This is a system-generated official request under Section 94 BNSS, 2023. Confidential.")

    c.save()
    return output_path


def generate_approved_request_pdf(
    request_data: dict,
    case_data: dict,
    officer_name: str,
    approver_name: str,
    approver_rank: str,
    output_path: str,
):
    """Generates an APPROVED & SIGNED police request letter under Section 94 BNSS, 2023."""
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    # APPROVED Stamp (Top Right)
    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(0, 0.5, 0)
    c.drawRightString(width - 50, height - 30, "APPROVED")
    c.setFillColorRGB(0, 0, 0)

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 50, "OFFICIAL POLICE REQUEST")

    c.setFont("Helvetica", 12)
    c.drawCentredString(width / 2, height - 70, "Cyber Crime Cell / Police Station")

    # Date & Ref
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 120, f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    c.drawString(360, height - 120, f"Ref No: {str(case_data['fir_number'])[:32]}/REQ/{request_data['id']}")

    # To Address
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 160, "To,")
    c.drawString(50, height - 175, "The Nodal Officer,")
    c.drawString(50, height - 190, "Telecom Service Provider (TSP)")

    # Subject
    c.setFont("Helvetica-Bold", 12)
    subject_lines = simpleSplit(
        f"Subject: Urgent Request for {request_data['request_type']} under Section 94 BNSS, 2023",
        "Helvetica-Bold",
        12,
        width - 100,
    )
    subj_y = height - 230
    for sline in subject_lines:
        c.drawString(50, subj_y, sline)
        subj_y -= 16

    c.setFont("Helvetica", 11)
    mobiles = [m.strip() for m in str(request_data["mobile_number"]).split(",") if m.strip()]

    lines = [
        "Respected Sir/Madam,",
        "",
        f"This is in reference to FIR No. {case_data['fir_number']} registered at {case_data['police_station']}.",
        f"For the purpose of investigation under Section 94 BNSS, 2023, we urgently require the {request_data['request_type']} details for the following mobile number(s):",
        "",
    ]
    for i, mobile in enumerate(mobiles, 1):
        lines.append(f"{i}. {mobile}")

    lines.extend([
        "",
        f"Reason: {request_data['reason']}",
        "",
        "Please provide the requested data in a secure digital format (CSV/PDF) with a Section 63 BSA, 2023 certificate at the earliest.",
        "Your cooperation in this investigation is highly appreciated.",
    ])

    text_y = _draw_wrapped_lines(c, lines, subj_y - 14, width)

    if text_y < 230:
        c.showPage()
        text_y = height - 60

    # Investigating Officer Signature
    c.setFont("Helvetica-Bold", 11)
    c.drawString(400, text_y - 35, "Prepared by:")
    c.drawString(400, text_y - 55, f"{officer_name}")
    c.drawString(400, text_y - 70, "Investigating Officer")
    c.drawString(400, text_y - 85, f"Station: {case_data['police_station']}")

    # Approval Signature (Below)
    text_y -= 130
    c.setFillColorRGB(0, 0.5, 0)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(400, text_y, "APPROVED & SIGNED:")
    c.setFillColorRGB(0, 0, 0)

    c.setFont("Helvetica-Bold", 11)
    c.drawString(400, text_y - 25, f"{approver_name}")
    c.drawString(400, text_y - 40, f"{approver_rank}")
    c.drawString(400, text_y - 55, f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    c.setFont("Helvetica-Oblique", 9)
    c.drawString(400, text_y - 75, "[Official Seal]")

    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(width / 2, 30, "This is an officially approved and signed government document under Section 94 BNSS, 2023. Confidential.")

    c.save()
    return output_path


def generate_bsa_63_manifest(
    case_data: dict,
    evidence_records: list[dict],
    generated_by: str = "System",
) -> dict:
    """Build a Section 63(4)(c) BSA, 2023 electronic evidence hash-manifest payload."""
    generated_at = datetime.now(timezone.utc).isoformat()
    items = []
    for ev in evidence_records:
        uploaded_at = ev.get("uploaded_at")
        if hasattr(uploaded_at, "isoformat"):
            uploaded_at = uploaded_at.isoformat()
        items.append({
            "evidence_id": ev["id"],
            "original_filename": ev["original_filename"],
            "file_type": ev["file_type"],
            "sha256_plaintext_hash": ev["file_hash"],
            "uploaded_at_utc": uploaded_at,
            "uploaded_by": ev.get("uploaded_by", "Unknown"),
            "verification_status": ev.get("verification_status", "verified"),
        })

    return {
        "statute": "Section 63(4)(c), Bharatiya Sakshya Adhiniyam (BSA), 2023",
        "fir_number": case_data["fir_number"],
        "police_station": case_data["police_station"],
        "generated_at_utc": generated_at,
        "generated_by_officer": generated_by,
        "total_evidence_items": len(items),
        "hash_algorithm": "SHA-256 (computed on raw plaintext bytes prior to MultiFernet encryption)",
        "part_a_declaration": {
            "source_system": "N.E.T.R.A. Digital Evidence Vault (FastAPI / MultiFernet Vault)",
            "lawful_control_statement": (
                f"Electronic records listed herein were produced/ingested under lawful police control "
                f"at {case_data['police_station']} in connection with FIR {case_data['fir_number']}."
            ),
            "system_integrity_statement": (
                "The computer system operated properly during ingestion and retrieval; plaintext SHA-256 "
                "digests were recorded at ingestion and re-verified on decryption."
            ),
        },
        "evidence_manifest": items,
    }
