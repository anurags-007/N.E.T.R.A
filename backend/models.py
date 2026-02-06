from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from backend.database import Base

class UserRole(str, enum.Enum):
    CONSTABLE = "constable"
    HEAD_CONSTABLE = "head_constable"
    SUB_INSPECTOR = "si"
    INSPECTOR = "sho"
    DY_SP = "dy_sp"
    SP = "sp"
    DIG = "dig"
    IGP = "igp"
    DGP = "dgp"
    ADMIN = "admin"
    # Legacy support (map to closest new role or migrate)
    OFFICER = "officer" 

class RequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"

class CaseCategory(str, enum.Enum):
    FINANCIAL = "financial"
    NON_FINANCIAL = "non_financial"

class CaseType(str, enum.Enum):
    # Financial Fraud Types
    UPI_FRAUD = "upi_fraud"
    BANK_TRANSFER_FRAUD = "bank_transfer_fraud"
    WALLET_FRAUD = "wallet_fraud"
    LOAN_APP_SCAM = "loan_app_scam"
    INVESTMENT_FRAUD = "investment_fraud"
    CRYPTO_FRAUD = "crypto_fraud"
    
    # Non-Financial Cyber Crime Types
    HARASSMENT = "harassment"
    SEXTORTION = "sextortion"
    FAKE_PROFILE = "fake_profile"
    EMAIL_HACK = "email_hack"
    IMPERSONATION = "impersonation"
    PHISHING = "phishing"
    
    # Legacy
    FRAUD = "fraud"
    FINANCIAL_FRAUD = "financial_fraud" # Legacy support for existing data
    OTHER = "other"

class FinancialEntityType(str, enum.Enum):
    BANK_ACCOUNT = "bank_account"
    UPI_ID = "upi_id"
    WALLET = "wallet"
    CRYPTO_WALLET = "crypto_wallet"
    PAYMENT_GATEWAY = "payment_gateway"

class TransactionEventType(str, enum.Enum):
    CALL_RECEIVED = "call_received"
    MESSAGE_RECEIVED = "message_received"
    PAYMENT = "payment"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    ACCOUNT_OPENED = "account_opened"
    CONTACT_BLOCKED = "contact_blocked"
    COMPLAINT_FILED = "complaint_filed"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(Enum(UserRole), default=UserRole.SUB_INSPECTOR)
    is_active = Column(Boolean, default=True)
    is_first_login = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Hierarchy Fields
    rank = Column(String, nullable=True) # Display rank
    station_name = Column(String, nullable=True) # Level 1
    sub_division = Column(String, nullable=True) # Level 2 (CO)
    district_name = Column(String, nullable=True) # Level 2 (SP)
    range_name = Column(String, nullable=True) # Level 3 (DIG)
    zone_name = Column(String, nullable=True) # Level 3 (IGP)
    state_name = Column(String, nullable=True) # Level 3 (DGP)

    cases = relationship("Case", back_populates="owner")
    audit_logs = relationship("AuditLog", back_populates="user")
    reviews = relationship("TelecomRequest", back_populates="reviewer") 

class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    fir_number = Column(String, unique=True, index=True)
    police_station = Column(String) # Derived from owner initially
    case_type = Column(Enum(CaseType), default=CaseType.OTHER)
    case_category = Column(Enum(CaseCategory), nullable=True)  # FINANCIAL or NON_FINANCIAL
    amount_involved = Column(String, default="0")  # Store total victim loss/fraud amount
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default="active")
    owner_id = Column(Integer, ForeignKey("users.id"))

    # Hierarchy Metadata for easy filtering
    sub_division = Column(String, nullable=True)
    district_name = Column(String, nullable=True)
    range_name = Column(String, nullable=True)
    zone_name = Column(String, nullable=True)

    owner = relationship("User", back_populates="cases")
    requests = relationship("TelecomRequest", back_populates="case")
    evidence = relationship("Evidence", back_populates="case")
    
    # Financial Fraud Module Relationships
    financial_entities = relationship("FinancialEntity", back_populates="case")
    transaction_events = relationship("TransactionTimeline", back_populates="case")
    bank_requests = relationship("BankRequest", back_populates="case")
    npci_requests = relationship("NPCIRequest", back_populates="case")
    freeze_requests = relationship("FreezeRequest", back_populates="case")

class TelecomRequest(Base):
    __tablename__ = "telecom_requests"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    mobile_number = Column(String, index=True)
    request_type = Column(String) # CAF, CDR, IP_LOGS
    status = Column(Enum(RequestStatus), default=RequestStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reason = Column(Text)
    
    # Approval Workflow
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Generated Request Letter
    request_file_path = Column(String, nullable=True) 

    case = relationship("Case", back_populates="requests")
    reviewer = relationship("User", back_populates="reviews")

class Evidence(Base):
    __tablename__ = "evidence"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    file_type = Column(String) # CDR_CSV, CAF_PDF
    file_path = Column(String) # Path to encrypted file
    file_hash = Column(String) # SHA-256
    original_filename = Column(String)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    uploaded_by_id = Column(Integer, ForeignKey("users.id"))
    
    # Hierarchy & Approval
    uploaded_by_rank = Column(String, nullable=True) # e.g. "constable"
    verification_status = Column(String, default="verified") # pending, verified, rejected
    verified_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    case = relationship("Case", back_populates="evidence")
    uploader = relationship("User", foreign_keys=[uploaded_by_id])

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    details = Column(Text, nullable=True)

    user = relationship("User", back_populates="audit_logs")

# ========== FINANCIAL FRAUD MODULE MODELS ==========

class FinancialEntity(Base):
    """Tracks bank accounts, UPI IDs, and wallet details linked to cases"""
    __tablename__ = "financial_entities"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    
    # Entity Classification
    entity_type = Column(Enum(FinancialEntityType))
    
    # Bank Account Details
    bank_name = Column(String, nullable=True)
    account_number = Column(String, nullable=True, index=True)
    ifsc_code = Column(String, nullable=True)
    account_holder_name = Column(String, nullable=True)
    
    # UPI/Wallet Details
    upi_id = Column(String, nullable=True, index=True)
    wallet_provider = Column(String, nullable=True)  # Paytm, PhonePe, etc.
    
    # Transaction Details
    transaction_id = Column(String, nullable=True, index=True)
    transaction_date = Column(DateTime(timezone=True), nullable=True)
    transaction_amount = Column(String, nullable=True)  # Store as string to avoid float issues
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    added_by_id = Column(Integer, ForeignKey("users.id"))
    verification_status = Column(String, default="pending")  # pending, verified, flagged
    
    # Relationships
    case = relationship("Case", back_populates="financial_entities")
    added_by = relationship("User")

class TransactionTimeline(Base):
    """Chronological sequence of events in financial fraud cases"""
    __tablename__ = "transaction_timeline"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    financial_entity_id = Column(Integer, ForeignKey("financial_entities.id"), nullable=True)
    
    event_type = Column(Enum(TransactionEventType))
    event_timestamp = Column(DateTime(timezone=True))
    amount = Column(String, nullable=True)
    narrative = Column(Text)  # "Victim received call from +91-XXXX claiming to be bank official"
    source_identifier = Column(String, nullable=True)
    destination_identifier = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    case = relationship("Case", back_populates="transaction_events")
    financial_entity = relationship("FinancialEntity")

class BankRequest(Base):
    """Manages requests to banks for KYC and account statements"""
    __tablename__ = "bank_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    financial_entity_id = Column(Integer, ForeignKey("financial_entities.id"))
    
    bank_name = Column(String)
    account_number = Column(String)
    request_type = Column(String)  # KYC, STATEMENT, BOTH
    
    # Request Workflow
    status = Column(Enum(RequestStatus), default=RequestStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reason = Column(Text)
    period_from = Column(DateTime(timezone=True), nullable=True)  # For statement requests
    period_to = Column(DateTime(timezone=True), nullable=True)
    
    # Approval Workflow
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    
    # Generated Files
    request_file_path = Column(String, nullable=True)
    
    # Relationships
    case = relationship("Case", back_populates="bank_requests")
    financial_entity = relationship("FinancialEntity")
    reviewer = relationship("User")

class NPCIRequest(Base):
    """Manages requests to NPCI for UPI transaction details"""
    __tablename__ = "npci_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    financial_entity_id = Column(Integer, ForeignKey("financial_entities.id"))
    
    upi_id = Column(String)
    transaction_reference = Column(String, nullable=True)
    request_type = Column(String)  # TRANSACTION_DETAILS, FULL_HISTORY
    
    # Request Workflow
    status = Column(Enum(RequestStatus), default=RequestStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    reason = Column(Text)
    
    # Approval Workflow
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    
    # Generated Files
    request_file_path = Column(String, nullable=True)
    
    # Relationships
    case = relationship("Case", back_populates="npci_requests")
    financial_entity = relationship("FinancialEntity")
    reviewer = relationship("User")

class FreezeRequest(Base):
    """Urgent account freeze requests (Section 102 CrPC)"""
    __tablename__ = "freeze_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    financial_entity_id = Column(Integer, ForeignKey("financial_entities.id"))
    
    bank_name = Column(String)
    account_number = Column(String)
    urgency_level = Column(String, default="high")  # high, critical
    justification = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    freeze_initiated_at = Column(DateTime(timezone=True), nullable=True)
    freeze_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Status Tracking
    status = Column(String, default="generated")  # generated, sent, confirmed, expired
    bank_reference_number = Column(String, nullable=True)
    
    # Generated Files
    request_file_path = Column(String, nullable=True)
    
    # Relationships
    case = relationship("Case", back_populates="freeze_requests")
    financial_entity = relationship("FinancialEntity")
