# N.E.T.R.A. — Complete Security, Logic & Forensics Remediation Report

**System:** N.E.T.R.A. (*Network Evidence Tracking & Record Analysis*)  
**Scope:** Full remediation across Phase 1 (`F-01`–`F-09`, `F-14`), Phase 2 (`F-10`–`F-13`), and Phase 3 (`F-15`–`F-22`).

---

## 1. Executive Summary (Before vs. After)

| Dimension | Before Overhaul | After Overhaul |
| :--- | :--- | :--- |
| **Access Control & RBAC** | Null `station_name` leaked state-wide FIRs; single-ID routes, `analysis.py`, `requests.py`, `files.py` (`/case/{id}`, `/view/{id}`), and `admin.py` lacked jurisdiction/role checks. | Centralized fail-closed RBAC (`backend/utils/rbac.py`) enforced across all case, request, evidence, financial, analytics, and audit endpoints. Missing jurisdiction attributes return `403`. |
| **File Upload & XSS** | Unauthenticated `/evidence/upload` saved raw files; SheetJS/Mammoth/ZIP/table `innerHTML` lacked sanitization; CSP blocked `cdnjs` DOMPurify. | `evidence.router` unmounted from `main.py` and locked down; self-hosted `purify.min.js` + `safeHTML`/`textContent` DOM rendering; `frame-src`/`media-src blob:` enabled. |
| **Secrets, Auth & Rate Limits** | Single static `Fernet` key; `.env` in git; SlowAPI not attached to `app`; `?token=` leaked JWT in URLs; `mobile_number` allowed `../` traversal. | `MultiFernet` key-rotation support (`ENCRYPTION_KEYS`), production default-secret rejection, SlowAPI wired in `main.py`, `Authorization` header Blob previews, Pydantic mobile + containment checks. |
| **Core Logic & Forensics** | Mule detection compared lowercase enums to uppercase strings (`0` inflow/outflow); CrPC 91/102 notices; mutable `AuditLog`; `/upload` overwrote `request_file_path`. | Enum-accurate mule detection, UTC-safe `risk_engine.py`, BNSS 2023 (`Sec 94`/`106`), BSA 2023 (`Sec 63`) hash-manifest export, hash-chained `AuditLog`, separate `result_file_path`. |
| **Concurrency, PWA & Hygiene** | SQLite without WAL; blocking sync calls on `async def`; fake Lucknow/Jio fallback in `tools.py`; broken `sw.js` paths; CORS default `:8000`; `0` tests. | SQLite WAL + `busy_timeout`, `run_in_threadpool` offload, `503` on IP lookup failure, fixed `sw.js` (`/frontend/...`), CORS `:8001`, 10+ char password policy, 12 automated tests. |

---

## 2. Complete Fix Matrix (`F-01` to `F-22`)

| ID | Severity | Status | Files Modified / Created | Exact Fix Implemented |
| :--- | :--- | :--- | :--- | :--- |
| **F-01** | `P0-Critical` | Fixed | `backend/main.py`, `backend/routers/evidence.py` | Unmounted `evidence.router` from `main.py`; locked `evidence.py` behind `get_current_active_user`, `authorize_case_access`, `ALLOWED_EXTENSIONS`, `MAX_FILE_SIZE_BYTES`, `sanitize_filename()`, and `MultiFernet` encryption. |
| **F-02** | `P0-Critical` | Fixed | `backend/utils/rbac.py`, `backend/schemas.py`, `backend/routers/auth.py`, `cases.py`, `bank_requests.py`, `npci_requests.py`, `freeze_requests.py`, `financial_analytics.py`, `frontend/admin.html`, `frontend/js/admin.js`, `frontend/js/api.js` | Built `apply_jurisdiction_filter` failing closed (`403`) whenever a scoped role lacks its jurisdiction field; added hierarchy fields to `UserCreate` and `register_user` + Admin UI. |
| **F-03** | `P0-Critical` | Fixed | `backend/utils/rbac.py`, `cases.py`, `requests.py`, `files.py`, `bank_requests.py`, `npci_requests.py`, `freeze_requests.py`, `financial_entities.py`, `financial_analytics.py`, `analysis.py` | Enforced `authorize_case_access` and `get_accessible_case_ids` across all single-ID, case-scoped, search, graph, and CDR endpoints; restricted `PATCH /freeze/requests/{id}/status` to `INSPECTOR` (`sho`) and above. |
| **F-04** | `P0-Critical` | Fixed | `backend/routers/admin.py` | Restricted `GET /admin/logs` to `ADMIN`, `INSPECTOR`, `SP`, and `DGP` with station/district scoping; restricted `GET /admin/logs/verify` to `ADMIN` and `DGP`. |
| **F-05** | `P0-Critical` | Fixed | `frontend/js/lib/purify.min.js`, `frontend/*.html`, `frontend/js/case_detail.js`, `requests.js`, `tools.js`, `admin.js`, `backend/middleware/security.py` | Self-hosted DOMPurify locally; sanitized SheetJS/Mammoth HTML with `safeHTML`; replaced raw `innerHTML` data interpolation with `textContent` / `escapeHtml` and event listeners. |
| **F-06** | `P0-Critical` | Fixed *(+ Manual Action)* | `backend/config.py`, `backend/routers/files.py`, `.gitignore` | Replaced `Fernet` with `MultiFernet` using `ENCRYPTION_KEYS`; rejected placeholder/dev keys in production. *Manual:* purge `.env` from git history and rotate live keys. |
| **F-07** | `P1-High` | Fixed | `backend/utils/limiter.py`, `backend/main.py`, `backend/routers/auth.py` | Moved `limiter` into shared module and registered `app.state.limiter` + `RateLimitExceeded` handler in `main.py`. |
| **F-08** | `P1-High` | Fixed | `backend/routers/files.py`, `frontend/js/case_detail.js`, `frontend/js/requests.js`, `frontend/js/api.js` | Removed `?token=` query-string auth from `/files/view/{evidence_id}`; switched evidence and request PDF previews/downloads to authenticated `fetch` (`Authorization: Bearer`) -> `Blob` URLs with `URL.revokeObjectURL` cleanup. |
| **F-09** | `P1-High` | Fixed | `backend/schemas.py`, `backend/routers/requests.py` | Added `validate_mobile_number` validators to `RequestCreate`/`RequestBatchCreate`; validated upload extensions/size, sanitized filenames, and enforced `REQUESTS_DIR` path containment. |
| **F-10** | `P1-High` | Fixed | `backend/routers/financial_analytics.py` | Replaced `"PAYMENT"` / `["WITHDRAWAL", "TRANSFER"]` string comparisons with `TransactionEventType.PAYMENT`, `.WITHDRAWAL`, and `.TRANSFER`. |
| **F-11** | `P1-High` | Fixed | `backend/routers/financial_analytics.py`, `backend/utils/risk_engine.py` | Guarded `.first()` case lookups before `.fir_number` access; normalized `risk_engine.py` timestamps to UTC (`timezone.utc`) before age calculation. |
| **F-12** | `P1-High` | Fixed | `backend/models.py`, `backend/main.py`, `backend/utils/audit.py`, `backend/utils/pdf_gen.py`, `backend/routers/files.py`, `freeze_requests.py`, `auth.py`, `bank_requests.py`, `npci_requests.py`, `financial_entities.py`, `admin.py`, `frontend/requests.html`, `frontend/js/requests.js` | Replaced repealed Section 91/102 CrPC citations with **Section 94 & Section 106 BNSS, 2023**; added **Section 63 BSA, 2023** manifest export (`/files/case/{id}/bsa63-manifest`); implemented SHA-256 hash-chained `AuditLog`. |
| **F-13** | `P1-High` | Fixed | `backend/models.py`, `backend/schemas.py`, `backend/routers/requests.py` | Added `result_file_path` to `TelecomRequest`; `POST /requests/{id}/upload` now writes to `result_file_path` without overwriting `request_file_path`. |
| **F-14** | `P1-High` | Fixed | `backend/middleware/security.py`, `frontend/js/case_detail.js`, `frontend/js/requests.js` | Updated `X-Frame-Options` to `SAMEORIGIN`, CSP `frame-ancestors 'self'`, `frame-src 'self' blob:`, `media-src 'self' blob:`, and switched PDF previews to authenticated Blob URLs. |
| **F-15** | `P2-Medium` | Fixed | `backend/utils/validation.py`, `backend/utils/security.py`, `requirements.txt`, `frontend/admin.html` | Enforced >=10-char mixed-character passwords (`upper`, `lower`, `digit`, `symbol`); cleaned duplicate imports and UTC timestamps in `security.py`; aligned `requirements.txt` (`passlib`, `PyPDF2`, `Pillow`, `pytest`, `httpx`; removed unused `bleach`). |
| **F-16** | `P2-Medium` | Fixed | `backend/utils/pdf_gen.py`, `backend/routers/tools.py` | Added `simpleSplit` line wrapping + page-break checks in PDF generation; added `timeout=5` and `raise_for_status()` on `ip-api.com` requests. |
| **F-17** | `P2-Medium` | Fixed | `backend/routers/tools.py` | Removed hardcoded Lucknow/Jio mock fallback; `ip_lookup` re-raises `HTTPException` and returns `503 Service Unavailable` when external geolocation is unreachable. |
| **F-18** | `P2-Medium` | Fixed *(+ DB Migration)* | `backend/database.py` | Enabled SQLite `PRAGMA journal_mode=WAL`, `busy_timeout=5000`, and `foreign_keys=ON` on connect. *Note:* recreate/migrate `data/police_caf.db` for new `TelecomRequest`/`AuditLog` columns; PostgreSQL recommended before multi-node rollout. |
| **F-19** | `P2-Medium` | Fixed | `backend/routers/files.py`, `requests.py`, `tools.py`, `analysis.py`, `evidence.py` | Offloaded blocking `pandas`, `PyPDF2`, `Fernet`, and file I/O work via `starlette.concurrency.run_in_threadpool`. |
| **F-20** | `P2-Medium` | Fixed | `backend/config.py`, `frontend/sw.js`, `frontend/js/app.js` | Updated `ALLOWED_ORIGINS` default to port `8001`; fixed `sw.js` cache paths to `/frontend/...` and excluded API/authenticated requests; aligned `app.js` New Case button visibility with `cases.py` RBAC. |
| **F-21** | `P2-Medium` | Fixed | `backend/routers/analysis.py`, `backend/schemas.py`, `requirements.txt` | Removed duplicate `APIRouter` definition in `analysis.py` and duplicate `is_first_login` field in `UserResponse`. |
| **F-22** | `P3-Low` | Fixed | `backend/routers/files.py` | Sanitized `evidence.original_filename` stored on upload and escaped filenames in `Content-Disposition` headers. |

---

## 3. Forensic & Legal Compliance Summary

- **BNSS 2023 Alignment:**
  - Telecom requisition PDFs (`backend/utils/pdf_gen.py`), frontend templates (`frontend/requests.html`, `frontend/js/requests.js`) now issue lawful production notices under **Section 94 BNSS, 2023** (replacing Section 91 CrPC).
  - Account freeze models and workflows (`backend/models.py`, `backend/routers/freeze_requests.py`) align with **Section 106 BNSS, 2023** (replacing Section 102 CrPC).
- **BSA 2023 Section 63 Hash Manifest:**
  - `generate_bsa_63_manifest()` (`backend/utils/pdf_gen.py`) and `GET /files/case/{case_id}/bsa63-manifest` (`backend/routers/files.py`) export structured case evidence records containing `evidence_id`, `original_filename`, `sha256_plaintext_hash` (computed on raw plaintext bytes before Fernet encryption), `uploaded_at_utc`, `uploaded_by`, and `verification_status`.
- **Tamper-Evident Hash-Chained Audit Log:**
  - `backend/utils/audit.py` (`record_audit_log`, `verify_audit_chain`) chains every `AuditLog` record to the preceding record via `prev_hash` and `entry_hash = SHA256(prev_hash|user_id|action|details|timestamp_iso)`, verifiable via `GET /admin/logs/verify` (`Admin` / `DGP` only).
- **Document Traceability:**
  - `TelecomRequest.request_file_path` retains the original requisition PDF while `TelecomRequest.result_file_path` stores uploaded TSP responses separately.

---

## 4. Verification & Test Coverage

### Static Verification (`git grep`)
- Repealed `Section 91 CrPC` / `Section 102 CrPC` / `CRPC_91` / `CRPC_102` references in `backend/` and `frontend/`: **0 matches**.
- Uppercase `"PAYMENT"` / `"WITHDRAWAL"` / `"TRANSFER"` comparisons in `backend/routers/financial_analytics.py`: **0 matches** (enum members used).
- Hardcoded `"Demo Result"` / `"Lucknow"` / `"Demo Data"` fallback in `backend/routers/tools.py`: **0 matches**.
- Query-string `?token=` auth in `frontend/` and `backend/`: **0 matches**.
- `cdnjs.*purify` CDN references in `frontend/`: **0 matches**.
- Duplicate `router = APIRouter` in `analysis.py` and duplicate `is_first_login` in `UserResponse`: **0 duplicates**.

### Automated Test Suite (`tests/test_security_rbac.py`)
12 tests implemented covering Phases 1–3:
1. `test_unauthenticated_upload_rejected` (`F-01`)
2. `test_unassigned_jurisdiction_fails_closed` (`F-02`)
3. `test_cross_station_isolation_enforced` (`F-03`)
4. `test_admin_logs_forbidden_for_constable_and_si` (`F-04`)
5. `test_mobile_number_path_traversal_rejected` (`F-09`)
6. `test_view_evidence_rejects_query_token_without_header` (`F-08`)
7. `test_multifernet_rotation_decrypts_legacy_key` (`F-06`)
8. `test_mule_indicators_uses_lowercase_transaction_event_types` (`F-10`)
9. `test_risk_engine_handles_timezone_aware_and_naive_timestamps` (`F-11`)
10. `test_request_upload_preserves_request_file_path` (`F-13`)
11. `test_audit_log_hash_chain_and_tamper_detection` (`F-12`)
12. `test_bsa63_manifest_and_password_policy` (`F-12`, `F-15`)

> **Execution Note:** Python/`pytest` was not installed in the audit workspace environment, so live `pytest` execution must be run locally after installing Python.

---

## 5. Remaining Local / Deployment Steps

Run these PowerShell commands from `c:\Users\anura\OneDrive\Desktop\New folder`:

```powershell
# 1. Install Python 3.12+ (if not installed) and create virtual environment
winget install -e --id Python.Python.3.12
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Run the full security, RBAC, and forensics test suite
pytest tests/test_security_rbac.py -v

# 3. Reset/recreate SQLite DB so new AuditLog (prev_hash/entry_hash) & TelecomRequest (result_file_path) columns exist
# (Back up data/police_caf.db first if keeping existing data, then re-seed)
Copy-Item data\police_caf.db data\police_caf.db.bak
Remove-Item data\police_caf.db
python -m backend.seed_demo

# 4. Generate fresh production secrets for .env (do NOT commit .env)
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEYS=' + Fernet.generate_key().decode())"

# 5. Purge leaked .env from git history before pushing to GitHub
git filter-repo --path .env --invert-paths

# 6. Start the portal locally
uvicorn backend.main:app --port 8001 --reload
```
