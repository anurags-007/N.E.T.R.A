"""Layer 2 forensics engine, real-dataset & Indian statutory compliance benchmarks."""
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.getcwd())
os.environ["DATABASE_URL"] = "sqlite:///./data/police_caf.db"

import PyPDF2
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import tools as tools_router
from backend.utils.cdr_parser import parse_cdr
from backend.utils.risk_engine import calculate_entity_risk


def _login(client: TestClient, username: str, password: str) -> dict:
    resp = client.post("/auth/token", data={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def main():
    # 1. DoT 22-Field CDR & Indian Cell-Tower Resolution
    dot_path = os.path.join("data", "test_data", "dot_22field_cdr_sample.csv")
    with open(dot_path, "rb") as f:
        dot_bytes = f.read()
    dot_res = parse_cdr(dot_bytes, "dot_22field_cdr_sample.csv")
    assert dot_res.get("schema_detected") == "indian_dot_22field", dot_res
    assert len(dot_res.get("imei_to_multiple_sims", {})) == 2, dot_res.get("imei_to_multiple_sims")
    assert len(dot_res.get("sim_to_multiple_imeis", {})) == 2, dot_res.get("sim_to_multiple_imeis")
    assert len(dot_res.get("resolved_towers", [])) == 4, dot_res.get("resolved_towers")
    print("[PASS] 2.1a DoT 22-Field CDR parsed: 2 IMEI swaps, 2 SIM swaps, 4 Indian towers resolved")

    with TestClient(app) as client:
        h_sec62 = _login(client, "si_sector62", "Sector62#2026")
        h_noida = _login(client, "si_noida_central", "CentralNoida#2026")

        # Indexed CDR search + station isolation
        srch_sec62 = client.get("/analysis/universal-search?query=9876543210", headers=h_sec62)
        assert srch_sec62.status_code == 200
        srch_data = srch_sec62.json()
        assert srch_data["summary"]["cdr_evidence_index"] >= 1
        assert client.get("/analysis/universal-search?query=9876543210", headers=h_noida).json()["summary"]["cdr_evidence_index"] == 0
        print(f"[PASS] 2.1b Universal search CDR Index match ({srch_data['summary']['cdr_evidence_index']} hit(s)) & jurisdiction scoping verified")

        # 2. PaySim Mule Analytics & Timezone-Safe Risk Engine
        conn = sqlite3.connect(os.path.join("data", "police_caf.db"))
        case_102_id = conn.execute("SELECT id FROM cases WHERE fir_number = 'FIR/GBN/2026/102'").fetchone()[0]
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
        fe_102_id = conn.execute("SELECT id FROM financial_entities WHERE case_id = ? LIMIT 1", (case_102_id,)).fetchone()[0]
        conn.close()
        assert mule_acc is not None
        acc_num = mule_acc[0]

        mule_resp = client.get(f"/analytics/mule-indicators/{acc_num}", headers=h_noida)
        assert mule_resp.status_code == 200
        mule = mule_resp.json()
        assert mule["financial_data"]["total_inflow"] > 0
        assert mule["financial_data"]["total_outflow"] > 0
        assert mule["classification"] == "SUSPECTED_MULE_ACCOUNT"

        comp = client.get(f"/analysis/comprehensive-investigation-data?identifier={acc_num}", headers=h_noida)
        assert comp.status_code == 200
        comp_risk = calculate_entity_risk(comp.json())
        assert comp_risk["level"] in ("CRITICAL", "HIGH"), comp_risk
        print(f"[PASS] 2.2 PaySim mule analytics ({acc_num}) inflow={mule['financial_data']['total_inflow']}, outflow={mule['financial_data']['total_outflow']}, risk={comp_risk['level']}")

        # 3. Offline GeoLite2 IP Lookup with Outbound HTTP Blocked
        orig_get = tools_router.requests.get
        def _forbid_network(*_args, **_kwargs):
            raise AssertionError("External network request attempted during offline GeoLite2 test")

        tools_router.requests.get = _forbid_network
        try:
            for ip in ("49.36.128.1", "8.8.8.8"):
                geo_resp = client.get(f"/tools/ip-lookup?query={ip}", headers=h_sec62)
                assert geo_resp.status_code == 200, geo_resp.text
                g = geo_resp.json()
                assert g["source"] == "offline_geolite2"
                assert g["asn"] is not None
                assert g["lat"] is not None and g["lon"] is not None
        finally:
            tools_router.requests.get = orig_get
        print("[PASS] 2.3 Offline GeoLite2 verified for 49.36.128.1 & 8.8.8.8 with outbound network blocked")

        # 4. BNSS 2023 & BSA 2023 Statutory Compliance (PDF generation & text extraction)
        case_101_id = client.get("/cases/", headers=h_sec62).json()[0]["id"]
        with tempfile.TemporaryDirectory() as tmpdir:
            from backend.utils.pdf_gen import generate_freeze_order_pdf, generate_request_pdf

            sec94_pdf = os.path.join(tmpdir, "qa_sec94.pdf")
            generate_request_pdf(
                request_data={"id": 999, "mobile_number": "9876543210", "request_type": "CDR", "reason": "Statutory QA"},
                case_data={"fir_number": "FIR/GBN/2026/101", "police_station": "Sector-62 Cyber PS"},
                officer_name="si_sector62",
                output_path=sec94_pdf,
            )
            sec94_text = "".join(p.extract_text() or "" for p in PyPDF2.PdfReader(sec94_pdf).pages)
            assert "Section 94" in sec94_text and "BNSS" in sec94_text
            assert "91 CrPC" not in sec94_text and "102 CrPC" not in sec94_text

            sec106_pdf = os.path.join(tmpdir, "qa_sec106.pdf")
            generate_freeze_order_pdf(
                freeze_data={
                    "id": 999,
                    "bank_name": "SBI",
                    "account_number": acc_num,
                    "urgency_level": "critical",
                    "justification": "Mule freeze QA",
                },
                case_data={"fir_number": "FIR/GBN/2026/102", "police_station": "Noida Central PS"},
                officer_name="si_noida_central",
                output_path=sec106_pdf,
            )
            sec106_text = "".join(p.extract_text() or "" for p in PyPDF2.PdfReader(sec106_pdf).pages)
            assert "Section 106" in sec106_text and "BNSS" in sec106_text
            assert "91 CrPC" not in sec106_text and "102 CrPC" not in sec106_text

        manifest = client.get(f"/files/case/{case_101_id}/bsa63-manifest", headers=h_sec62)
        assert manifest.status_code == 200
        mdata = manifest.json()
        assert "Section 63" in mdata["statute"] and "2023" in mdata["statute"]
        assert "part_a_declaration" in mdata and len(mdata["evidence_manifest"]) >= 2
        assert all(len(item["sha256_plaintext_hash"]) == 64 for item in mdata["evidence_manifest"])
        print("[PASS] 2.4 Section 94 BNSS PDF, Section 106 BNSS PDF (0 CrPC hits) & Section 63 BSA manifest verified")


if __name__ == "__main__":
    main()
