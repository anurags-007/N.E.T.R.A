from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session, joinedload
from collections import defaultdict
from backend.database import get_db
from backend import models, schemas
from backend.routers.auth import get_current_active_user
from backend.utils import cdr_parser, risk_engine
from backend.utils.cdr_indexer import index_cdr_bytes
from backend.utils.rbac import authorize_case_access, get_accessible_case_ids
from backend.routers.files import cipher_suite
import os
import re
import io

router = APIRouter(
    prefix="/analysis",
    tags=["analysis"]
)

@router.get("/cdr/{evidence_id}")
def analyze_cdr(
    evidence_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Fetch Evidence & verify case jurisdiction
    evidence = db.query(models.Evidence).filter(models.Evidence.id == evidence_id).first()
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    authorize_case_access(evidence.case_id, current_user, db)
    
    # Decrypt File
    try:
        with open(evidence.file_path, "rb") as f:
            encrypted_data = f.read()
        decrypted_data = cipher_suite.decrypt(encrypted_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decrypt evidence file")

    # Parse
    analysis_result = cdr_parser.parse_cdr(decrypted_data, evidence.original_filename)
    
    if "error" in analysis_result:
        raise HTTPException(status_code=400, detail=analysis_result["error"])

    if (evidence.original_filename or "").lower().endswith((".csv", ".xlsx", ".xls")):
        try:
            index_cdr_bytes(db, evidence.case_id, evidence.id, decrypted_data, evidence.original_filename)
        except Exception:
            pass
        
    return analysis_result

@router.get("/universal-search")
def universal_search(
    query: str,
    search_type: str = "auto",  # auto, mobile, upi, account, name, fir, email
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Universal search across all cases, requests, and financial entities.
    Supports multiple search types:
    - Mobile numbers
    - UPI IDs
    - Bank account numbers
    - Names (suspect/victim)
    - FIR numbers
    - Email addresses
    """
    results = []
    query_lower = query.lower().strip()
    accessible_case_ids = get_accessible_case_ids(current_user, db)
    if accessible_case_ids is not None and not accessible_case_ids:
        return {
            "query": query,
            "search_type": search_type,
            "matches": [],
            "count": 0,
            "summary": {
                "telecom_requests": 0,
                "financial_entities": 0,
                "case_records": 0,
                "transaction_timeline": 0,
                "evidence_files": 0,
            },
        }
    
    # Auto-detect search type if not specified
    if search_type == "auto":
        if query.replace("+", "").replace("-", "").isdigit() and len(query.replace("+", "").replace("-", "")) >= 10:
            search_type = "mobile"
        elif "@" in query and "." in query:
            if query.count("@") == 1:
                search_type = "email" if "." in query.split("@")[1] else "upi"
        elif "/" in query or query.upper().startswith("FIR"):
            search_type = "fir"
        elif query.isdigit() and len(query) >= 9:
            search_type = "account"
        else:
            search_type = "name"
    
    # 1. Search in Telecom Requests (Mobile Numbers)
    if search_type in ["mobile", "auto"]:
        req_q = db.query(models.TelecomRequest).filter(
            models.TelecomRequest.mobile_number.ilike(f"%{query}%")
        )
        if accessible_case_ids is not None:
            req_q = req_q.filter(models.TelecomRequest.case_id.in_(accessible_case_ids))
        requests = req_q.all()
        
        for req in requests:
            results.append({
                "source": "Telecom Request",
                "case_id": req.case_id,
                "fir_number": req.case.fir_number,
                "match_type": "Mobile Number",
                "matched_value": req.mobile_number,
                "case_type": req.case.case_type.value if req.case.case_type else "N/A",
                "status": req.case.status,
                "created_at": req.created_at.isoformat() if req.created_at else None
            })
    
    # 2. Search in Financial Entities (UPI IDs, Bank Accounts)
    if search_type in ["upi", "account", "auto"]:
        fin_q = db.query(models.FinancialEntity).filter(
            (models.FinancialEntity.upi_id.ilike(f"%{query}%")) |
            (models.FinancialEntity.account_number.ilike(f"%{query}%")) |
            (models.FinancialEntity.account_holder_name.ilike(f"%{query}%")) |
            (models.FinancialEntity.bank_name.ilike(f"%{query}%"))
        )
        if accessible_case_ids is not None:
            fin_q = fin_q.filter(models.FinancialEntity.case_id.in_(accessible_case_ids))
        financial_entities = fin_q.all()
        
        for entity in financial_entities:
            match_field = "Unknown"
            matched_value = query
            
            if entity.upi_id and query_lower in entity.upi_id.lower():
                match_field = "UPI ID"
                matched_value = entity.upi_id
            elif entity.account_number and query_lower in entity.account_number.lower():
                match_field = "Bank Account"
                matched_value = f"{entity.bank_name} - {entity.account_number}"
            elif entity.account_holder_name and query_lower in entity.account_holder_name.lower():
                match_field = "Account Holder Name"
                matched_value = entity.account_holder_name
            
            results.append({
                "source": "Financial Entity",
                "case_id": entity.case_id,
                "fir_number": entity.case.fir_number if entity.case else "N/A",
                "match_type": match_field,
                "matched_value": matched_value,
                "entity_type": entity.entity_type.value if entity.entity_type else "N/A",
                "transaction_amount": entity.transaction_amount,
                "case_type": entity.case.case_type.value if entity.case and entity.case.case_type else "N/A",
                "status": entity.case.status if entity.case else "N/A",
                "created_at": entity.created_at.isoformat() if entity.created_at else None
            })
    
    # 3. Search in Cases (FIR Number, Description)
    if search_type in ["fir", "name", "auto"]:
        case_q = db.query(models.Case).filter(
            (models.Case.fir_number.ilike(f"%{query}%")) |
            (models.Case.description.ilike(f"%{query}%"))
        )
        if accessible_case_ids is not None:
            case_q = case_q.filter(models.Case.id.in_(accessible_case_ids))
        cases = case_q.all()
        
        for case in cases:
            match_field = "FIR Number" if query_lower in case.fir_number.lower() else "Case Description"
            
            results.append({
                "source": "Case Record",
                "case_id": case.id,
                "fir_number": case.fir_number,
                "match_type": match_field,
                "matched_value": case.fir_number,
                "case_type": case.case_type.value if case.case_type else "N/A",
                "case_category": case.case_category.value if case.case_category else "N/A",
                "status": case.status,
                "police_station": case.police_station,
                "created_at": case.created_at.isoformat() if case.created_at else None
            })
    
    # 4. Search in Transaction Timeline (narrative text search)
    if search_type in ["name", "auto"]:
        txn_q = db.query(models.TransactionTimeline).filter(
            models.TransactionTimeline.narrative.ilike(f"%{query}%")
        )
        if accessible_case_ids is not None:
            txn_q = txn_q.filter(models.TransactionTimeline.case_id.in_(accessible_case_ids))
        transactions = txn_q.all()
        
        for txn in transactions:
            results.append({
                "source": "Transaction Timeline",
                "case_id": txn.case_id,
                "fir_number": txn.case.fir_number if txn.case else "N/A",
                "match_type": "Mentioned in Timeline",
                "matched_value": txn.narrative[:100] + "..." if len(txn.narrative) > 100 else txn.narrative,
                "event_type": txn.event_type.value if txn.event_type else "N/A",
                "amount": txn.amount,
                "case_type": txn.case.case_type.value if txn.case and txn.case.case_type else "N/A",
                "created_at": txn.event_timestamp.isoformat() if txn.event_timestamp else None
            })
    
    # 5. Search in Evidence Files (CAF, CDR metadata)
    ev_q = db.query(models.Evidence).filter(
        (models.Evidence.original_filename.ilike(f"%{query}%")) |
        (models.Evidence.file_type.ilike(f"%{query}%"))
    )
    if accessible_case_ids is not None:
        ev_q = ev_q.filter(models.Evidence.case_id.in_(accessible_case_ids))
    evidence_files = ev_q.all()
    
    for evidence in evidence_files:
        results.append({
            "source": "Evidence File",
            "case_id": evidence.case_id,
            "fir_number": evidence.case.fir_number if evidence.case else "N/A",
            "match_type": "Evidence Document",
            "matched_value": evidence.original_filename,
            "file_type": evidence.file_type,
            "file_id": evidence.id,
            "uploaded_at": evidence.uploaded_at.isoformat() if evidence.uploaded_at else None,
            "case_type": evidence.case.case_type.value if evidence.case and evidence.case.case_type else "N/A",
            "status": evidence.case.status if evidence.case else "N/A",
            "verification_status": evidence.verification_status
        })
    
    # 6. Search in CDR Evidence Index (MSISDN / IMEI across parsed CDRs)
    cdr_q = (
        db.query(models.CdrIndexEntry)
        .options(
            joinedload(models.CdrIndexEntry.case),
            joinedload(models.CdrIndexEntry.evidence),
        )
        .filter(
            (models.CdrIndexEntry.msisdn.ilike(f"%{query}%")) |
            (models.CdrIndexEntry.imei.ilike(f"%{query}%"))
        )
    )
    if accessible_case_ids is not None:
        cdr_q = cdr_q.filter(models.CdrIndexEntry.case_id.in_(accessible_case_ids))

    for entry in cdr_q.all():
        matched_val = (
            entry.msisdn
            if (entry.msisdn and query_lower in entry.msisdn.lower())
            else (entry.imei or entry.msisdn)
        )
        results.append({
            "source": "CDR Evidence Index",
            "case_id": entry.case_id,
            "fir_number": entry.case.fir_number if entry.case else "N/A",
            "match_type": f"CDR ({entry.call_count} calls)",
            "matched_value": matched_val,
            "msisdn": entry.msisdn,
            "imei": entry.imei,
            "call_count": entry.call_count,
            "file_id": entry.evidence_id,
            "file_name": entry.evidence.original_filename if entry.evidence else "N/A",
            "case_type": entry.case.case_type.value if entry.case and entry.case.case_type else "N/A",
            "status": entry.case.status if entry.case else "N/A",
        })

    # Remove duplicates based on case_id, source, match_type, and matched_value
    unique_results = []
    seen = set()
    for result in results:
        key = (result["case_id"], result["source"], result["match_type"], result.get("matched_value"))
        if key not in seen:
            seen.add(key)
            unique_results.append(result)
    
    return {
        "query": query,
        "search_type": search_type,
        "matches": unique_results,
        "count": len(unique_results),
        "summary": {
            "telecom_requests": sum(1 for r in unique_results if r["source"] == "Telecom Request"),
            "financial_entities": sum(1 for r in unique_results if r["source"] == "Financial Entity"),
            "case_records": sum(1 for r in unique_results if r["source"] == "Case Record"),
            "transaction_timeline": sum(1 for r in unique_results if r["source"] == "Transaction Timeline"),
            "evidence_files": sum(1 for r in unique_results if r["source"] == "Evidence File"),
            "cdr_evidence_index": sum(1 for r in unique_results if r["source"] == "CDR Evidence Index")
        }
    }


@router.get("/comprehensive-investigation-data")
def get_comprehensive_investigation_data(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    ONE-CLICK INVESTIGATION DATA!
    Get ALL investigation-related data for any identifier (mobile, UPI, account, FIR).
    Returns: Cases, Telecom Requests, Financial Entities, Evidence Files, Timeline - EVERYTHING!
    Perfect for investigators who need complete picture in one click.
    """
    
    identifier_lower = identifier.lower().strip()
    investigation_data = {
        "identifier": identifier,
        "cases": [],
        "telecom_requests": [],
        "financial_entities": [],
        "evidence_files": [],
        "transaction_timeline": [],
        "summary_stats": {},
        "risk_profile": {}
    }
    
    case_ids = set()
    accessible_case_ids = get_accessible_case_ids(current_user, db)
    
    # 1. Collect all Case IDs from various matches (scoped to user's jurisdiction)
    # Match by Case Text
    text_q = db.query(models.Case).filter(
        (models.Case.fir_number.ilike(f"%{identifier}%")) |
        (models.Case.description.ilike(f"%{identifier}%"))
    )
    if accessible_case_ids is not None:
        text_q = text_q.filter(models.Case.id.in_(accessible_case_ids)) if accessible_case_ids else text_q.filter(False)
    for c in text_q.all(): case_ids.add(c.id)
    
    # Match by Telecom
    tel_q = db.query(models.TelecomRequest).filter(
        models.TelecomRequest.mobile_number.ilike(f"%{identifier}%")
    )
    if accessible_case_ids is not None:
        tel_q = tel_q.filter(models.TelecomRequest.case_id.in_(accessible_case_ids)) if accessible_case_ids else tel_q.filter(False)
    telecom_requests = tel_q.all()
    for req in telecom_requests:
        case_ids.add(req.case_id)
        investigation_data["telecom_requests"].append({
            "id": req.id,
            "case_id": req.case_id,
            "fir_number": req.case.fir_number if req.case else "N/A",
            "mobile_number": req.mobile_number,
            "request_type": req.request_type,
            "status": req.status.value if req.status else "N/A",
            "reason": req.reason,
            "created_at": req.created_at.isoformat() if req.created_at else None
        })
    
    # Match by Financial
    fin_q = db.query(models.FinancialEntity).filter(
        (models.FinancialEntity.upi_id.ilike(f"%{identifier}%")) |
        (models.FinancialEntity.account_number.ilike(f"%{identifier}%")) |
        (models.FinancialEntity.account_holder_name.ilike(f"%{identifier}%"))
    )
    if accessible_case_ids is not None:
        fin_q = fin_q.filter(models.FinancialEntity.case_id.in_(accessible_case_ids)) if accessible_case_ids else fin_q.filter(False)
    financial_entities = fin_q.all()
    for entity in financial_entities:
        case_ids.add(entity.case_id)
        investigation_data["financial_entities"].append({
            "id": entity.id,
            "case_id": entity.case_id,
            "fir_number": entity.case.fir_number if entity.case else "N/A",
            "entity_type": entity.entity_type.value if entity.entity_type else "N/A",
            "bank_name": entity.bank_name,
            "account_number": entity.account_number,
            "ifsc_code": entity.ifsc_code,
            "upi_id": entity.upi_id,
            "account_holder_name": entity.account_holder_name,
            "transaction_id": entity.transaction_id,
            "transaction_amount": entity.transaction_amount,
            "status": entity.verification_status,
            "created_at": entity.created_at.isoformat() if entity.created_at else None
        })

    # 2. Now fetch ALL Case details for all collected IDs
    if case_ids:
        all_cases = db.query(models.Case).filter(models.Case.id.in_(case_ids)).all()
        for case in all_cases:
            investigation_data["cases"].append({
                "id": case.id,
                "fir_number": case.fir_number,
                "police_station": case.police_station,
                "case_type": case.case_type.value if case.case_type else "N/A",
                "case_category": case.case_category.value if case.case_category else "N/A",
                "status": case.status,
                "amount_involved": case.amount_involved,
                "description": case.description,
                "created_at": case.created_at.isoformat() if case.created_at else None
            })
    
    # 4. Get ALL Evidence Files for discovered cases
    if case_ids:
        evidence_files = db.query(models.Evidence).filter(
            models.Evidence.case_id.in_(case_ids)
        ).all()
        
        for evidence in evidence_files:
            investigation_data["evidence_files"].append({
                "id": evidence.id,
                "case_id": evidence.case_id,
                "fir_number": evidence.case.fir_number if evidence.case else "N/A",
                "file_type": evidence.file_type,
                "original_filename": evidence.original_filename,
                "uploaded_at": evidence.uploaded_at.isoformat() if evidence.uploaded_at else None,
                "verification_status": evidence.verification_status,
                "file_hash": evidence.file_hash
            })
        
        # 5. Get Transaction Timeline for discovered cases
        timeline = db.query(models.TransactionTimeline).filter(
            models.TransactionTimeline.case_id.in_(case_ids)
        ).order_by(models.TransactionTimeline.event_timestamp.desc()).all()
        
        for txn in timeline:
            investigation_data["transaction_timeline"].append({
                "id": txn.id,
                "case_id": txn.case_id,
                "fir_number": txn.case.fir_number if txn.case else "N/A",
                "event_type": txn.event_type.value if txn.event_type else "N/A",
                "event_timestamp": txn.event_timestamp.isoformat() if txn.event_timestamp else None,
                "narrative": txn.narrative,
                "amount": txn.amount,
                "source_identifier": txn.source_identifier,
                "destination_identifier": txn.destination_identifier
            })
    
    # Summary Statistics
    investigation_data["summary_stats"] = {
        "total_cases": len(case_ids),
        "total_telecom_requests": len(investigation_data["telecom_requests"]),
        "total_financial_entities": len(investigation_data["financial_entities"]),
        "total_evidence_files": len(investigation_data["evidence_files"]),
        "total_timeline_events": len(investigation_data["transaction_timeline"]),
        "total_transaction_amount": sum(
            float(case.get("amount_involved") or 0) 
            for case in investigation_data["cases"]
        ),
        "case_ids": list(case_ids),
        "fir_numbers": list(set(
            case["fir_number"] for case in investigation_data["cases"]
        ))
    }

    # Delegate unified risk scoring to shared risk_engine (prevents score drift & handles tz-naive/aware dates)
    investigation_data["risk_profile"] = risk_engine.calculate_entity_risk(investigation_data)

    return investigation_data


@router.get("/network-graph")
def get_network_graph(
    identifier: str = None,
    max_nodes: int = 250,
    max_edges: int = 500,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    GENERATE INTELLIGENCE NETWORK MAP!
    Builds a JSON of Nodes and Edges connecting Cases, Mobiles, and Accounts.
    """
    max_nodes = max(1, min(max_nodes, 250))
    max_edges = max(1, min(max_edges, 1000))
    nodes = []
    edges = []
    node_ids = set()
    edge_keys = set()
    truncated = False
    edges_truncated = False

    def add_node(id, label, type, color="#97C2FC", size=20):
        nonlocal truncated
        if id in node_ids:
            return True
        if len(nodes) >= max_nodes:
            truncated = True
            return False
        nodes.append({
            "id": id,
            "label": str(label), # Ensure string
            "group": type,
            "color": color,
            "size": size,
            "font": {"size": 14, "color": "#343a40", "face": "Inter"}
        })
        node_ids.add(id)
        return True

    def add_edge(from_node, to_node, label="", color="#848484"):
        nonlocal edges_truncated
        key = tuple(sorted([str(from_node), str(to_node)]))
        if from_node in node_ids and to_node in node_ids and key not in edge_keys and from_node != to_node:
            if len(edges) >= max_edges:
                edges_truncated = True
                return False
            edges.append({
                "from": from_node,
                "to": to_node,
                "label": label,
                "color": {"color": color},
                "arrows": "to"
            })
            edge_keys.add(key)
            return True
        return False

    # Initial search to find related cases (scoped to user's jurisdiction)
    found_case_ids = set()
    accessible_case_ids = get_accessible_case_ids(current_user, db)
    
    if identifier:
        if accessible_case_ids is not None and not accessible_case_ids:
            add_node(f"SEARCH_{identifier}", identifier, "search", "#6c757d", 30)
            return {"nodes": nodes, "edges": edges, "truncated": truncated, "edges_truncated": edges_truncated}

        # 1. Search Telecom Requests
        req_q = db.query(models.TelecomRequest).filter(models.TelecomRequest.mobile_number.ilike(f"%{identifier}%"))
        if accessible_case_ids is not None:
            req_q = req_q.filter(models.TelecomRequest.case_id.in_(accessible_case_ids))
        for r in req_q.all():
            found_case_ids.add(r.case_id)
            
        # 2. Search Financial Entities
        fin_q = db.query(models.FinancialEntity).filter(
            (models.FinancialEntity.upi_id.ilike(f"%{identifier}%")) |
            (models.FinancialEntity.account_number.ilike(f"%{identifier}%"))
        )
        if accessible_case_ids is not None:
            fin_q = fin_q.filter(models.FinancialEntity.case_id.in_(accessible_case_ids))
        for f in fin_q.all():
            found_case_ids.add(f.case_id)
            
        # 3. Search Cases directly
        case_q = db.query(models.Case).filter(models.Case.fir_number.ilike(f"%{identifier}%"))
        if accessible_case_ids is not None:
            case_q = case_q.filter(models.Case.id.in_(accessible_case_ids))
        for c in case_q.all():
            found_case_ids.add(c.id)

    # If no identifier or no matches, return empty or default view
    if not found_case_ids:
        # Just return the searched node itself if nothing found
        if identifier: 
            add_node(f"SEARCH_{identifier}", identifier, "search", "#6c757d", 30)
        return {"nodes": nodes, "edges": edges, "truncated": truncated, "edges_truncated": edges_truncated}

    # --- EXPANSION LOGIC (batched to eliminate N+1 queries) ---
    all_cases = db.query(models.Case).filter(models.Case.id.in_(found_case_ids)).all()
    all_reqs = db.query(models.TelecomRequest).filter(models.TelecomRequest.case_id.in_(found_case_ids)).all()
    all_fins = db.query(models.FinancialEntity).filter(models.FinancialEntity.case_id.in_(found_case_ids)).all()

    reqs_by_case = defaultdict(list)
    for r in all_reqs:
        reqs_by_case[r.case_id].append(r)

    fins_by_case = defaultdict(list)
    for f in all_fins:
        fins_by_case[f.case_id].append(f)

    for case in all_cases:
        cid = f"CASE_{case.id}"
        if not add_node(cid, f"FIR: {case.fir_number}", "case", "#4CAF50", 40):
            break

        # Add Mobiles linked to this Case
        for r in reqs_by_case.get(case.id, []):
            mid = f"MOB_{r.mobile_number}"
            color = "#FF9800" # Orange for mobile
            if identifier and str(identifier) in r.mobile_number:
                color = "#d32f2f" # Red if it matches search

            if not add_node(mid, r.mobile_number, "mobile", color):
                break
            add_edge(cid, mid, "suspect")

        if truncated:
            break

        # Add Financials linked to this Case
        for f in fins_by_case.get(case.id, []):
            val = f.upi_id or f.account_number
            fid = f"FIN_{val}"
            color = "#2196F3" # Blue for finance
            if identifier and (str(identifier) in (f.upi_id or "") or str(identifier) in (f.account_number or "")):
                color = "#d32f2f" # Red if matches search

            if not add_node(fid, val, "financial", color):
                break
            add_edge(cid, fid, "money_trail")

        if truncated:
            break

    return {
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated,
        "edges_truncated": edges_truncated
    }


# Legacy endpoint for backward compatibility
@router.get("/correlate/{mobile_number}")
def multi_case_search(
    mobile_number: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Legacy mobile number search - redirects to universal search"""
    return universal_search(mobile_number, "mobile", db, current_user)


@router.post("/file-search")
async def file_based_search(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Upload and analyze files (PDF, Excel, CSV) to extract identifiers
    and perform batch intelligence search.
    """
    try:
        content = await file.read()
        file_extension = (file.filename or "").split('.')[-1].lower()

        def _extract_identifiers() -> list[str]:
            extracted = []
            if file_extension in ['xlsx', 'xls', 'csv']:
                from backend.utils.cdr_parser import _read_tabular_rows
                headers, rows = _read_tabular_rows(content, file.filename or f"upload.{file_extension}")
                for h in headers:
                    if h:
                        extracted.append(str(h).strip())
                for row in rows:
                    for value in row.values():
                        if value is not None and str(value).strip():
                            extracted.append(str(value).strip())
            elif file_extension == 'pdf':
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
                text = "".join((page.extract_text() or "") for page in pdf_reader.pages)
                extracted = text.split()
            else:
                raise ValueError("UNSUPPORTED_FORMAT")
            return extracted

        try:
            identifiers = await run_in_threadpool(_extract_identifiers)
        except ValueError as ve:
            if str(ve) == "UNSUPPORTED_FORMAT":
                raise HTTPException(status_code=400, detail="Unsupported file format. Use Excel, CSV, or PDF")
            raise
        except Exception as e:
            label = "PDF" if file_extension == "pdf" else "Excel/CSV"
            raise HTTPException(status_code=400, detail=f"Error processing {label}: {str(e)}")
        
        # Extract phone numbers, UPI IDs, account numbers using regex
        extracted_data = {
            'mobile_numbers': set(),
            'upi_ids': set(),
            'account_numbers': set(),
            'other_identifiers': set()
        }
        
        for identifier in identifiers:
            # Mobile number pattern (Indian)
            if re.match(r'^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$', identifier):
                extracted_data['mobile_numbers'].add(identifier)
            # UPI ID pattern
            elif '@' in identifier and '.' not in identifier.split('@')[0]:
                extracted_data['upi_ids'].add(identifier)
            # Account number pattern (9-18 digits)
            elif re.match(r'^\d{9,18}$', identifier):
                extracted_data['account_numbers'].add(identifier)
            # Other identifiers (names, FIR numbers, etc.)
            elif len(identifier) > 3:
                extracted_data['other_identifiers'].add(identifier)
        
        # Perform batch search
        all_results = []
        summary_stats = {
            'total_identifiers': sum(len(v) for v in extracted_data.values()),
            'mobile_numbers_found': len(extracted_data['mobile_numbers']),
            'upi_ids_found': len(extracted_data['upi_ids']),
            'account_numbers_found': len(extracted_data['account_numbers']),
            'total_matches': 0
        }
        
        # Search each type
        for mobile in extracted_data['mobile_numbers']:
            try:
                result = universal_search(mobile, "mobile", db, current_user)
                if result['count'] > 0:
                    for match in result['matches']:
                        match['searched_identifier'] = mobile
                        all_results.append(match)
            except:
                pass
        
        for upi in extracted_data['upi_ids']:
            try:
                result = universal_search(upi, "upi", db, current_user)
                if result['count'] > 0:
                    for match in result['matches']:
                        match['searched_identifier'] = upi
                        all_results.append(match)
            except:
                pass
        
        for account in extracted_data['account_numbers']:
            try:
                result = universal_search(account, "account", db, current_user)
                if result['count'] > 0:
                    for match in result['matches']:
                        match['searched_identifier'] = account
                        all_results.append(match)
            except:
                pass
        
        # Remove duplicates
        unique_results = []
        seen = set()
        for result in all_results:
            key = (result['case_id'], result['source'], result.get('searched_identifier'))
            if key not in seen:
                seen.add(key)
                unique_results.append(result)
        
        summary_stats['total_matches'] = len(unique_results)
        
        return {
            'filename': file.filename,
            'file_type': file_extension,
            'extracted_data': {
                'mobile_numbers': list(extracted_data['mobile_numbers']),
                'upi_ids': list(extracted_data['upi_ids']),
                'account_numbers': list(extracted_data['account_numbers'])
            },
            'summary': summary_stats,
            'matches': unique_results,
            'count': len(unique_results)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")

