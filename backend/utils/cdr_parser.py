"""CDR & Indian DoT 22-Field / Cell-Tower Forensic Parser."""
from collections import Counter, defaultdict
import csv
from datetime import datetime
import io
import os
import re
from typing import Dict, List, Optional, Tuple


TOWER_INDEX_PATH = os.path.join("data", "geo", "india_towers.csv")


def _load_india_towers() -> Tuple[Dict[Tuple[str, str, str, str], dict], Dict[str, dict]]:
    """Load Indian MCC 404/405 tower coordinates indexed by (mcc, mnc, lac, cell_id) and cell_id."""
    exact_idx: Dict[Tuple[str, str, str, str], dict] = {}
    cell_idx: Dict[str, dict] = {}
    if not os.path.exists(TOWER_INDEX_PATH):
        return exact_idx, cell_idx

    with open(TOWER_INDEX_PATH, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mcc = (row.get("mcc") or "").strip()
            mnc = (row.get("mnc") or "").strip().lstrip("0") or "0"
            mnc_padded = (row.get("mnc") or "").strip().zfill(2)
            lac = (row.get("lac") or "").strip()
            cell_id = (row.get("cell_id") or "").strip()
            entry = {
                "mcc": mcc,
                "mnc": mnc_padded,
                "lac": lac,
                "cell_id": cell_id,
                "operator": row.get("operator", "").strip(),
                "circle": row.get("circle", "").strip(),
                "lat": float(row["lat"]) if row.get("lat") else None,
                "lon": float(row["lon"]) if row.get("lon") else None,
            }
            exact_idx[(mcc, mnc, lac, cell_id)] = entry
            exact_idx[(mcc, mnc_padded, lac, cell_id)] = entry
            if cell_id:
                cell_idx[cell_id] = entry
    return exact_idx, cell_idx


def _resolve_cgi(
    cgi_raw: str,
    exact_idx: Dict[Tuple[str, str, str, str], dict],
    cell_idx: Dict[str, dict],
) -> Optional[dict]:
    """Parse MCC-MNC-LAC-CellID or bare CellID against India tower lookup."""
    val = (cgi_raw or "").strip()
    if not val:
        return None
    parts = [p for p in re.split(r"[-:/\s]+", val) if p]
    if len(parts) >= 4:
        mcc, mnc, lac, cell_id = parts[0], parts[1], parts[2], parts[3]
        hit = exact_idx.get((mcc, mnc, lac, cell_id)) or exact_idx.get((mcc, mnc.lstrip("0") or "0", lac, cell_id))
        if hit:
            return hit
        if cell_id in cell_idx:
            return cell_idx[cell_id]
    if val in cell_idx:
        return cell_idx[val]
    return None


def _read_tabular_rows(file_content: bytes, file_ext: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read CSV or Excel bytes into (headers, dict_rows) using pure-Python readers first."""
    lower = (file_ext or "").lower()
    if lower.endswith(".csv") or "csv" in lower:
        text = file_content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        headers = [h.strip() for h in (reader.fieldnames or [])]
        rows = []
        for raw in reader:
            rows.append({(k or "").strip(): ("" if v is None else str(v).strip()) for k, v in raw.items()})
        return headers, rows

    if lower.endswith(".xlsx") or "xlsx" in lower:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        raw_headers = next(it, None)
        if not raw_headers:
            wb.close()
            return [], []
        headers = ["" if h is None else str(h).strip() for h in raw_headers]
        rows = []
        for row_vals in it:
            row_dict = {}
            for idx, h in enumerate(headers):
                val = row_vals[idx] if idx < len(row_vals) else None
                row_dict[h] = "" if val is None else str(val).strip()
            rows.append(row_dict)
        wb.close()
        return headers, rows

    # Legacy .xls fallback
    import pandas as pd
    df = pd.read_excel(io.BytesIO(file_content), dtype=str)
    headers = [str(c).strip() for c in df.columns]
    rows = df.fillna("").astype(str).to_dict(orient="records")
    return headers, rows


def _parse_hour(dt_str: str) -> Optional[int]:
    val = (dt_str or "").strip()
    if not val:
        return None
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M",
        "%H:%M:%S",
        "%H:%M",
    ):
        try:
            return datetime.strptime(val[:19], fmt).hour
        except ValueError:
            continue
    m = re.search(r"\b(\d{1,2}):\d{2}", val)
    if m:
        hr = int(m.group(1))
        if 0 <= hr <= 23:
            return hr
    return None


def _parse_subscriber_summary_cdr(rows: List[Dict[str, str]], norm_to_orig: Dict[str, str]) -> dict:
    """Parse subscriber-level telecom summary dataset (e.g. data/datasets/real_telecom_cdr.csv)."""
    phone_col = norm_to_orig["phone number"]
    day_calls_col = norm_to_orig.get("day calls")
    eve_calls_col = norm_to_orig.get("eve calls")
    night_calls_col = norm_to_orig.get("night calls")
    intl_calls_col = norm_to_orig.get("intl calls")
    day_mins_col = norm_to_orig.get("day mins")
    eve_mins_col = norm_to_orig.get("eve mins")
    night_mins_col = norm_to_orig.get("night mins")
    intl_mins_col = norm_to_orig.get("intl mins")
    churn_col = norm_to_orig.get("churn")
    custserv_col = norm_to_orig.get("custserv calls")

    total_calls = 0
    total_minutes = 0.0
    subscriber_calls: Counter = Counter()
    intl_heavy_accounts: Counter = Counter()
    churn_true_count = 0
    high_custserv_count = 0

    def _f(row: dict, col: Optional[str]) -> float:
        if not col:
            return 0.0
        try:
            return float(row.get(col) or 0)
        except ValueError:
            return 0.0

    for row in rows:
        phone = row.get(phone_col, "").strip()
        if not phone:
            continue
        calls = int(round(_f(row, day_calls_col) + _f(row, eve_calls_col) + _f(row, night_calls_col) + _f(row, intl_calls_col)))
        mins = _f(row, day_mins_col) + _f(row, eve_mins_col) + _f(row, night_mins_col) + _f(row, intl_mins_col)
        intl_calls = int(round(_f(row, intl_calls_col)))

        total_calls += calls
        total_minutes += mins
        subscriber_calls[phone] += calls
        if intl_calls > 0:
            intl_heavy_accounts[phone] += intl_calls
        if churn_col and row.get(churn_col, "").strip().upper() == "TRUE":
            churn_true_count += 1
        if custserv_col and _f(row, custserv_col) >= 4:
            high_custserv_count += 1

    return {
        "schema_detected": "subscriber_summary_cdr",
        "total_records": len(rows),
        "total_calls": int(total_calls),
        "total_duration": int(round(total_minutes * 60)),
        "top_contacts_outgoing": dict(subscriber_calls.most_common(10)),
        "top_contacts_incoming": dict(intl_heavy_accounts.most_common(10)),
        "hourly_stats": {},
        "imei_to_multiple_sims": {},
        "sim_to_multiple_imeis": {},
        "resolved_towers": [],
        "subscriber_risk_metrics": {
            "churned_subscribers": churn_true_count,
            "high_custserv_call_subscribers": high_custserv_count,
        },
        "column_mapping_used": {
            "phone": phone_col,
            "day_calls": day_calls_col,
            "eve_calls": eve_calls_col,
            "night_calls": night_calls_col,
            "intl_calls": intl_calls_col,
        },
    }


def parse_cdr(file_content: bytes, file_ext: str):
    """
    Parse CDR files (CSV/Excel) across:
      1. Official Indian DoT 22-field / event-level CDR schemas
      2. Standard Source/Destination CDR schemas
      3. Subscriber-level summary CDR datasets (e.g., real_telecom_cdr.csv)
    Includes IMEI-to-multiple-SIM / SIM-to-multiple-IMEI forensic anomaly detection
    and offline Indian MCC 404/405 cell-tower resolution from data/geo/india_towers.csv.
    """
    try:
        headers, rows = _read_tabular_rows(file_content, file_ext)
        if not headers:
            return {"error": "CDR file is empty or missing headers."}

        norm_to_orig = {h.lower().strip(): h for h in headers}

        # Check Subscriber Summary CDR format first (e.g., real_telecom_cdr.csv)
        if "phone number" in norm_to_orig and ("day calls" in norm_to_orig or "day mins" in norm_to_orig):
            return _parse_subscriber_summary_cdr(rows, norm_to_orig)

        # Map Indian DoT 22-field and generic event CDR headers
        aliases = {
            "source": ["a_party", "calling_no", "calling_party", "calling number", "source number", "source", "caller", "origin", "from"],
            "destination": ["b_party", "called_no", "called_party", "called number", "destination number", "destination", "callee", "term", "to"],
            "call_type": ["call_type", "service_type", "type"],
            "call_date": ["call_date", "date"],
            "call_time": ["call_time", "time"],
            "datetime": ["datetime", "timestamp", "start_time", "date_time", "call_datetime"],
            "duration": ["duration", "dur", "duration_sec", "sec"],
            "imei": ["imei", "imei_no", "a_imei", "handset_imei"],
            "imsi": ["imsi", "imsi_no", "a_imsi"],
            "cgi": ["first_cgi", "cgi", "cell_id", "first_cell_id", "lac_cell_id"],
            "bts_location": ["first_bts_location", "bts_location", "tower_location", "location"],
        }

        col_map: Dict[str, str] = {}
        for field, candidates in aliases.items():
            for cand in candidates:
                if cand in norm_to_orig:
                    col_map[field] = norm_to_orig[cand]
                    break
            if field not in col_map:
                # Substring fallback for non-standard headers
                for norm_h, orig_h in norm_to_orig.items():
                    if any(cand in norm_h for cand in candidates):
                        col_map[field] = orig_h
                        break

        if "source" not in col_map or "destination" not in col_map:
            return {
                "error": "Could not identify Source/Destination (or A_PARTY/B_PARTY) columns in CDR file."
            }

        is_dot_22 = any(
            k in norm_to_orig
            for k in ("a_party", "b_party", "calling_no", "called_no", "first_cgi", "first_bts_location")
        )

        exact_idx, cell_idx = _load_india_towers()
        outgoing: Counter = Counter()
        incoming: Counter = Counter()
        hourly: Counter = Counter()
        total_duration = 0

        imei_to_sims: Dict[str, set] = defaultdict(set)
        sim_to_imeis: Dict[str, set] = defaultdict(set)
        tower_hits: Dict[str, dict] = {}

        for row in rows:
            src = row.get(col_map["source"], "").strip()
            dst = row.get(col_map["destination"], "").strip()
            if src:
                incoming[src] += 1
            if dst:
                outgoing[dst] += 1

            if "duration" in col_map:
                try:
                    total_duration += int(float(row.get(col_map["duration"]) or 0))
                except ValueError:
                    pass

            dt_val = ""
            if "datetime" in col_map:
                dt_val = row.get(col_map["datetime"], "")
            elif "call_date" in col_map and "call_time" in col_map:
                dt_val = f"{row.get(col_map['call_date'], '')} {row.get(col_map['call_time'], '')}".strip()
            elif "call_time" in col_map:
                dt_val = row.get(col_map["call_time"], "")
            hr = _parse_hour(dt_val)
            if hr is not None:
                hourly[hr] += 1

            if "imei" in col_map:
                imei = row.get(col_map["imei"], "").strip()
                if imei and src:
                    imei_to_sims[imei].add(src)
                    sim_to_imeis[src].add(imei)

            if "cgi" in col_map:
                cgi = row.get(col_map["cgi"], "").strip()
                if cgi:
                    resolved = _resolve_cgi(cgi, exact_idx, cell_idx)
                    bts_loc = row.get(col_map["bts_location"], "").strip() if "bts_location" in col_map else ""
                    if cgi not in tower_hits:
                        tower_hits[cgi] = {
                            "cgi": cgi,
                            "bts_location": bts_loc or (resolved["circle"] if resolved else "Unresolved"),
                            "operator": resolved["operator"] if resolved else "Unknown",
                            "circle": resolved["circle"] if resolved else "Unknown",
                            "lat": resolved["lat"] if resolved else None,
                            "lon": resolved["lon"] if resolved else None,
                            "hit_count": 0,
                        }
                    tower_hits[cgi]["hit_count"] += 1

        imei_multi_sim = {k: sorted(v) for k, v in imei_to_sims.items() if len(v) > 1}
        sim_multi_imei = {k: sorted(v) for k, v in sim_to_imeis.items() if len(v) > 1}

        return {
            "schema_detected": "indian_dot_22field" if is_dot_22 else "event_cdr",
            "total_calls": len(rows),
            "total_duration": int(total_duration),
            "top_contacts_outgoing": dict(outgoing.most_common(10)),
            "top_contacts_incoming": dict(incoming.most_common(10)),
            "hourly_stats": dict(sorted(hourly.items())),
            "imei_to_multiple_sims": imei_multi_sim,
            "sim_to_multiple_imeis": sim_multi_imei,
            "resolved_towers": sorted(tower_hits.values(), key=lambda t: t["hit_count"], reverse=True),
            "column_mapping_used": col_map,
        }

    except Exception as e:
        return {"error": f"Failed to parse file: {str(e)}"}


def _parse_dt(raw: str) -> Optional[datetime]:
    """Parse common CDR timestamp formats into datetime."""
    val = (raw or "").strip()
    if not val:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(val[:19], fmt)
        except ValueError:
            continue
    return None


def extract_tower_co_locations(
    evidence_items: List[Tuple[bytes, str]],
    window_minutes: int = 15,
) -> dict:
    """
    Group case CDR/tower events by (lac, cell_id) / CGI and identify distinct MSISDN pairs
    active on the same cell tower within ±window_minutes.
    """
    exact_idx, cell_idx = _load_india_towers()
    tower_events: Dict[Tuple[str, str], List[Tuple[datetime, str, str, str]]] = defaultdict(list)
    files_scanned = 0

    for content, filename in evidence_items:
        lower = (filename or "").lower()
        if not lower.endswith((".csv", ".xlsx", ".xls")):
            continue
        try:
            headers, rows = _read_tabular_rows(content, lower)
        except Exception:
            continue
        if not headers or not rows:
            continue
        files_scanned += 1
        norm_to_orig = {h.lower().strip(): h for h in headers}

        src_col = next((norm_to_orig[k] for k in ("a_party", "calling_no", "calling_party", "source", "caller", "msisdn", "phone number") if k in norm_to_orig), None)
        cgi_col = next((norm_to_orig[k] for k in ("first_cgi", "cgi", "cell_id", "tower_id", "last_cgi") if k in norm_to_orig), None)
        lac_col = next((norm_to_orig[k] for k in ("lac", "lac_id") if k in norm_to_orig), None)
        cell_col = next((norm_to_orig[k] for k in ("cell_id", "cell") if k in norm_to_orig), None)
        bts_col = next((norm_to_orig[k] for k in ("first_bts_location", "bts_location", "tower_location", "location") if k in norm_to_orig), None)
        dt_col = next((norm_to_orig[k] for k in ("call_datetime", "datetime", "timestamp") if k in norm_to_orig), None)
        date_col = next((norm_to_orig[k] for k in ("date", "call_date") if k in norm_to_orig), None)
        time_col = next((norm_to_orig[k] for k in ("time", "call_time") if k in norm_to_orig), None)

        if not src_col or (not cgi_col and not cell_col):
            continue

        for row in rows:
            msisdn = (row.get(src_col) or "").strip()
            if not msisdn:
                continue
            cgi = (row.get(cgi_col) or "").strip() if cgi_col else ""
            lac = (row.get(lac_col) or "").strip() if lac_col else ""
            cell_id = (row.get(cell_col) or "").strip() if cell_col else ""

            if cgi and (not lac or not cell_id):
                parts = [p for p in re.split(r"[-:/\s]+", cgi) if p]
                if len(parts) >= 4:
                    lac = lac or parts[2]
                    cell_id = cell_id or parts[3]
                elif not cell_id:
                    cell_id = cgi

            if not cell_id and not cgi:
                continue

            dt_raw = (row.get(dt_col) or "").strip() if dt_col else ""
            if not dt_raw and date_col and time_col:
                dt_raw = f"{row.get(date_col, '')} {row.get(time_col, '')}".strip()
            ts = _parse_dt(dt_raw)
            if not ts:
                continue

            bts_loc = (row.get(bts_col) or "").strip() if bts_col else ""
            tower_events[(lac, cell_id)].append((ts, msisdn, cgi or f"{lac}-{cell_id}", bts_loc))

    window_sec = window_minutes * 60
    pair_stats: Dict[Tuple[str, str, str, str], dict] = {}

    for (lac, cell_id), evs in tower_events.items():
        evs.sort(key=lambda x: x[0])
        for i in range(len(evs)):
            ts_a, m_a, cgi_a, bts_a = evs[i]
            for j in range(i + 1, len(evs)):
                ts_b, m_b, _cgi_b, bts_b = evs[j]
                delta_sec = (ts_b - ts_a).total_seconds()
                if delta_sec > window_sec:
                    break
                if m_a == m_b:
                    continue
                pair_a, pair_b = sorted((m_a, m_b))
                key = (pair_a, pair_b, lac, cell_id)
                delta_min = round(delta_sec / 60.0, 2)
                if key not in pair_stats:
                    resolved = _resolve_cgi(cgi_a, exact_idx, cell_idx) or _resolve_cgi(cell_id, exact_idx, cell_idx)
                    pair_stats[key] = {
                        "msisdn_a": pair_a,
                        "msisdn_b": pair_b,
                        "lac": lac or (resolved["lac"] if resolved else "-"),
                        "cell_id": cell_id,
                        "cgi": cgi_a,
                        "tower_name": bts_a or bts_b or (resolved["circle"] if resolved else "Unknown Tower"),
                        "operator": resolved["operator"] if resolved else "Unknown",
                        "lat": resolved["lat"] if resolved else None,
                        "lon": resolved["lon"] if resolved else None,
                        "co_location_count": 0,
                        "min_delta_minutes": delta_min,
                    }
                pair_stats[key]["co_location_count"] += 1
                if delta_min < pair_stats[key]["min_delta_minutes"]:
                    pair_stats[key]["min_delta_minutes"] = delta_min

    ranked = sorted(
        pair_stats.values(),
        key=lambda p: (-p["co_location_count"], p["min_delta_minutes"]),
    )[:100]

    return {
        "files_scanned": files_scanned,
        "window_minutes": window_minutes,
        "total_pairs": len(ranked),
        "pairs": ranked,
    }
