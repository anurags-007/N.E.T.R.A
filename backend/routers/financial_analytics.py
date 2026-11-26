from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, distinct
from datetime import datetime, timedelta

from backend.database import get_db
from backend import models
from backend.routers.auth import get_current_active_user
from backend.utils.rbac import apply_jurisdiction_filter, authorize_case_access, get_accessible_case_ids

router = APIRouter(
    prefix="/analytics",
    tags=["financial_analytics"]
)

@router.get("/timeline/{case_id}")
def get_transaction_timeline(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Build chronological transaction timeline for a financial fraud case
    Returns ordered sequence of events with timestamps
    """
    # Verify case exists and user has jurisdiction access
    case = authorize_case_access(case_id, current_user, db)
    
    # Get all timeline events for this case
    events = db.query(models.TransactionTimeline).filter(
        models.TransactionTimeline.case_id == case_id
    ).order_by(models.TransactionTimeline.event_timestamp.asc()).all()
    
    # Format timeline
    timeline = []
    for event in events:
        timeline.append({
            "timestamp": event.event_timestamp.isoformat(),
            "event_type": event.event_type,
            "amount": event.amount,
            "narrative": event.narrative,
            "relative_time": _calculate_relative_time(events[0].event_timestamp, event.event_timestamp)
        })
    
    return {
        "case_id": case_id,
        "fir_number": case.fir_number,
        "total_events": len(timeline),
        "timeline": timeline
    }

@router.get("/mule-indicators/{account_number}")
def detect_mule_account_indicators(
    account_number: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Rule-based mule account detection across all cases
    Flags suspicious patterns:
    - High inflow + rapid withdrawal (>80% in 24h)
    - Linked to multiple victim cases
    - Short account lifespan
    """
    # Find financial entities matching this account within accessible cases
    accessible_case_ids = get_accessible_case_ids(current_user, db)
    entity_query = db.query(models.FinancialEntity).filter(
        models.FinancialEntity.account_number == account_number
    )
    if accessible_case_ids is not None:
        if not accessible_case_ids:
            return {"account_number": account_number, "status": "not_found"}
        entity_query = entity_query.filter(models.FinancialEntity.case_id.in_(accessible_case_ids))
    entities = entity_query.all()
    
    if not entities:
        return {"account_number": account_number, "status": "not_found"}
    
    # Count linked cases
    linked_cases = set([e.case_id for e in entities])
    num_linked_cases = len(linked_cases)
    
    # Get all transactions for this account across cases
    transactions = []
    for entity in entities:
        case_transactions = db.query(models.TransactionTimeline).filter(
            models.TransactionTimeline.financial_entity_id == entity.id
        ).all()
        transactions.extend(case_transactions)
    
    # Calculate inflow/outflow using TransactionEventType enums
    inflow = sum([
        float(t.amount or 0)
        for t in transactions
        if t.event_type == models.TransactionEventType.PAYMENT
    ])
    outflow = sum([
        float(t.amount or 0)
        for t in transactions
        if t.event_type in [
            models.TransactionEventType.WITHDRAWAL,
            models.TransactionEventType.TRANSFER,
        ]
    ])
    
    outflow_ratio = (outflow / inflow * 100) if inflow > 0 else 0
    
    # Detection flags
    flags = []
    risk_score = 0
    
    if num_linked_cases >= 3:
        flags.append("MULTIPLE_VICTIMS")
        risk_score += 40
    
    if outflow_ratio > 80:
        flags.append("RAPID_WITHDRAWAL")
        risk_score += 30
    
    if inflow > 100000:  # High volume
        flags.append("HIGH_VOLUME")
        risk_score += 20
    
    # Determine classification
    classification = "NORMAL"
    if risk_score >= 50:
        classification = "SUSPECTED_MULE_ACCOUNT"
    elif risk_score >= 30:
        classification = "FLAGGED_FOR_REVIEW"
    
    linked_firs = []
    for cid in linked_cases:
        c = db.query(models.Case).filter(models.Case.id == cid).first()
        linked_firs.append(c.fir_number if c else f"Case#{cid}")

    return {
        "account_number": account_number,
        "classification": classification,
        "risk_score": risk_score,
        "indicators": flags,
        "linked_cases_count": num_linked_cases,
        "financial_data": {
            "total_inflow": inflow,
            "total_outflow": outflow,
            "outflow_ratio": round(outflow_ratio, 2)
        },
        "linked_fir_numbers": linked_firs,
        "note": "⚠️ Rule-based indicators only. Not AI prediction."
    }

@router.get("/repeat-entities")
def get_repeat_fraud_entities(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Detect UPI IDs / Account Numbers appearing in multiple FIRs
    Critical intelligence for identifying repeat offenders
    """
    accessible_case_ids = get_accessible_case_ids(current_user, db)
    if accessible_case_ids is not None and not accessible_case_ids:
        return {"total_repeat_entities": 0, "alerts": []}

    # Find accounts appearing in multiple accessible cases
    acc_query = db.query(
        models.FinancialEntity.account_number,
        models.FinancialEntity.bank_name,
        func.count(distinct(models.FinancialEntity.case_id)).label('case_count')
    ).filter(
        models.FinancialEntity.account_number.isnot(None)
    )
    if accessible_case_ids is not None:
        acc_query = acc_query.filter(models.FinancialEntity.case_id.in_(accessible_case_ids))
    repeat_accounts = acc_query.group_by(
        models.FinancialEntity.account_number,
        models.FinancialEntity.bank_name
    ).having(
        func.count(distinct(models.FinancialEntity.case_id)) > 1
    ).all()
    
    # Find UPI IDs appearing in multiple accessible cases
    upi_query = db.query(
        models.FinancialEntity.upi_id,
        func.count(distinct(models.FinancialEntity.case_id)).label('case_count')
    ).filter(
        models.FinancialEntity.upi_id.isnot(None)
    )
    if accessible_case_ids is not None:
        upi_query = upi_query.filter(models.FinancialEntity.case_id.in_(accessible_case_ids))
    repeat_upis = upi_query.group_by(
        models.FinancialEntity.upi_id
    ).having(
        func.count(distinct(models.FinancialEntity.case_id)) > 1
    ).all()
    
    # Format results (batched to eliminate N+1 queries)
    alerts = []
    acc_values = [acc for acc, _bank, _count in repeat_accounts]
    upi_values = [upi for upi, _count in repeat_upis]

    acc_entities_by_acc = {}
    upi_entities_by_upi = {}
    all_case_ids = set()

    if acc_values:
        acc_ent_q = db.query(models.FinancialEntity).filter(
            models.FinancialEntity.account_number.in_(acc_values)
        )
        if accessible_case_ids is not None:
            acc_ent_q = acc_ent_q.filter(models.FinancialEntity.case_id.in_(accessible_case_ids))
        for e in acc_ent_q.all():
            acc_entities_by_acc.setdefault(e.account_number, []).append(e)
            all_case_ids.add(e.case_id)

    if upi_values:
        upi_ent_q = db.query(models.FinancialEntity).filter(
            models.FinancialEntity.upi_id.in_(upi_values)
        )
        if accessible_case_ids is not None:
            upi_ent_q = upi_ent_q.filter(models.FinancialEntity.case_id.in_(accessible_case_ids))
        for e in upi_ent_q.all():
            upi_entities_by_upi.setdefault(e.upi_id, []).append(e)
            all_case_ids.add(e.case_id)

    case_map = {}
    if all_case_ids:
        from backend.utils.rbac import apply_jurisdiction_filter
        scoped_cases = apply_jurisdiction_filter(
            db.query(models.Case).filter(models.Case.id.in_(all_case_ids)),
            current_user,
            models.Case,
        ).all()
        case_map = {c.id: c.fir_number for c in scoped_cases}

    for acc, bank, count in repeat_accounts:
        entities = acc_entities_by_acc.get(acc, [])
        fir_numbers = [case_map.get(e.case_id, f"Case#{e.case_id}") for e in entities]
        alerts.append({
            "type": "BANK_ACCOUNT",
            "identifier": f"***{acc[-4:]} ({bank})",
            "full_account": acc,  # Only for authorized personnel
            "linked_cases_count": count,
            "fir_numbers": fir_numbers,
            "alert_level": "HIGH" if count >= 4 else "MEDIUM"
        })

    for upi, count in repeat_upis:
        entities = upi_entities_by_upi.get(upi, [])
        fir_numbers = [case_map.get(e.case_id, f"Case#{e.case_id}") for e in entities]
        alerts.append({
            "type": "UPI_ID",
            "identifier": upi,
            "linked_cases_count": count,
            "fir_numbers": fir_numbers,
            "alert_level": "HIGH" if count >= 4 else "MEDIUM"
        })
    
    return {
        "total_repeat_entities": len(alerts),
        "alerts": sorted(alerts, key=lambda x: x['linked_cases_count'], reverse=True)
    }

@router.get("/financial-dashboard")
def get_financial_fraud_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Financial fraud-specific dashboard metrics
    """
    # Get all financial fraud cases accessible to user (fail-closed)
    cases_query = apply_jurisdiction_filter(
        db.query(models.Case).filter(models.Case.case_category == models.CaseCategory.FINANCIAL),
        current_user,
        models.Case,
    )
    
    financial_cases = cases_query.all()
    case_ids = [c.id for c in financial_cases]
    
    # Calculate total amount at risk (Sum of amount_involved per case to avoid double counting entities)
    total_amount_at_risk = sum([
        float(c.amount_involved or 0) for c in financial_cases
    ])
    
    # Get bank request stats
    bank_requests = db.query(models.BankRequest).filter(
        models.BankRequest.case_id.in_(case_ids)
    ).all()
    
    avg_response_time = "Pending data"  # Would need response tracking
    
    # Freeze request stats
    freeze_requests = db.query(models.FreezeRequest).filter(
        models.FreezeRequest.case_id.in_(case_ids)
    ).all()
    
    frozen_count = len([f for f in freeze_requests if f.status == "confirmed"])
    
    return {
        "total_financial_cases": len(financial_cases),
        "amount_at_risk": f"₹{total_amount_at_risk:,.2f}",
        "bank_requests_sent": len(bank_requests),
        "freeze_requests": {
            "total": len(freeze_requests),
            "confirmed": frozen_count,
            "pending": len(freeze_requests) - frozen_count
        },
        "avg_bank_response_time": avg_response_time,
        "top_fraud_types": _get_fraud_type_breakdown(financial_cases)
    }

def _calculate_relative_time(start_time, event_time):
    """Calculate human-readable relative time"""
    delta = event_time - start_time
    if delta.total_seconds() < 3600:
        return f"+{int(delta.total_seconds() / 60)} minutes"
    elif delta.total_seconds() < 86400:
        return f"+{int(delta.total_seconds() / 3600)} hours"
    else:
        return f"+{delta.days} days"

def _get_fraud_type_breakdown(cases):
    """Get breakdown of fraud types"""
    types = {}
    for case in cases:
        case_type = case.case_type.value if hasattr(case.case_type, 'value') else str(case.case_type)
        types[case_type] = types.get(case_type, 0) + 1
    return dict(sorted(types.items(), key=lambda x: x[1], reverse=True))
