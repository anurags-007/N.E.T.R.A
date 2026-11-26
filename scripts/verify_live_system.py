"""Live end-to-end API verification against the populated data/police_caf.db."""
import os
import sqlite3
import sys

sys.path.insert(0, os.getcwd())
os.environ["DATABASE_URL"] = "sqlite:///./data/police_caf.db"

from fastapi.testclient import TestClient
from backend.main import app


def _login(client: TestClient, username: str, password: str) -> dict:
    resp = client.post(
        "/auth/token",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed for {username}: {resp.status_code} {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _login_any(client: TestClient, username: str, passwords: list[str]) -> dict:
    for pw in passwords:
        resp = client.post("/auth/token", data={"username": username, "password": pw})
        if resp.status_code == 200:
            return {"Authorization": f"Bearer {resp.json()['access_token']}"}
    raise AssertionError(f"Login failed for {username} across candidate passwords")


def main():
    with TestClient(app) as client:
        # 1. Cross-station RBAC verification
        h_sec62 = _login(client, "si_sector62", "Sector62#2026")
        h_admin = _login(client, "netra_admin", "NetraAdmin#2026")
        h_dgp = _login(client, "dgp_state", "NetraDgp#2026")

        cases_sec62 = client.get("/cases/", headers=h_sec62)
        assert cases_sec62.status_code == 200
        sec62_firs = {c["fir_number"]: c["id"] for c in cases_sec62.json()}
        assert "FIR/GBN/2026/101" in sec62_firs
        assert "FIR/GBN/2026/102" not in sec62_firs

        admin_cases = client.get("/cases/", headers=h_admin)
        dgp_cases = client.get("/cases/", headers=h_dgp)
        assert admin_cases.status_code == 200 and dgp_cases.status_code == 200
        all_firs = {c["fir_number"]: c["id"] for c in admin_cases.json()}
        assert "FIR/GBN/2026/101" in all_firs and "FIR/GBN/2026/102" in all_firs
        assert len(dgp_cases.json()) == len(admin_cases.json())

        case_101_id = all_firs["FIR/GBN/2026/101"]
        case_102_id = all_firs["FIR/GBN/2026/102"]
        assert client.get(f"/cases/{case_101_id}", headers=h_sec62).status_code == 200
        assert client.get(f"/cases/{case_102_id}", headers=h_sec62).status_code == 403
        print("[PASS] 1. Cross-station RBAC enforced (Sector-62 isolated; Admin/DGP statewide)")

        # 2. DoT 22-field CDR & Cell-Tower resolution
        ev_list = client.get(f"/files/case/{case_101_id}", headers=h_sec62).json()
        dot_ev = next(e for e in ev_list if e["original_filename"] == "dot_22field_cdr_sample.csv")
        cdr_resp = client.get(f"/analysis/cdr/{dot_ev['id']}", headers=h_sec62)
        assert cdr_resp.status_code == 200
        cdr_data = cdr_resp.json()
        assert cdr_data["schema_detected"] == "indian_dot_22field"
        assert len(cdr_data["imei_to_multiple_sims"]) == 2
        assert len(cdr_data["sim_to_multiple_imeis"]) == 2
        assert len(cdr_data["resolved_towers"]) == 4
        print("[PASS] 2. DoT 22-field CDR anomalies (2 IMEI, 2 SIM) & 4 Indian towers verified")

        # 3. Section 63 BSA 2023 Manifest & SAMEORIGIN PDF/evidence framing
        manifest_resp = client.get(f"/files/case/{case_101_id}/bsa63-manifest", headers=h_sec62)
        assert manifest_resp.status_code == 200
        manifest = manifest_resp.json()
        assert "Section 63" in manifest["statute"]
        assert manifest["total_evidence_items"] >= 2
        assert all(len(item["sha256_plaintext_hash"]) == 64 for item in manifest["evidence_manifest"])

        view_resp = client.get(f"/files/view/{dot_ev['id']}", headers=h_sec62)
        assert view_resp.status_code == 200
        assert view_resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        print("[PASS] 3. Section 63 BSA 2023 manifest & X-Frame-Options: SAMEORIGIN verified")

        # 4. PaySim Mule Indicators
        conn = sqlite3.connect("data/police_caf.db")
        mule_acc = conn.execute(
            """
            SELECT fe.account_number
            FROM financial_entities fe
            JOIN transaction_timeline tt ON tt.financial_entity_id = fe.id
            WHERE fe.case_id = ?
            GROUP BY fe.account_number
            HAVING SUM(CASE WHEN tt.event_type = 'PAYMENT' THEN CAST(tt.amount AS REAL) ELSE 0 END) > 100000
               AND SUM(CASE WHEN tt.event_type IN ('WITHDRAWAL', 'TRANSFER') THEN CAST(tt.amount AS REAL) ELSE 0 END) > 0
            LIMIT 1
            """,
            (case_102_id,),
        ).fetchone()
        conn.close()
        assert mule_acc is not None, "Expected a PaySim fraud mule account with inflow+withdrawal"

        h_noida = _login(client, "si_noida_central", "CentralNoida#2026")
        mule_resp = client.get(f"/analytics/mule-indicators/{mule_acc[0]}", headers=h_noida)
        assert mule_resp.status_code == 200
        mule = mule_resp.json()
        assert mule["financial_data"]["total_inflow"] > 0
        assert mule["financial_data"]["total_outflow"] > 0
        assert mule["classification"] == "SUSPECTED_MULE_ACCOUNT"
        print(f"[PASS] 4. PaySim mule indicator verified for {mule_acc[0]} ({mule['classification']})")

        # 5. Offline GeoLite2 & AuditLog hash-chain verification
        geo_resp = client.get("/tools/ip-lookup?query=49.36.128.1", headers=h_sec62)
        assert geo_resp.status_code == 200
        geo = geo_resp.json()
        assert geo["source"] == "offline_geolite2"
        assert "Jio" in (geo.get("isp") or "")

        verify_resp = client.get("/admin/logs/verify", headers=h_admin)
        assert verify_resp.status_code == 200
        verify_data = verify_resp.json()
        assert verify_data["valid"] is True
        assert verify_data["checked_entries"] >= 5
        print(f"[PASS] 5. Offline GeoLite2 ({geo['city']}, {geo['isp']}) & AuditLog chain ({verify_data['checked_entries']} entries) verified")

        # 6. Indexed CDR Universal Search + Jurisdiction Scoping + JWT Logout Revocation
        search_sec62 = client.get("/analysis/universal-search?query=9876543210", headers=h_sec62)
        assert search_sec62.status_code == 200
        s_data = search_sec62.json()
        assert s_data["summary"]["cdr_evidence_index"] >= 1
        assert any(m["source"] == "CDR Evidence Index" for m in s_data["matches"])

        search_noida = client.get("/analysis/universal-search?query=9876543210", headers=h_noida)
        assert search_noida.status_code == 200
        assert search_noida.json()["summary"]["cdr_evidence_index"] == 0

        h_temp = _login(client, "si_sector62", "Sector62#2026")
        assert client.post("/auth/logout", headers=h_temp).status_code == 200
        assert client.get("/auth/me", headers=h_temp).status_code == 401
        print("[PASS] 6. Indexed CDR universal search, RBAC scoping & JWT logout revocation verified")


if __name__ == "__main__":
    main()
