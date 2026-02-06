import sys
import os
import pandas as pd
from datetime import datetime, timedelta
import io

# Add backend to path
sys.path.append(os.getcwd())

from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine
from backend import models, schemas
from backend.utils.security import get_password_hash

def seed_data():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # 1. Create Users
        admin_user = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin_user:
            admin_user = models.User(
                username="admin",
                email="admin@netra.gov.in",
                hashed_password=get_password_hash("admin123"),
                role=models.UserRole.ADMIN,
                rank="SP",
                station_name="HQ",
                is_active=True,
                is_first_login=False
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)

        si_user = db.query(models.User).filter(models.User.username == "si_amit").first()
        if not si_user:
            si_user = models.User(
                username="si_amit",
                email="amit@uppolice.gov.in",
                hashed_password=get_password_hash("password123"),
                role=models.UserRole.SUB_INSPECTOR,
                rank="SI",
                district_name="Lucknow",
                station_name="Kotwali",
                is_active=True,
                is_first_login=False
            )
            db.add(si_user)
            db.commit()
            db.refresh(si_user)

        # 2. Financial Fraud Case
        case1 = db.query(models.Case).filter(models.Case.fir_number == "FIR/FIN/2026/001").first()
        if not case1:
            case1 = models.Case(
                fir_number="FIR/FIN/2026/001",
                police_station="Kotwali",
                case_type=models.CaseType.UPI_FRAUD,
                case_category=models.CaseCategory.FINANCIAL,
                amount_involved="50000",
                description="Victim cheated of Rs. 50,000 via fake QR code scan.",
                status="active",
                owner_id=si_user.id
            )
            db.add(case1)
            db.commit()
            db.refresh(case1)

        # 3. Non-Financial Fraud Case
        case2 = db.query(models.Case).filter(models.Case.fir_number == "FIR/CYB/2026/002").first()
        if not case2:
            case2 = models.Case(
                fir_number="FIR/CYB/2026/002",
                police_station="Civil Lines",
                case_type=models.CaseType.HARASSMENT,
                case_category=models.CaseCategory.NON_FINANCIAL,
                description="Cyber stalking and harassment of female victim using multiple mobile numbers.",
                status="active",
                owner_id=si_user.id
            )
            db.add(case2)
            db.commit()
            db.refresh(case2)

        # 4. Financial Entities
        fe1 = models.FinancialEntity(
            case_id=case1.id,
            entity_type=models.FinancialEntityType.UPI_ID,
            upi_id="fraudster@upi",
            account_holder_name="Fake Name",
            bank_name="Payment Bank",
            transaction_amount="50000",
            transaction_id="TXN123456789",
            verification_status="flagged",
            added_by_id=si_user.id
        )
        db.add(fe1)
        
        fe2 = models.FinancialEntity(
            case_id=case1.id,
            entity_type=models.FinancialEntityType.BANK_ACCOUNT,
            account_number="987654321098",
            bank_name="XYZ Bank",
            account_holder_name="Mule Holder",
            transaction_amount="50000",
            verification_status="pending",
            added_by_id=si_user.id
        )
        db.add(fe2)

        # 5. Telecom Requests
        tr1 = models.TelecomRequest(
            case_id=case2.id,
            mobile_number="9876543210",
            request_type="CDR",
            status=models.RequestStatus.PENDING,
            reason="Primary suspect number identified from victim's call logs."
        )
        db.add(tr1)
        
        tr2 = models.TelecomRequest(
            case_id=case1.id,
            mobile_number="9999988888",
            request_type="CAF",
            status=models.RequestStatus.APPROVED,
            reason="Number linked to the fraudster UPI ID profile.",
            reviewer_id=admin_user.id,
            reviewed_at=datetime.utcnow()
        )
        db.add(tr2)

        # 6. Transaction Timeline
        tt1 = models.TransactionTimeline(
            case_id=case1.id,
            event_type=models.TransactionEventType.CALL_RECEIVED,
            event_timestamp=datetime.utcnow() - timedelta(hours=2),
            narrative="Suspect called victim impersonating bank officer.",
            source_identifier="9876543210"
        )
        db.add(tt1)
        
        tt2 = models.TransactionTimeline(
            case_id=case1.id,
            event_type=models.TransactionEventType.PAYMENT,
            event_timestamp=datetime.utcnow() - timedelta(hours=1),
            narrative="Victim scanned QR code and Rs. 50,000 debited.",
            amount=50000.0,
            destination_identifier="fraudster@upi"
        )
        db.add(tt2)

        db.commit()
        print("Database seeded successfully!")

        # 7. Generate Dummy Files for Testing
        os.makedirs("test_data", exist_ok=True)
        
        # CSV for File Search
        df_csv = pd.DataFrame({
            'Mobile': ['9876543210', '9999988888'],
            'UPI': ['fraudster@upi', 'test@upi'],
            'Account': ['987654321098', '111222333444']
        })
        df_csv.to_csv("test_data/suspect_list.csv", index=False)
        print("Created test_data/suspect_list.csv")
        
        # Excel for File Search
        df_excel = pd.DataFrame({
            'Entity': ['9876543210', 'fraudster@upi'],
            'Type': ['Mobile', 'UPI']
        })
        df_excel.to_excel("test_data/suspect_details.xlsx", index=False)
        print("Created test_data/suspect_details.xlsx")
        
        # PDF (Simple Text file renamed to .pdf for basic extension test or use reportlab)
        # Since I am not sure if reportlab is fully ready, I'll just write a text file with PDF extension
        # and hope the PDF parser handles it or I'll just skip PDF for now if it fails.
        # Actually I saw 'pypdf' so I should create a real PDF if possible.
        try:
             from reportlab.pdfgen import canvas
             c = canvas.Canvas("test_data/investigation_report.pdf")
             c.drawString(100, 750, "Suspect Mobile: 9876543210")
             c.drawString(100, 730, "Fraud UPI: fraudster@upi")
             c.save()
             print("Created test_data/investigation_report.pdf")
        except ImportError:
             with open("test_data/investigation_report.pdf", "w") as f:
                 f.write("%PDF-1.4\n1 0 obj\n<< /Title (Test) >>\nendobj\ntext: 9876543210")
             print("Created dummy text-based investigation_report.pdf")

    except Exception as e:
        db.rollback()
        print(f"Error seeding data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
