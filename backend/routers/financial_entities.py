from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user

router = APIRouter(
    prefix="/financial-entities",
    tags=["financial_entities"]
)

@router.post("/{case_id}", response_model=schemas.FinancialEntityResponse)
def create_financial_entity(
    case_id: int,
    entity: schemas.FinancialEntityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Add a financial entity (bank account, UPI ID, wallet) to a case
    """
    # Verify case exists
    case = db.query(models.Case).filter(models.Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    
    # Authorization: Only SI and above
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE]:
        raise HTTPException(status_code=403, detail="Not authorized to add financial entities")
    
    # Create financial entity
    new_entity = models.FinancialEntity(
        case_id=case_id,
        entity_type=entity.entity_type,
        bank_name=entity.bank_name,
        account_number=entity.account_number,
        ifsc_code=entity.ifsc_code,
        account_holder_name=entity.account_holder_name,
        upi_id=entity.upi_id,
        wallet_provider=entity.wallet_provider,
        transaction_id=entity.transaction_id,
        transaction_date=entity.transaction_date,
        transaction_amount=entity.transaction_amount,
        added_by_id=current_user.id,
        verification_status="pending"
    )
    
    db.add(new_entity)
    db.commit()
    db.refresh(new_entity)
    
    # Log action
    audit = models.AuditLog(
        user_id=current_user.id,
        action=f"Added financial entity to case {case.fir_number}",
        details=f"Type: {entity.entity_type}, Amount: {entity.transaction_amount}"
    )
    db.add(audit)
    db.commit()
    
    return new_entity

@router.get("/{case_id}", response_model=List[schemas.FinancialEntityResponse])
def get_case_financial_entities(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all financial entities linked to a case
    """
    entities = db.query(models.FinancialEntity).filter(
        models.FinancialEntity.case_id == case_id
    ).all()
    
    return entities

@router.patch("/{entity_id}/verify")
def verify_financial_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Mark a financial entity as verified (after data validation)
    """
    # Authorization: SHO and above
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE,
                             models.UserRole.SUB_INSPECTOR]:
        raise HTTPException(status_code=403, detail="Only SHO and above can verify entities")
    
    entity = db.query(models.FinancialEntity).filter(
        models.FinancialEntity.id == entity_id
    ).first()
    
    if not entity:
        raise HTTPException(status_code=404, detail="Financial entity not found")
    
    entity.verification_status = "verified"
    db.commit()
    
    return {"status": "verified", "entity_id": entity_id}

@router.delete("/{entity_id}")
def delete_financial_entity(
    entity_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Delete a financial entity (for corrections)
    """
    # Authorization: SI and above
    if current_user.role in [models.UserRole.CONSTABLE, models.UserRole.HEAD_CONSTABLE]:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    entity = db.query(models.FinancialEntity).filter(
        models.FinancialEntity.id == entity_id
    ).first()
    
    if not entity:
        raise HTTPException(status_code=404, detail="Financial entity not found")
    
    db.delete(entity)
    db.commit()
    
    return {"status": "deleted"}
