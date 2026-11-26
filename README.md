# N.E.T.R.A. — Network Evidence Tracking & Record Analysis

**N.E.T.R.A.** is a hardened cybercrime investigation, telecom requisitioning, and financial fraud intelligence platform built for Indian law enforcement operations. It combines hierarchical police RBAC, `MultiFernet`-encrypted evidence storage, Indian statutory workflows (**BNSS 2023** & **BSA 2023**), offline IP/cell-tower geolocation, and real-time fraud correlation.

---

## Architecture Overview

```mermaid
flowchart LR
    UI["Frontend Portal (Bootstrap 5 + Vanilla JS + Self-Hosted DOMPurify + PWA)"]
    MW["FastAPI Security Middleware (CSP, SAMEORIGIN, RequestLogging, SlowAPI, CORS)"]
    API["13 FastAPI Routers / 50 Endpoints"]
    RBAC["Fail-Closed 11-Tier Hierarchy RBAC (Constable -> DGP / Admin)"]
    VAULT["MultiFernet Encrypted Evidence Vault + Plaintext SHA-256"]
    AUDIT["Tamper-Evident SHA-256 Hash-Chained AuditLog"]
    ENG["Intelligence Engines (DoT 22-Field CDR, Risk Engine, Mule Detector, Offline GeoLite2)"]
    DB["PostgreSQL 16 (Production) / SQLite WAL (Local Dev)"]

    UI --> MW
    MW --> API
    API --> RBAC
    API --> VAULT
    API --> AUDIT
    API --> ENG
    API --> DB
```

---

## Security & Indian Cyber-Forensics Architecture

- **Fail-Closed 11-Tier Police Hierarchy RBAC (`backend/utils/rbac.py`):**
  - Scoped roles (`constable`, `head_constable`, `si`, `sho` -> station; `dy_sp` -> sub-division; `sp` -> district; `dig` -> range; `igp` -> zone) fail closed (`403 Forbidden`) whenever a user's jurisdiction field is unassigned or a request crosses jurisdiction boundaries. Only `dgp` and `admin` hold state-wide visibility.
- **`MultiFernet` Evidence Vault & Integrity (`backend/routers/files.py`):**
  - Computes raw-plaintext **SHA-256** prior to `MultiFernet` encryption (`ENCRYPTION_KEYS` supports seamless key rotation), re-verifies hashes on every download/view, and logs integrity mismatches.
- **Tamper-Evident Hash-Chained `AuditLog` (`backend/utils/audit.py`):**
  - Every security/investigative action appends an entry linked via `prev_hash` -> `entry_hash = SHA256(prev_hash|user_id|action|details|timestamp_utc)`, verifiable via `GET /admin/logs/verify`.
- **Hardened Web Security & Auth (`backend/middleware/security.py`, `backend/routers/auth.py`, `backend/utils/validation.py`):**
  - Strict `'self'` CSP with **air-gapped self-hosted frontend assets** (`frontend/vendor/`: Bootstrap 5, Bootstrap Icons, Chart.js, Vis-Network, `DOMPurify`, `jsPDF` — zero external CDN dependencies), `X-Frame-Options: SAMEORIGIN` + `blob:` previews (zero JWTs in URL query strings), server-side JWT `jti` revocation (`TokenBlocklist` + `POST /auth/logout`), magic-byte & anti-zip-bomb upload validation (`<= 100` files / `50 MB` uncompressed), production Swagger/OpenAPI schema lockdown (`ENVIRONMENT=production`), SlowAPI rate limiting on `/auth/token`, and ≥10-character mixed-complexity password enforcement.
- **Indian Statutory Alignment (`BNSS 2023` & `BSA 2023`) & Indexed Forensics:**
  - Official PDF requisitions cite **Section 94 BNSS, 2023** (`backend/utils/pdf_gen.py`), **Section 106 BNSS, 2023** freeze orders are exposed in `case_detail.html` (`POST /freeze/request/{case_id}`), and `Export Sec 63 BSA Certificate` downloads **Section 63(4)(c) BSA, 2023** manifests with Part A source-device declarations (`GET /files/case/{case_id}/bsa63-manifest`).
  - Uploaded CSV/Excel CDRs auto-index MSISDN/IMEI pairs into `CdrIndexEntry` for jurisdiction-scoped `/analysis/universal-search`, and `/analysis/network-graph` uses batched queries capped at `max_nodes=250` with a `truncated` indicator.
  - Admin Console (`admin.html`) provides one-click `Verify Audit Chain` (`GET /admin/logs/verify`) with DIG (`range_name`) / IGP (`zone_name`) officer provisioning, while the Admin sidebar link is hidden for non-supervisor roles (`si`, `constable`, `dy_sp`, `dig`, `igp`).

---

## Real-Dataset Benchmark Results

Verified against real public datasets in `scripts/ingest_real_datasets.py` (full metrics in [docs/DATASET_INTEGRATION_REPORT.md](docs/DATASET_INTEGRATION_REPORT.md)):

| Module | Dataset Used | Verified Benchmark |
| :--- | :--- | :--- |
| **Financial Risk Engine** | PaySim (`5,000` streamed rows; `300` `isFraud=1` mule accounts evaluated) | **283 / 300 (94.3%)** flagged `HIGH` / `CRITICAL` |
| **Mule Indicator Engine** | PaySim `TRANSFER -> CASH_OUT` chains | **292 / 300 (97.3%)** flagged `HIGH_VOLUME` / `RAPID_WITHDRAWAL` |
| **DoT 22-Field CDR & Tower Parser** | `real_telecom_cdr.csv` (101,174 rows; 500-row slice) + `dot_22field_cdr_sample.csv` + `india_towers.csv` (`218` India MCC `404`/`405` towers) | Auto-detected `subscriber_summary_cdr` (`152,070` calls) & `indian_dot_22field` (`2` IMEI->MultiSIM swaps, `2` SIM->MultiIMEI swaps, `4` resolved towers) |
| **Offline IP & ASN Lookup** | MaxMind `GeoLite2-City.mmdb` + `GeoLite2-ASN.mmdb` | Instant zero-leak offline resolution (e.g., `49.36.128.1` -> New Delhi, `AS55836 Reliance Jio Infocomm Limited`) |

---

## Quickstart Guide

### Option 1: Production Deployment with Docker Compose (PostgreSQL 16)
1. Configure `.env` with strong production secrets (never commit `.env`):
   ```bash
   cp .env.example .env
   # Generate SECRET_KEY and ENCRYPTION_KEYS using Python secrets / cryptography.fernet
   ```
2. Start PostgreSQL and the hardened non-root Gunicorn container on port `8001`:
   ```bash
   docker compose up -d --build
   ```
3. Access the portal at `http://localhost:8001/frontend/index.html`.

### Option 2: Local Python Setup (Windows / Linux)
```powershell
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Linux/macOS:        source .venv/bin/activate && pip install -r requirements.txt

# Populate realistic Indian station cases, DoT CDRs & PaySim fraud data
.\.venv\Scripts\python.exe scripts\ingest_real_datasets.py

# Run FastAPI on port 8001
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8001 --reload
```

### Seeded Demo Station Credentials
| Role / Station | Username | Password | Scope |
| :--- | :--- | :--- | :--- |
| **SI (`Sector-62 Cyber PS`)** | `si_sector62` | `Sector62#2026` | `FIR/GBN/2026/101` (CDR & DoT 22-field case) |
| **SHO (`Sector-62 Cyber PS`)** | `sho_sector62` | `ShoSec62#2026` | `Sector-62 Cyber PS` approvals & logs |
| **SI (`Noida Central PS`)** | `si_noida_central` | `CentralNoida#2026` | `FIR/GBN/2026/102` (PaySim mule fraud case) |
| **DGP (`Statewide`)** | `dgp_state` | `NetraDgp#2026` | Statewide visibility & `/admin/logs/verify` |
| **Admin** | `netra_admin` | `NetraAdmin#2026` | User lifecycle & audit chain verification |

---

## Project Structure

```text
├── backend/              # FastAPI app, RBAC, hash-chained audit, routers & forensic engines
├── frontend/             # Bootstrap 5 UI, self-hosted DOMPurify, Vis.js & Service Worker
├── data/                 # SQLite dev DB, GeoLite2/India towers, datasets, encrypted uploads
├── deploy/               # PaaS configs (Procfile, render.yaml, CNAME)
├── docs/                 # R&D, Remediation & Dataset Integration reports
├── scripts/              # Dataset ingestion & live end-to-end verification CLIs
├── tests/                # Pytest security, RBAC & forensics regression suite
├── Dockerfile            # Non-root multi-stage production container
├── docker-compose.yml    # PostgreSQL 16 + FastAPI/Gunicorn stack
└── requirements.txt
```
