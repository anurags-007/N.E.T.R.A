import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from datetime import datetime

def generate_request_pdf(request_data: dict, case_data: dict, officer_name: str, output_path: str):
    """
    Generates an official police request letter for CAF/CDR.
    """
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 50, "OFFICIAL POLICE REQUEST")
    
    c.setFont("Helvetica", 12)
    c.drawCentredString(width / 2, height - 70, "Cyber Crime Cell / Police Station")
    
    # Date & Ref
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 120, f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    c.drawString(400, height - 120, f"Ref No: {case_data['fir_number']}/REQ/{request_data['id']}")

    # To Address
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 160, "To,")
    c.drawString(50, height - 175, "The Nodal Officer,")
    c.drawString(50, height - 190, "Telecom Service Provider (TSP)")

    # Subject
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 230, f"Subject: Urgent Request for {request_data['request_type']} under Section 91 CrPC")

    # Body
    c.setFont("Helvetica", 11)
    text_y = height - 260
    
    # Handle Multiple Numbers (Comma Separated)
    mobiles = [m.strip() for m in str(request_data['mobile_number']).split(',')]
    
    lines = [
        "Respected Sir/Madam,",
        "",
        f"This is in reference to FIR No. {case_data['fir_number']} registered at {case_data['police_station']}.",
        f"For the purpose of investigation, we urgently require the {request_data['request_type']} details",
        f"for the following mobile number(s):",
        ""
    ]
    
    # Add numbers to lines
    for i, mobile in enumerate(mobiles, 1):
        lines.append(f"{i}. {mobile}")
        
    lines.extend([
        "",
        f"Reason: {request_data['reason']}",
        "",
        "Please provide the requested data in a secure digital format (CSV/PDF) at the earliest.",
        "Your cooperation in this investigation is highly appreciated.",
    ])

    for line in lines:
        # Simple page break check (if text_y < 50) - for MVP we assume < 20 numbers
        c.drawString(50, text_y, line)
        text_y -= 15

    # Footer / Sign
    c.setFont("Helvetica-Bold", 11)
    c.drawString(400, text_y - 50, "Sincerely,")
    c.drawString(400, text_y - 80, f"{officer_name}")
    c.drawString(400, text_y - 95, "Investigating Officer")
    c.drawString(400, text_y - 110, f"Station: {case_data['police_station']}")

    # Footnote
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(width / 2, 30, "This is a system-generated official request. Confidential.")

    c.save()
    return output_path


def generate_approved_request_pdf(request_data: dict, case_data: dict, officer_name: str, 
                                  approver_name: str, approver_rank: str, output_path: str):
    """
    Generates an APPROVED & SIGNED police request letter for CAF/CDR.
    Includes approval stamp and reviewer signature.
    """
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    # APPROVED Stamp (Top Right)
    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(0, 0.5, 0)  # Green
    c.drawRightString(width - 50, height - 30, "✓ APPROVED")
    c.setFillColorRGB(0, 0, 0)  # Back to black

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, height - 50, "OFFICIAL POLICE REQUEST")
    
    c.setFont("Helvetica", 12)
    c.drawCentredString(width / 2, height - 70, "Cyber Crime Cell / Police Station")
    
    # Date & Ref
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 120, f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    c.drawString(400, height - 120, f"Ref No: {case_data['fir_number']}/REQ/{request_data['id']}")

    # To Address
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 160, "To,")
    c.drawString(50, height - 175, "The Nodal Officer,")
    c.drawString(50, height - 190, "Telecom Service Provider (TSP)")

    # Subject
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, height - 230, f"Subject: Urgent Request for {request_data['request_type']} under Section 91 CrPC")

    # Body
    c.setFont("Helvetica", 11)
    text_y = height - 260
    
    # Handle Multiple Numbers (Comma Separated)
    mobiles = [m.strip() for m in str(request_data['mobile_number']).split(',')]
    
    lines = [
        "Respected Sir/Madam,",
        "",
        f"This is in reference to FIR No. {case_data['fir_number']} registered at {case_data['police_station']}.",
        f"For the purpose of investigation, we urgently require the {request_data['request_type']} details",
        f"for the following mobile number(s):",
        ""
    ]
    
    # Add numbers to lines
    for i, mobile in enumerate(mobiles, 1):
        lines.append(f"{i}. {mobile}")
        
    lines.extend([
        "",
        f"Reason: {request_data['reason']}",
        "",
        "Please provide the requested data in a secure digital format (CSV/PDF) at the earliest.",
        "Your cooperation in this investigation is highly appreciated.",
    ])

    for line in lines:
        c.drawString(50, text_y, line)
        text_y -= 15

    # Investigating Officer Signature
    c.setFont("Helvetica-Bold", 11)
    c.drawString(400, text_y - 50, "Prepared by:")
    c.drawString(400, text_y - 70, f"{officer_name}")
    c.drawString(400, text_y - 85, "Investigating Officer")
    c.drawString(400, text_y - 100, f"Station: {case_data['police_station']}")
    
    # Approval Signature (Below)
    text_y -= 150
    c.setFillColorRGB(0, 0.5, 0)  # Green
    c.setFont("Helvetica-Bold", 12)
    c.drawString(400, text_y, "APPROVED & SIGNED:")
    c.setFillColorRGB(0, 0, 0)  # Black
    
    c.setFont("Helvetica-Bold", 11)
    c.drawString(400, text_y - 25, f"{approver_name}")
    c.drawString(400, text_y - 40, f"{approver_rank}")
    c.drawString(400, text_y - 55, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Official Seal Placeholder
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(400, text_y - 75, "[Official Seal]")

    # Footnote
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(width / 2, 30, "This is an officially approved and signed government document. Confidential.")

    c.save()
    return output_path
