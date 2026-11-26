# N.E.T.R.A. — Real Dataset Integration & Benchmark Report

**Database Updated:** `data/police_caf.db` (backup saved at `data/police_caf.db.bak`)  
**Ingestion Script:** `scripts/ingest_real_datasets.py`

---

## 1. Datasets Downloaded & Prepared

| Dataset | Source URL | Local File Path | Size (bytes) | Data Rows | Column Headers |
| :--- | :--- | :--- | ---: | ---: | :--- |
| **MaxMind GeoLite2 City** | `https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-City.mmdb` | `data/geo/GeoLite2-City.mmdb` | 50,531,001 | Binary MMDB | MaxMind GeoLite2 City schema |
| **MaxMind GeoLite2 ASN** | `https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/GeoLite2-ASN.mmdb` | `data/geo/GeoLite2-ASN.mmdb` | 9,079,903 | Binary MMDB | MaxMind GeoLite2 ASN schema |
| **Indian MCC 404/405 Towers** | `https://raw.githubusercontent.com/pbakondy/mcc-mnc-list/master/mcc-mnc-list.json` (+ Noida/Lucknow DoT forensic entries) | `data/geo/india_towers.csv` | 13,159 | 218 | `mcc,mnc,lac,cell_id,operator,circle,lat,lon` |
| **Real Telecom CDR** | `https://raw.githubusercontent.com/jamesrawlins1000/Telecom-CDR-Dataset-/master/Call%20Details-Data.csv` | `data/datasets/real_telecom_cdr.csv` | 8,191,461 | 101,174 | `Phone Number,Account Length,VMail Message,Day Mins,Day Calls,Day Charge,Eve Mins,Eve Calls,Eve Charge,Night Mins,Night Calls,Night Charge,Intl Mins,Intl Calls,Intl Charge,CustServ Calls,Churn` |
| **PaySim Mobile Money Fraud (Sample)** | `https://media.githubusercontent.com/media/lordlinus/cosmosdb-graph-demo/main/load_data/data/PS_20174392719_1491204439457_log.csv` *(Kaggle CLI unavailable; streamed balanced sample)* | `data/datasets/paysim_sample.csv` | 373,793 | 5,000 *(1,500 `isFraud=1`, 3,500 `isFraud=0`)* | `step,type,amount,nameOrig,oldbalanceOrg,newbalanceOrig,nameDest,oldbalanceDest,newbalanceDest,isFraud,isFlaggedFraud` |
| **Indian DoT 22-Field CDR Sample** | Generated in `scripts/ingest_real_datasets.py` | `data/test_data/dot_22field_cdr_sample.csv` | 10,718 | 50 | `A_PARTY,B_PARTY,CALL_TYPE,CALL_DATE,CALL_TIME,DURATION,FIRST_CGI,LAST_CGI,FIRST_BTS_LOCATION,IMEI,IMSI,ROAMING_CIRCLE,SMS_CENTER,SERVICE_TYPE,CALL_STATUS,RECORD_TYPE,NETWORK_ID,PORTED_FLAG,TECH_TYPE,MSC_ID,TRUNK_GROUP,SWITCH_ID` |

---

## 2. Schema Mappings to N.E.T.R.A. Engines & Models

### 2.1 Offline GeoIP & ASN (`backend/routers/tools.py`)
- `/tools/ip-lookup` resolves public IPs and hostnames using `geoip2.database.Reader` against `data/geo/GeoLite2-City.mmdb` and `data/geo/GeoLite2-ASN.mmdb` first (`source: "offline_geolite2"`), eliminating external HTTP leaks.
- Falls back to `https://ipwho.is/{target_ip}` (`timeout=5`) **only** when `.mmdb` files are missing on disk.
- Private RFC 1918 IPs return `source: "local_rfc1918"`.

### 2.2 Telecom & DoT 22-Field CDR Parser (`backend/utils/cdr_parser.py`)
- **Subscriber Summary CDR (`real_telecom_cdr.csv`):** Auto-detects `Phone Number` + `Day Calls`/`Day Mins` and aggregates Day/Eve/Night/Intl call volumes, total duration in seconds, top active subscribers, international call outliers, churn count, and high customer-service call counts (`schema_detected: "subscriber_summary_cdr"`).
- **Indian DoT 22-Field / Event CDR (`dot_22field_cdr_sample.csv`):** Normalizes `A_PARTY`/`CALLING_NO` -> `source`, `B_PARTY`/`CALLED_NO` -> `destination`, `CALL_DATE` + `CALL_TIME` -> `hourly_stats`, `DURATION` -> `total_duration`, `IMEI`, `IMSI`, `FIRST_CGI`/`CELL_ID` -> `cgi`, and `FIRST_BTS_LOCATION` -> `bts_location` (`schema_detected: "indian_dot_22field"`).
- **Forensic & Tower Enrichment:** Computes `imei_to_multiple_sims` and `sim_to_multiple_imeis` anomalies, and resolves `MCC-MNC-LAC-CellID` strings from `data/geo/india_towers.csv` into `operator`, `circle`, `lat`, `lon`, and `hit_count`.

### 2.3 PaySim Fraud -> Financial Intelligence (`scripts/ingest_real_datasets.py`)
- Maps PaySim customer/merchant IDs (`nameOrig`, `nameDest`) to `FinancialEntity` (`BANK_ACCOUNT` for `C...`, `WALLET` for `M...`).
- Links paired `isFraud=1` `TRANSFER` -> `CASH_OUT` chains sharing `(step, amount)` onto the recipient mule `FinancialEntity`, logging `PAYMENT` (inflow) and `WITHDRAWAL` (outflow) events into `TransactionTimeline`.
- Encrypted raw CSV evidence files (`real_telecom_cdr_500.csv` and `dot_22field_cdr_sample.csv`) are stored in `data/secure_uploads/` via `MultiFernet` with plaintext SHA-256 hashes and SHA-256 hash-chained `AuditLog` entries.

---

## 3. Live Verification & Benchmark Metrics

### Database State (`data/police_caf.db`)
- **Users:** `19` (includes `admin`, `dgp_state`, `si_sector62`, `sho_sector62`, `si_noida_central`)
- **Cases:** `3` (includes `FIR/GBN/2026/101` at `Sector-62 Cyber PS` and `FIR/GBN/2026/102` at `Noida Central PS`)
- **Evidence:** `2` (`real_telecom_cdr_500.csv`, `dot_22field_cdr_sample.csv`)
- **Financial Entities:** `4,263`
- **Transaction Timeline Events:** `5,000`
- **Audit Log Entries:** `34`

### Engine Benchmark Outputs
1. **Telecom CDR Parser (`cdr_parser.py`):**
   - `real_telecom_cdr_500.csv` (500 rows) -> `Evidence #1`, `schema_detected: subscriber_summary_cdr`, `Total Calls: 152,070`, `Duration(s): 17,920,452`.
   - `dot_22field_cdr_sample.csv` (50 rows) -> `Evidence #2`, `schema_detected: indian_dot_22field`, `IMEI->MultiSIM anomalies: 2` (`358240051111110` linked to `['6399887766', '9876543210', '9910099100']`; `359999002222221` linked to `['9876543210', '9910099100']`), `SIM->MultiIMEI anomalies: 2`, `Resolved Towers: 4` (e.g., `404-10-1042-41201` -> `Bharti Airtel Limited (Delhi/NCR)`, `Delhi NCR / Sector-62 Noida`, `28.6279, 77.3649`, 17 hits).
2. **PaySim Risk & Mule Detection (`risk_engine.py` + mule logic):**
   - Evaluated `300` known `isFraud=1` mule accounts (out of `5,000` ingested rows / `3,500` normal accounts).
   - `risk_engine.py` flagged **281 / 300 (93.7%)** as `HIGH` or `CRITICAL`.
   - Mule indicators (`HIGH_VOLUME` / `RAPID_WITHDRAWAL`) flagged **288 / 300 (96.0%)** of fraud accounts.
3. **Offline GeoLite2 Lookups:**
   - `8.8.8.8` -> `Country=United States`, `Lat/Lon=(37.751, -97.822)`, `AS15169 (Google LLC)`
   - `1.1.1.1` -> `AS13335 (Cloudflare, Inc.)`
   - `49.36.128.1` -> `Country=India`, `City=New Delhi`, `Lat/Lon=(28.6327, 77.2198)`, `AS55836 (Reliance Jio Infocomm Limited)`
   - `157.240.22.35` -> `Country=United States`, `Lat/Lon=(37.751, -97.822)`, `AS32934 (Facebook, Inc.)`

---

## 4. Commands to Start & Inspect in the UI

> **Note:** On Windows hosts with Application Control blocking `.pyd` extensions in `.venv`, allow `.venv` in Windows Security (or run in WSL2/Docker) before launching Uvicorn.

```powershell
# Start FastAPI server (port 8001)
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8001 --reload
```

Open `http://localhost:8001/frontend/index.html` and sign in with the newly seeded station accounts:
- **Sector-62 Cyber PS (CDR & DoT 22-Field Case `FIR/GBN/2026/101`):** `si_sector62` / `Sector62#2026` (or SHO `sho_sector62` / `ShoSec62#2026`)
- **Noida Central PS (PaySim Financial Fraud Case `FIR/GBN/2026/102`):** `si_noida_central` / `CentralNoida#2026`
- **Statewide / Admin View:** `netra_admin` / `NetraAdmin#2026` or `dgp_state` / `NetraDgp#2026`
