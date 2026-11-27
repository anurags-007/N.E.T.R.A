from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Literal, Optional, List
from datetime import datetime
from backend.models import (
    UserRole, RequestStatus, CaseType, CaseCategory,
    FinancialEntityType, TransactionEventType
)
from backend.utils.validation import validate_mobile_number

# User Schemas
class UserBase(BaseModel):
    username: str
    email: EmailStr
    role: UserRole = UserRole.OFFICER
    rank: Optional[str] = None
    station_name: Optional[str] = None
    sub_division: Optional[str] = None
    district_name: Optional[str] = None
    range_name: Optional[str] = None
    zone_name: Optional[str] = None
    state_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class PasswordChange(BaseModel):
    old_password: str
    new_password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    is_first_login: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Token Schemas
class Token(BaseModel):
    access_token: str
    token_type: str
    is_first_login: bool

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

# Case Schemas
class CaseBase(BaseModel):
    fir_number: str = Field(..., min_length=3, max_length=64)
    police_station: str = Field(..., min_length=2, max_length=120)
    case_type: CaseType
    case_category: Optional[CaseCategory] = None
    amount_involved: Optional[str] = Field("0", max_length=32)
    description: Optional[str] = Field(None, max_length=5000)

class CaseCreate(CaseBase):
    model_config = ConfigDict(extra="forbid")

class CaseStatusUpdate(BaseModel):
    status: Literal["active", "pending", "closed"]
    model_config = ConfigDict(extra="forbid")

class CaseResponse(CaseBase):
    id: int
    created_at: datetime
    status: str
    owner_id: int
    owner: UserResponse

    model_config = ConfigDict(from_attributes=True)

# Request Schemas
class RequestBase(BaseModel):
    mobile_number: str
    request_type: str # CAF, CDR
    reason: str

class RequestCreate(RequestBase):
    @field_validator("mobile_number")
    @classmethod
    def check_mobile_number(cls, v: str) -> str:
        is_valid, err = validate_mobile_number(v)
        if not is_valid:
            raise ValueError(err)
        return v.strip()

class RequestBatchCreate(BaseModel):
    mobile_numbers: List[str]
    request_type: str
    reason: str

    @field_validator("mobile_numbers")
    @classmethod
    def check_mobile_numbers(cls, values: List[str]) -> List[str]:
        cleaned = []
        for v in values:
            item = v.strip()
            if not item:
                continue
            is_valid, err = validate_mobile_number(item)
            if not is_valid:
                raise ValueError(f"{item}: {err}")
            cleaned.append(item)
        if not cleaned:
            raise ValueError("At least one valid mobile number is required")
        return cleaned

class RequestResponse(RequestBase):
    id: int
    case_id: int
    status: RequestStatus
    created_at: datetime
    reviewer_id: Optional[int] = None
    request_file_path: Optional[str] = None
    result_file_path: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# Evidence Schemas
class EvidenceResponse(BaseModel):
    id: int
    file_type: str
    original_filename: str
    uploaded_at: datetime
    file_hash: str

    model_config = ConfigDict(from_attributes=True)

# ========== FINANCIAL FRAUD MODULE SCHEMAS ==========

# Financial Entity Schemas
class FinancialEntityBase(BaseModel):
    entity_type: FinancialEntityType
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    ifsc_code: Optional[str] = None
    account_holder_name: Optional[str] = None
    upi_id: Optional[str] = None
    wallet_provider: Optional[str] = None
    transaction_id: Optional[str] = None
    transaction_date: Optional[datetime] = None
    transaction_amount: Optional[str] = None

class FinancialEntityCreate(FinancialEntityBase):
    pass

class FinancialEntityResponse(FinancialEntityBase):
    id: int
    case_id: int
    created_at: datetime
    verification_status: str
    
    model_config = ConfigDict(from_attributes=True)

# Transaction Timeline Schemas
class TransactionEventBase(BaseModel):
    event_type: TransactionEventType
    event_timestamp: datetime
    amount: Optional[str] = None
    narrative: str
    financial_entity_id: Optional[int] = None

class TransactionEventCreate(TransactionEventBase):
    pass

class TransactionEventResponse(TransactionEventBase):
    id: int
    case_id: int
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# Bank Request Schemas
class BankRequestBase(BaseModel):
    bank_name: str
    account_number: str
    request_type: str  # KYC, STATEMENT, BOTH
    reason: str
    period_from: Optional[datetime] = None
    period_to: Optional[datetime] = None

class BankRequestCreate(BankRequestBase):
    financial_entity_id: int

class BankRequestResponse(BankRequestBase):
    id: int
    case_id: int
    financial_entity_id: int
    status: RequestStatus
    created_at: datetime
    reviewer_id: Optional[int] = None
    request_file_path: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

# NPCI Request Schemas  
class NPCIRequestBase(BaseModel):
    upi_id: str
    transaction_reference: Optional[str] = None
    request_type: str  # TRANSACTION_DETAILS, FULL_HISTORY
    reason: str

class NPCIRequestCreate(NPCIRequestBase):
    financial_entity_id: int

class NPCIRequestResponse(NPCIRequestBase):
    id: int
    case_id: int
    financial_entity_id: int
    status: RequestStatus
    created_at: datetime
    reviewer_id: Optional[int] = None
    request_file_path: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

# Freeze Request Schemas
class FreezeRequestBase(BaseModel):
    bank_name: str
    account_number: str
    urgency_level: str
    justification: str

class FreezeRequestCreate(FreezeRequestBase):
    financial_entity_id: int

class FreezeRequestResponse(FreezeRequestBase):
    id: int
    case_id: int
    financial_entity_id: int
    status: str
    created_at: datetime
    freeze_initiated_at: Optional[datetime] = None
    freeze_confirmed_at: Optional[datetime] = None
    bank_reference_number: Optional[str] = None
    request_file_path: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
