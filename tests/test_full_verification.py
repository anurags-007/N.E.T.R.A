"""Layer 1 comprehensive automated security, RBAC & forensic verification suite."""
from datetime import datetime, timezone
import hashlib
import io
import os
import zipfile

from cryptography.fernet import Fernet, MultiFernet
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import config, models
from backend.database import Base, get_db
from backend.main import app
from backend.utils import security
from backend.utils.audit import record_audit_log, verify_audit_chain
from backend.utils.limiter import limiter


@pytest.fixture()
def isolated_env(monkeypatch, tmp_path):
    """Fresh in-memory SQLite DB, temp upload/PDF dirs, and reset rate limiter per test."""
    limiter._storage.reset()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        bind=engine,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    from backend.routers import (
        evidence as evidence_router,
        files as files_router,
        freeze_requests as freeze_router,
        requests as req_router,
    )

    for mod, attr, folder in [
        (files_router, "UPLOAD_DIR", "uploads"),
        (evidence_router, "UPLOAD_DIR", "uploads"),
        (req_router, "REQUESTS_DIR", "requests"),
        (freeze_router, "FREEZE_PDF_DIR", "requests"),
    ]:
        target = str(tmp_path / folder)
        os.makedirs(target, exist_ok=True)
        monkeypatch.setattr(mod, attr, target)

    with TestClient(app) as client:
        yield client, TestingSession, tmp_path

    app.dependency_overrides.clear()
    limiter._storage.reset()


def _mk_user(db, username: str, role: models.UserRole, password: str, station=None, district=None):
    user = models.User(
        username=username,
        email=f"{username}@netra.gov.in",
        hashed_password=security.get_password_hash(password),
        role=role,
        rank=role.value.upper(),
        station_name=station,
        district_name=district,
        is_active=True,
        is_first_login=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _login_headers(client: TestClient, username: str, password: str) -> dict:
    resp = client.post("/auth/token", data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _jwt_headers(user: models.User) -> dict:
    tok = security.create_access_token(
        {
            "sub": user.username,
            "role": user.role.value,
            "rank": user.rank,
            "station": user.station_name,
            "district": user.district_name,
        }
    )
    return {"Authorization": f"Bearer {tok}"}


def _seed_demo_hierarchy(SessionLocal):
    db = SessionLocal()
    try:
        admin = _mk_user(db, "netra_admin", models.UserRole.ADMIN, "NetraAdmin#2026")
        dgp = _mk_user(db, "dgp_state", models.UserRole.DGP, "NetraDgp#2026")
        si_sec62 = _mk_user(
            db, "si_sector62", models.UserRole.SUB_INSPECTOR, "Sector62#2026",
            station="Sector-62 Cyber PS", district="Gautam Buddha Nagar",
        )
        sho_sec62 = _mk_user(
            db, "sho_sector62", models.UserRole.INSPECTOR, "ShoSec62#2026",
            station="Sector-62 Cyber PS", district="Gautam Buddha Nagar",
        )
        const_sec62 = _mk_user(
            db, "const_sector62", models.UserRole.CONSTABLE, "ConstSec62#2026",
            station="Sector-62 Cyber PS", district="Gautam Buddha Nagar",
        )
        si_noida = _mk_user(
            db, "si_noida_central", models.UserRole.SUB_INSPECTOR, "CentralNoida#2026",
            station="Noida Central PS", district="Gautam Buddha Nagar",
        )
        unassigned = _mk_user(
            db, "unassigned_officer", models.UserRole.SUB_INSPECTOR, "Unassigned#2026",
            station=None, district=None,
        )

        case_101 = models.Case(
            fir_number="FIR/GBN/2026/101",
            police_station="Sector-62 Cyber PS",
            district_name="Gautam Buddha Nagar",
            case_type=models.CaseType.IMPERSONATION,
            case_category=models.CaseCategory.NON_FINANCIAL,
            owner_id=si_sec62.id,
        )
        case_102 = models.Case(
            fir_number="FIR/GBN/2026/102",
            police_station="Noida Central PS",
            district_name="Gautam Buddha Nagar",
            case_type=models.CaseType.UPI_FRAUD,
            case_category=models.CaseCategory.FINANCIAL,
            amount_involved="1850000",
            owner_id=si_noida.id,
        )
        db.add_all([case_101, case_102])
        db.commit()
        db.refresh(case_101)
        db.refresh(case_102)

        fe_101 = models.FinancialEntity(
            case_id=case_101.id,
            entity_type=models.FinancialEntityType.BANK_ACCOUNT,
            bank_name="HDFC",
            account_number="111122223333",
            added_by_id=si_sec62.id,
        )
        fe_102 = models.FinancialEntity(
            case_id=case_102.id,
            entity_type=models.FinancialEntityType.BANK_ACCOUNT,
            bank_name="SBI",
            account_number="999988887777",
            added_by_id=si_noida.id,
        )
        db.add_all([fe_101, fe_102])
        db.commit()
        db.refresh(fe_101)
        db.refresh(fe_102)

        bank_102 = models.BankRequest(
            case_id=case_102.id,
            financial_entity_id=fe_102.id,
            bank_name="SBI",
            account_number="999988887777",
            request_type="KYC",
            reason="Mule trace",
        )
        npci_102 = models.NPCIRequest(
            case_id=case_102.id,
            financial_entity_id=fe_102.id,
            upi_id="mule@okaxis",
            request_type="FULL_HISTORY",
            reason="UPI trail",
        )
        frz_101 = models.FreezeRequest(
            case_id=case_101.id,
            financial_entity_id=fe_101.id,
            bank_name="HDFC",
            account_number="111122223333",
            urgency_level="high",
            justification="Section 106 hold",
        )
        frz_102 = models.FreezeRequest(
            case_id=case_102.id,
            financial_entity_id=fe_102.id,
            bank_name="SBI",
            account_number="999988887777",
            urgency_level="critical",
            justification="PaySim mule freeze",
        )
        db.add_all([bank_102, npci_102, frz_101, frz_102])
        db.commit()
        for obj in (bank_102, npci_102, frz_101, frz_102):
            db.refresh(obj)

        return {
            "admin": admin,
            "dgp": dgp,
            "si_sec62": si_sec62,
            "sho_sec62": sho_sec62,
            "const_sec62": const_sec62,
            "si_noida": si_noida,
            "unassigned": unassigned,
            "case_101": case_101,
            "case_102": case_102,
            "fe_101": fe_101,
            "fe_102": fe_102,
            "bank_102": bank_102,
            "npci_102": npci_102,
            "frz_101": frz_101,
            "frz_102": frz_102,
        }
    finally:
        db.close()


def test_auth_rate_limiting_and_jwt_jti_revocation(isolated_env):
    client, SessionLocal, _ = isolated_env
    _seed_demo_hierarchy(SessionLocal)

    # 1. Invalid password -> 401
    bad_login = client.post("/auth/token", data={"username": "si_sector62", "password": "WrongPassword#1"})
    assert bad_login.status_code == 401

    # 2. Exceeding 5/minute SlowAPI threshold triggers 429
    statuses = []
    for _ in range(7):
        r = client.post("/auth/token", data={"username": "si_sector62", "password": "WrongPassword#1"})
        statuses.append(r.status_code)
    assert 429 in statuses, f"Expected 429 Too Many Requests in {statuses}"

    # Reset limiter for clean logout revocation check
    limiter._storage.reset()
    headers = _login_headers(client, "si_sector62", "Sector62#2026")
    assert client.get("/cases/", headers=headers).status_code == 200

    # 3. Logout revokes active jti in TokenBlocklist
    logout_resp = client.post("/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get("/cases/", headers=headers).status_code == 401


def test_fail_closed_rbac_across_all_nine_routers(isolated_env):
    client, SessionLocal, _ = isolated_env
    data = _seed_demo_hierarchy(SessionLocal)

    h_sec62 = _jwt_headers(data["si_sec62"])
    h_sho62 = _jwt_headers(data["sho_sec62"])
    h_const62 = _jwt_headers(data["const_sec62"])
    h_noida = _jwt_headers(data["si_noida"])
    h_unassigned = _jwt_headers(data["unassigned"])
    h_dgp = _jwt_headers(data["dgp"])
    h_admin = _jwt_headers(data["admin"])

    c101 = data["case_101"].id
    c102 = data["case_102"].id

    # Seed evidence & telecom requests in 101 and 102 via respective station officers
    cdr_csv = b"A_PARTY,B_PARTY,IMEI,DATE,TIME,DURATION,CALL_TYPE,FIRST_CGI\n9876543210,9811122233,358240051111110,2026-01-01,10:00:00,45,OUT,404-10-1042-41201\n"
    up_101 = client.post(
        f"/files/upload/{c101}",
        headers=h_sec62,
        files={"file": ("sec62_cdr.csv", cdr_csv, "text/csv")},
        data={"file_type": "CDR_CSV"},
    )
    up_102 = client.post(
        f"/files/upload/{c102}",
        headers=h_noida,
        files={"file": ("noida_cdr.csv", cdr_csv, "text/csv")},
        data={"file_type": "CDR_CSV"},
    )
    assert up_101.status_code == 200 and up_102.status_code == 200
    ev101 = up_101.json()["id"]
    ev102 = up_102.json()["id"]

    req_102 = client.post(
        f"/requests/?case_id={c102}",
        headers=h_noida,
        json={"mobile_number": "9811122233", "request_type": "CDR", "reason": "Cross-station isolation fixture"},
    )
    assert req_102.status_code == 200
    req102_id = req_102.json()["id"]

    # Unassigned officer fails closed with 403
    assert client.get("/cases/", headers=h_unassigned).status_code == 403
    assert client.get(f"/cases/{c101}", headers=h_unassigned).status_code == 403
    assert client.get(f"/files/case/{c101}", headers=h_unassigned).status_code == 403
    assert client.get(f"/financial-entities/{c101}", headers=h_unassigned).status_code == 403
    assert client.get(f"/analytics/timeline/{c101}", headers=h_unassigned).status_code == 403

    # si_sector62 CAN access FIR/GBN/2026/101 (200)
    assert client.get(f"/cases/{c101}", headers=h_sec62).status_code == 200
    assert client.get(f"/files/case/{c101}", headers=h_sec62).status_code == 200
    assert client.get(f"/files/view/{ev101}", headers=h_sec62).status_code == 200
    assert client.get(f"/analysis/cdr/{ev101}", headers=h_sec62).status_code == 200

    # si_sector62 gets 403 Forbidden across all 9 routers on FIR/GBN/2026/102
    assert client.get(f"/cases/{c102}", headers=h_sec62).status_code == 403
    assert client.patch(f"/cases/{c102}/status", headers=h_sec62, json={"status": "closed"}).status_code == 403

    assert client.post(f"/requests/?case_id={c102}", headers=h_sec62, json={"mobile_number": "9811122233", "request_type": "CDR", "reason": "Probe"}).status_code == 403
    assert client.get(f"/requests/{req102_id}/download", headers=h_sec62).status_code == 403
    assert client.post(f"/requests/{req102_id}/upload", headers=h_sec62, files={"file": ("r.csv", b"a,b\n1,2\n", "text/csv")}).status_code == 403

    assert client.get(f"/files/case/{c102}", headers=h_sec62).status_code == 403
    assert client.post(f"/files/upload/{c102}", headers=h_sec62, files={"file": ("x.txt", b"x", "text/plain")}, data={"file_type": "DOC"}).status_code == 403
    assert client.get(f"/files/download/{ev102}", headers=h_sec62).status_code == 403
    assert client.get(f"/files/view/{ev102}", headers=h_sec62).status_code == 403
    assert client.get(f"/files/case/{c102}/bsa63-manifest", headers=h_sec62).status_code == 403

    assert client.post(f"/bank/requests/{c102}", headers=h_sec62, json={"financial_entity_id": data["fe_102"].id, "bank_name": "SBI", "account_number": "999988887777", "request_type": "KYC", "reason": "Probe"}).status_code == 403
    assert client.get(f"/bank/requests/{data['bank_102'].id}", headers=h_sec62).status_code == 403

    assert client.post(f"/npci/requests/{c102}", headers=h_sec62, json={"financial_entity_id": data["fe_102"].id, "upi_id": "mule@okaxis", "request_type": "FULL_HISTORY", "reason": "Probe"}).status_code == 403
    assert client.get(f"/npci/requests/{data['npci_102'].id}", headers=h_sec62).status_code == 403

    assert client.post(f"/freeze/request/{c102}", headers=h_sec62, json={"financial_entity_id": data["fe_102"].id, "bank_name": "SBI", "account_number": "999988887777", "urgency_level": "high", "justification": "Probe"}).status_code == 403
    assert client.get(f"/freeze/requests/{data['frz_102'].id}", headers=h_sec62).status_code == 403
    assert client.patch(f"/freeze/requests/{data['frz_102'].id}/status?status=confirmed", headers=h_sho62).status_code == 403

    assert client.get(f"/financial-entities/{c102}", headers=h_sec62).status_code == 403
    assert client.delete(f"/financial-entities/{data['fe_102'].id}", headers=h_sec62).status_code == 403

    assert client.get(f"/analytics/timeline/{c102}", headers=h_sec62).status_code == 403
    assert client.get("/analytics/mule-indicators/999988887777", headers=h_sec62).json().get("status") == "not_found"

    assert client.get(f"/analysis/cdr/{ev102}", headers=h_sec62).status_code == 403
    assert client.get("/analysis/universal-search?query=FIR/GBN/2026/102", headers=h_sec62).json()["count"] == 0

    # DGP and Admin see both cases
    assert {c["fir_number"] for c in client.get("/cases/", headers=h_dgp).json()} >= {"FIR/GBN/2026/101", "FIR/GBN/2026/102"}
    assert {c["fir_number"] for c in client.get("/cases/", headers=h_admin).json()} >= {"FIR/GBN/2026/101", "FIR/GBN/2026/102"}

    # Non-admin/non-SHO restrictions on /admin/logs & PATCH /freeze/requests/{id}/status
    assert client.get("/admin/logs", headers=h_const62).status_code == 403
    assert client.get("/admin/logs", headers=h_sec62).status_code == 403
    assert client.patch(f"/freeze/requests/{data['frz_101'].id}/status?status=sent", headers=h_sec62).status_code == 403
    assert client.patch(f"/freeze/requests/{data['frz_101'].id}/status?status=sent", headers=h_const62).status_code == 403


def test_upload_hardening_and_cryptographic_integrity(isolated_env):
    client, SessionLocal, _ = isolated_env
    data = _seed_demo_hierarchy(SessionLocal)
    h_sec62 = _jwt_headers(data["si_sec62"])
    c101 = data["case_101"].id

    # 1. Renamed PE executable rejected as .pdf and .csv
    for fname, ctype in [("fake.pdf", "application/pdf"), ("fake.csv", "text/csv")]:
        resp = client.post(
            f"/files/upload/{c101}",
            headers=h_sec62,
            files={"file": (fname, b"MZ\x90\x00\x03\x00\x00\x00PE-PAYLOAD", ctype)},
            data={"file_type": "OTHER"},
        )
        assert resp.status_code == 400

    # 2. Zip bomb > 100 entries rejected
    many_buf = io.BytesIO()
    with zipfile.ZipFile(many_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i in range(105):
            zf.writestr(f"e_{i}.txt", "x")
    assert client.post(
        f"/files/upload/{c101}",
        headers=h_sec62,
        files={"file": ("many.zip", many_buf.getvalue(), "application/zip")},
        data={"file_type": "OTHER"},
    ).status_code == 400

    # 3. Zip bomb > 50 MB uncompressed rejected (52 MB zeros compressed << 1 MB)
    bomb_buf = io.BytesIO()
    with zipfile.ZipFile(bomb_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("huge.txt", b"\x00" * (52 * 1024 * 1024))
    assert len(bomb_buf.getvalue()) < 1024 * 1024
    assert client.post(
        f"/files/upload/{c101}",
        headers=h_sec62,
        files={"file": ("bomb.zip", bomb_buf.getvalue(), "application/zip")},
        data={"file_type": "OTHER"},
    ).status_code == 400

    # 4. Path traversal rejected in mobile_number and uploaded filenames
    assert client.post(
        f"/requests/?case_id={c101}",
        headers=h_sec62,
        json={"mobile_number": "../../etc/passwd", "request_type": "CDR", "reason": "Test"},
    ).status_code == 422

    assert client.post(
        f"/files/upload/{c101}",
        headers=h_sec62,
        files={"file": ("../../etc/passwd.txt", b"safe-bytes", "text/plain")},
        data={"file_type": "OTHER"},
    ).status_code == 400

    # 5. Plaintext SHA-256 + MultiFernet ciphertext verification on disk
    raw_bytes = b"CLASSIFIED-EVIDENCE-PLAINTEXT-2026"
    expected_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    up_ok = client.post(
        f"/files/upload/{c101}",
        headers=h_sec62,
        files={"file": ("secret_report.txt", raw_bytes, "text/plain")},
        data={"file_type": "OTHER"},
    )
    assert up_ok.status_code == 200
    ev = up_ok.json()
    assert ev["file_hash"] == expected_sha256

    db = SessionLocal()
    try:
        ev_row = db.query(models.Evidence).filter(models.Evidence.id == ev["id"]).first()
        with open(ev_row.file_path, "rb") as disk_f:
            disk_bytes = disk_f.read()
        assert raw_bytes not in disk_bytes
        cipher = MultiFernet([Fernet(k) for k in config.ENCRYPTION_KEYS])
        assert cipher.decrypt(disk_bytes) == raw_bytes
    finally:
        db.close()


def test_audit_log_hash_chain_endpoint_and_tamper(isolated_env):
    client, SessionLocal, _ = isolated_env
    data = _seed_demo_hierarchy(SessionLocal)
    h_admin = _jwt_headers(data["admin"])

    db = SessionLocal()
    try:
        e1 = record_audit_log(db, data["si_sec62"].id, "LOGIN", "Officer login", commit=True)
        record_audit_log(db, data["si_sec62"].id, "VIEW_CASE", "Viewed 101", commit=True)
    finally:
        db.close()

    ok_resp = client.get("/admin/logs/verify", headers=h_admin)
    assert ok_resp.status_code == 200
    assert ok_resp.json()["valid"] is True
    assert ok_resp.json()["checked_entries"] == 2

    # Mutate historical details directly in DB session -> verify fails
    db = SessionLocal()
    try:
        row = db.query(models.AuditLog).filter(models.AuditLog.id == e1.id).first()
        row.details = "TAMPERED-DETAILS"
        db.commit()
        check = verify_audit_chain(db)
        assert check["valid"] is False
        assert check["broken_id"] == e1.id
    finally:
        db.close()

    tamper_resp = client.get("/admin/logs/verify", headers=h_admin)
    assert tamper_resp.status_code == 200
    assert tamper_resp.json()["valid"] is False
    assert tamper_resp.json()["broken_id"] == e1.id
