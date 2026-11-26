"""Phase 1, 2 & 3 security, RBAC, forensics, and logic regression tests for N.E.T.R.A."""
from datetime import datetime, timedelta, timezone
import os
from cryptography.fernet import Fernet, MultiFernet
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import models
from backend.database import Base, get_db
from backend.main import app
from backend.utils import security
from backend.utils.audit import record_audit_log, verify_audit_chain
from backend.utils.risk_engine import calculate_entity_risk
from backend.utils.validation import validate_password_strength


@pytest.fixture()
def client_and_db(monkeypatch, tmp_path):
    """Provide an isolated in-memory SQLite DB and TestClient per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Redirect disk upload/request directories to temp folders
    from backend.routers import files as files_router, requests as req_router

    monkeypatch.setattr(files_router, "UPLOAD_DIR", str(tmp_path / "uploads"))
    os.makedirs(files_router.UPLOAD_DIR, exist_ok=True)
    monkeypatch.setattr(req_router, "REQUESTS_DIR", str(tmp_path / "requests"))
    os.makedirs(req_router.REQUESTS_DIR, exist_ok=True)

    with TestClient(app) as client:
        yield client, TestingSessionLocal

    app.dependency_overrides.clear()


def _create_user(
    db,
    username: str,
    role: models.UserRole,
    station_name=None,
    district_name=None,
):
    user = models.User(
        username=username,
        email=f"{username}@netra.gov.in",
        hashed_password=security.get_password_hash("StrongPass123"),
        role=role,
        rank=role.value.upper(),
        station_name=station_name,
        district_name=district_name,
        is_active=True,
        is_first_login=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(user: models.User) -> dict:
    token = security.create_access_token(
        {
            "sub": user.username,
            "role": user.role.value,
            "rank": user.rank,
            "station": user.station_name,
            "district": user.district_name,
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _seed_two_stations(SessionLocal):
    db = SessionLocal()
    try:
        admin = _create_user(db, "admin_user", models.UserRole.ADMIN)
        si_a = _create_user(db, "si_alpha", models.UserRole.SUB_INSPECTOR, station_name="Kotwali")
        sho_a = _create_user(db, "sho_alpha", models.UserRole.INSPECTOR, station_name="Kotwali")
        const_a = _create_user(db, "const_alpha", models.UserRole.CONSTABLE, station_name="Kotwali")
        si_b = _create_user(db, "si_beta", models.UserRole.SUB_INSPECTOR, station_name="GomtiNagar")
        unassigned = _create_user(db, "unassigned_si", models.UserRole.SUB_INSPECTOR, station_name=None)

        case_a = models.Case(
            fir_number="FIR/2026/A01",
            police_station="Kotwali",
            case_type=models.CaseType.UPI_FRAUD,
            case_category=models.CaseCategory.FINANCIAL,
            owner_id=si_a.id,
        )
        case_b = models.Case(
            fir_number="FIR/2026/B01",
            police_station="GomtiNagar",
            case_type=models.CaseType.UPI_FRAUD,
            case_category=models.CaseCategory.FINANCIAL,
            owner_id=si_b.id,
        )
        db.add_all([case_a, case_b])
        db.commit()
        db.refresh(case_a)
        db.refresh(case_b)

        fe_b = models.FinancialEntity(
            case_id=case_b.id,
            entity_type=models.FinancialEntityType.BANK_ACCOUNT,
            bank_name="SBI",
            account_number="123456789012",
            added_by_id=si_b.id,
        )
        db.add(fe_b)
        db.commit()
        db.refresh(fe_b)

        freeze_b = models.FreezeRequest(
            case_id=case_b.id,
            financial_entity_id=fe_b.id,
            bank_name="SBI",
            account_number="123456789012",
            urgency_level="high",
            justification="Fraud mule account",
        )
        db.add(freeze_b)
        db.commit()
        db.refresh(freeze_b)

        return {
            "admin": admin,
            "si_a": si_a,
            "sho_a": sho_a,
            "const_a": const_a,
            "si_b": si_b,
            "unassigned": unassigned,
            "case_a": case_a,
            "case_b": case_b,
            "freeze_b": freeze_b,
        }
    finally:
        db.close()


def test_unauthenticated_upload_rejected(client_and_db):
    client, _ = client_and_db
    resp_legacy = client.post(
        "/evidence/upload",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert resp_legacy.status_code in (401, 404)

    resp_vault = client.post(
        "/files/upload/1",
        files={"file": ("test.txt", b"hello", "text/plain")},
        data={"file_type": "DOC"},
    )
    assert resp_vault.status_code == 401


def test_unassigned_jurisdiction_fails_closed(client_and_db):
    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)

    resp = client.get("/cases/", headers=_auth_headers(data["unassigned"]))
    assert resp.status_code == 403

    resp_req = client.get("/requests/", headers=_auth_headers(data["unassigned"]))
    assert resp_req.status_code == 403


def test_cross_station_isolation_enforced(client_and_db):
    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)
    headers_a = _auth_headers(data["si_a"])
    headers_sho_a = _auth_headers(data["sho_a"])
    headers_b = _auth_headers(data["si_b"])

    # Upload evidence into Station B case
    up = client.post(
        f"/files/upload/{data['case_b'].id}",
        headers=headers_b,
        files={"file": ("cdr.csv", b"Source,Destination,Duration\n9876543210,9999988888,10\n", "text/csv")},
        data={"file_type": "CDR_CSV"},
    )
    assert up.status_code == 200
    ev_id = up.json()["id"]

    # Station A cannot read Station B case, evidence, CDR analysis, or freeze status
    assert client.get(f"/cases/{data['case_b'].id}", headers=headers_a).status_code == 403
    assert client.get(f"/files/case/{data['case_b'].id}", headers=headers_a).status_code == 403
    assert client.get(f"/files/download/{ev_id}", headers=headers_a).status_code == 403
    assert client.get(f"/files/view/{ev_id}", headers=headers_a).status_code == 403
    assert client.get(f"/analysis/cdr/{ev_id}", headers=headers_a).status_code == 403
    assert client.patch(
        f"/freeze/requests/{data['freeze_b'].id}/status?status=confirmed",
        headers=headers_sho_a,
    ).status_code == 403

    # Universal search must not leak Station B FIR to Station A
    search = client.get("/analysis/universal-search?query=FIR/2026/B01", headers=headers_a)
    assert search.status_code == 200
    assert search.json()["count"] == 0


def test_admin_logs_forbidden_for_constable_and_si(client_and_db):
    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)

    assert client.get("/admin/logs", headers=_auth_headers(data["const_a"])).status_code == 403
    assert client.get("/admin/logs", headers=_auth_headers(data["si_a"])).status_code == 403
    assert client.get("/admin/logs", headers=_auth_headers(data["admin"])).status_code == 200


def test_mobile_number_path_traversal_rejected(client_and_db):
    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)

    resp = client.post(
        f"/requests/?case_id={data['case_a'].id}",
        headers=_auth_headers(data["si_a"]),
        json={
            "mobile_number": "../../etc/passwd",
            "request_type": "CDR",
            "reason": "Investigation",
        },
    )
    assert resp.status_code == 422


def test_view_evidence_rejects_query_token_without_header(client_and_db):
    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)
    headers_b = _auth_headers(data["si_b"])

    up = client.post(
        f"/files/upload/{data['case_b'].id}",
        headers=headers_b,
        files={"file": ("note.txt", b"evidence", "text/plain")},
        data={"file_type": "DOC"},
    )
    assert up.status_code == 200
    ev_id = up.json()["id"]

    raw_token = headers_b["Authorization"].split(" ", 1)[1]
    resp = client.get(f"/files/view/{ev_id}?token={raw_token}")
    assert resp.status_code == 401


def test_multifernet_rotation_decrypts_legacy_key():
    old_key = Fernet.generate_key()
    new_key = Fernet.generate_key()
    ciphertext = Fernet(old_key).encrypt(b"sensitive-evidence")

    rotated = MultiFernet([Fernet(new_key), Fernet(old_key)])
    assert rotated.decrypt(ciphertext) == b"sensitive-evidence"


def test_mule_indicators_uses_lowercase_transaction_event_types(client_and_db):
    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)
    db = SessionLocal()
    try:
        fe = models.FinancialEntity(
            case_id=data["case_a"].id,
            entity_type=models.FinancialEntityType.BANK_ACCOUNT,
            bank_name="HDFC Bank",
            account_number="998877665544",
            added_by_id=data["si_a"].id,
        )
        db.add(fe)
        db.commit()
        db.refresh(fe)

        now = datetime.now(timezone.utc)
        db.add_all([
            models.TransactionTimeline(
                case_id=data["case_a"].id,
                financial_entity_id=fe.id,
                event_type=models.TransactionEventType.PAYMENT,
                event_timestamp=now - timedelta(hours=2),
                amount="200000",
                narrative="Victim payment",
            ),
            models.TransactionTimeline(
                case_id=data["case_a"].id,
                financial_entity_id=fe.id,
                event_type=models.TransactionEventType.WITHDRAWAL,
                event_timestamp=now - timedelta(hours=1),
                amount="190000",
                narrative="Rapid ATM withdrawal",
            ),
        ])
        db.commit()
    finally:
        db.close()

    resp = client.get(
        "/analytics/mule-indicators/998877665544",
        headers=_auth_headers(data["si_a"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["financial_data"]["total_inflow"] == 200000.0
    assert body["financial_data"]["total_outflow"] == 190000.0
    assert "RAPID_WITHDRAWAL" in body["indicators"]
    assert body["classification"] == "SUSPECTED_MULE_ACCOUNT"


def test_risk_engine_handles_timezone_aware_and_naive_timestamps():
    aware_ts = datetime.now(timezone.utc).isoformat()
    naive_ts = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    for ts in (aware_ts, naive_ts):
        result = calculate_entity_risk({
            "summary_stats": {"total_cases": 2, "total_transaction_amount": 150000.0},
            "cases": [{"case_category": "financial", "police_station": "Kotwali"}],
            "transaction_timeline": [{"event_timestamp": ts}],
        })
        assert result["score"] > 0
        assert any("RECENTLY ACTIVE" in t for t in result["tags"])


def test_request_upload_preserves_request_file_path(client_and_db):
    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)
    headers_a = _auth_headers(data["si_a"])

    create_resp = client.post(
        f"/requests/?case_id={data['case_a'].id}",
        headers=headers_a,
        json={
            "mobile_number": "9876543210",
            "request_type": "CDR",
            "reason": "Section 94 BNSS requisition",
        },
    )
    assert create_resp.status_code == 200
    req_data = create_resp.json()
    original_req_path = req_data["request_file_path"]
    assert original_req_path

    upload_resp = client.post(
        f"/requests/{req_data['id']}/upload",
        headers=headers_a,
        files={"file": ("cdr_reply.csv", b"col1,col2\n1,2\n", "text/csv")},
    )
    assert upload_resp.status_code == 200
    result_path = upload_resp.json()["result_file_path"]

    db = SessionLocal()
    try:
        refreshed = db.query(models.TelecomRequest).filter(models.TelecomRequest.id == req_data["id"]).first()
        assert refreshed.request_file_path == original_req_path
        assert refreshed.result_file_path == result_path
        assert refreshed.request_file_path != refreshed.result_file_path
    finally:
        db.close()


def test_audit_log_hash_chain_and_tamper_detection(client_and_db):
    _, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)
    db = SessionLocal()
    try:
        e1 = record_audit_log(db, data["si_a"].id, "LOGIN", "First login", commit=True)
        e2 = record_audit_log(db, data["si_a"].id, "VIEW_CASE", "Viewed case A", commit=True)
        assert e2.prev_hash == e1.entry_hash
        assert verify_audit_chain(db)["valid"] is True

        # Tamper with e1 details directly in DB
        e1.details = "Altered log"
        db.commit()
        check = verify_audit_chain(db)
        assert check["valid"] is False
        assert check["broken_id"] == e1.id
    finally:
        db.close()


def test_bsa63_manifest_and_password_policy(client_and_db):
    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)
    headers_a = _auth_headers(data["si_a"])

    up = client.post(
        f"/files/upload/{data['case_a'].id}",
        headers=headers_a,
        files={"file": ("evidence.txt", b"raw-bytes", "text/plain")},
        data={"file_type": "DOC"},
    )
    assert up.status_code == 200

    manifest_resp = client.get(
        f"/files/case/{data['case_a'].id}/bsa63-manifest",
        headers=headers_a,
    )
    assert manifest_resp.status_code == 200
    manifest = manifest_resp.json()
    assert "Section 63" in manifest["statute"]
    assert manifest["total_evidence_items"] == 1

    assert validate_password_strength("1234")[0] is False
    assert validate_password_strength("StrongPass#2026")[0] is True


def test_logout_revokes_jwt_jti(client_and_db):
    client, SessionLocal = client_and_db
    _seed_two_stations(SessionLocal)

    tok_resp = client.post(
        "/auth/token",
        data={"username": "si_alpha", "password": "StrongPass123"},
    )
    assert tok_resp.status_code == 200
    token = tok_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/auth/me", headers=headers).status_code == 200
    out = client.post("/auth/logout", headers=headers)
    assert out.status_code == 200
    # Same JWT must now be rejected because its jti is in token_blocklist
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_magic_byte_and_zip_bomb_rejection(client_and_db):
    import io
    import zipfile

    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)
    headers_a = _auth_headers(data["si_a"])

    # Renamed Windows PE executable (.exe disguised as .pdf)
    bad_pdf = client.post(
        f"/files/upload/{data['case_a'].id}",
        headers=headers_a,
        files={"file": ("fake_caf.pdf", b"MZ\x90\x00not-a-pdf", "application/pdf")},
        data={"file_type": "CAF_PDF"},
    )
    assert bad_pdf.status_code == 400

    # Zip archive exceeding >100 files limit
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(105):
            zf.writestr(f"f_{i}.txt", "ok")
    bad_zip = client.post(
        f"/files/upload/{data['case_a'].id}",
        headers=headers_a,
        files={"file": ("many_files.zip", buf.getvalue(), "application/zip")},
        data={"file_type": "OTHER"},
    )
    assert bad_zip.status_code == 400


def test_cdr_index_universal_search_scoping(client_and_db):
    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)
    headers_a = _auth_headers(data["si_a"])
    headers_b = _auth_headers(data["si_b"])

    cdr_csv = (
        b"A_PARTY,B_PARTY,IMEI,DATE,TIME,DURATION,CALL_TYPE,FIRST_CGI\n"
        b"9876543210,9811122233,358240051111110,2026-01-01,10:00:00,42,OUT,404-10-1042-41201\n"
    )
    up = client.post(
        f"/files/upload/{data['case_a'].id}",
        headers=headers_a,
        files={"file": ("cdr_sample.csv", cdr_csv, "text/csv")},
        data={"file_type": "CDR_CSV"},
    )
    assert up.status_code == 200

    res_a = client.get("/analysis/universal-search?query=9876543210", headers=headers_a)
    assert res_a.status_code == 200
    body_a = res_a.json()
    assert body_a["summary"]["cdr_evidence_index"] >= 1
    assert any(m["source"] == "CDR Evidence Index" and m["matched_value"] == "9876543210" for m in body_a["matches"])

    # Station B must not see Station A's indexed CDR entries
    res_b = client.get("/analysis/universal-search?query=9876543210", headers=headers_b)
    assert res_b.status_code == 200
    assert res_b.json()["count"] == 0


def test_network_graph_max_nodes_and_truncated(client_and_db):
    client, SessionLocal = client_and_db
    data = _seed_two_stations(SessionLocal)
    db = SessionLocal()
    try:
        for i in range(6):
            db.add(
                models.TelecomRequest(
                    case_id=data["case_a"].id,
                    mobile_number=f"999000110{i}",
                    request_type="CDR",
                    reason="Graph limit test",
                )
            )
        db.commit()
    finally:
        db.close()

    headers_a = _auth_headers(data["si_a"])
    resp = client.get("/analysis/network-graph?identifier=9990001100&max_nodes=3", headers=headers_a)
    assert resp.status_code == 200
    graph = resp.json()
    assert len(graph["nodes"]) <= 3
    assert graph["truncated"] is True
