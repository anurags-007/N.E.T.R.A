from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from starlette.concurrency import run_in_threadpool
from backend.routers.auth import get_current_active_user
from backend import config, models
from backend.utils.validation import read_upload_with_limit, validate_file_magic_and_zip

import csv
import io
import ipaddress
import logging
import os
import re
import socket
import requests

logger = logging.getLogger(__name__)
MAX_TOWER_DUMP_FILES = 10

router = APIRouter(
    prefix="/tools",
    tags=["tools"],
)

GEOLITE_CITY_PATH = os.path.join("data", "geo", "GeoLite2-City.mmdb")
GEOLITE_ASN_PATH = os.path.join("data", "geo", "GeoLite2-ASN.mmdb")


def _lookup_offline_geolite2(target_ip: str, query: str, is_domain: bool) -> dict:
    """Resolve IP geolocation and ASN offline using local MaxMind GeoLite2 .mmdb files."""
    import geoip2.database
    import geoip2.errors

    country = None
    region = None
    city = None
    lat = None
    lon = None
    asn = None
    org = None
    found_any = False

    if os.path.exists(GEOLITE_CITY_PATH):
        with geoip2.database.Reader(GEOLITE_CITY_PATH) as city_reader:
            try:
                city_resp = city_reader.city(target_ip)
                country = city_resp.country.name
                region = city_resp.subdivisions.most_specific.name if city_resp.subdivisions else None
                city = city_resp.city.name
                lat = city_resp.location.latitude
                lon = city_resp.location.longitude
                found_any = True
            except geoip2.errors.AddressNotFoundError:
                pass

    if os.path.exists(GEOLITE_ASN_PATH):
        with geoip2.database.Reader(GEOLITE_ASN_PATH) as asn_reader:
            try:
                asn_resp = asn_reader.asn(target_ip)
                asn = asn_resp.autonomous_system_number
                org = asn_resp.autonomous_system_organization
                found_any = True
            except geoip2.errors.AddressNotFoundError:
                pass

    if not found_any:
        raise HTTPException(status_code=404, detail="IP address not found in offline GeoLite2 database")

    org_lower = (org or "").lower()
    is_mobile = any(k in org_lower for k in ("jio", "airtel", "vodafone", "idea", "bsnl", "cellular", "mobile"))
    map_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}" if (lat is not None and lon is not None) else "#"

    return {
        "query": query,
        "resolved_ip": target_ip if is_domain else None,
        "country": country,
        "region": region,
        "city": city,
        "isp": org,
        "organization": f"AS{asn} {org}" if asn and org else org,
        "asn": asn,
        "is_mobile": is_mobile,
        "is_proxy": False,
        "lat": lat,
        "lon": lon,
        "map_url": map_url,
        "source": "offline_geolite2",
    }


@router.get("/ip-lookup")
def ip_lookup(
    query: str,
    current_user: models.User = Depends(get_current_active_user),
):
    """
    Resolve and locate IP address or domain name.
    Uses local offline MaxMind GeoLite2 .mmdb files first (zero external network leak),
    falling back to HTTPS lookup only if the .mmdb files are missing.
    """
    query = query.strip()
    target_ip = query
    is_domain = False

    try:
        ip_obj = ipaddress.ip_address(query)
        target_ip = str(ip_obj)

        if ip_obj.is_private:
            return {
                "query": query,
                "resolved_ip": target_ip,
                "country": "Local Network (LAN)",
                "city": "Internal Device",
                "isp": "Private/Intranet",
                "organization": "Local System",
                "is_mobile": False,
                "is_proxy": False,
                "lat": 0,
                "lon": 0,
                "map_url": "#",
                "source": "local_rfc1918",
                "note": "This is a Private IP. It exists only inside your local Network, not on the public internet.",
            }
    except ValueError:
        is_domain = True
        try:
            target_ip = socket.gethostbyname(query)
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="Invalid Domain Name or IP address")
        resolved_obj = ipaddress.ip_address(target_ip)
        if resolved_obj.is_private or resolved_obj.is_loopback or resolved_obj.is_link_local or resolved_obj.is_reserved or resolved_obj.is_multicast:
            raise HTTPException(status_code=400, detail="Domain resolves to a restricted internal/private IP address")

    # 1. Offline GeoLite2 Lookup (Preferred - zero external HTTP leakage)
    if os.path.exists(GEOLITE_CITY_PATH) or os.path.exists(GEOLITE_ASN_PATH):
        return _lookup_offline_geolite2(target_ip, query, is_domain)

    # 2. HTTPS Fallback ONLY if local .mmdb files are absent
    try:
        response = requests.get(f"https://ipwho.is/{target_ip}", timeout=5)
        response.raise_for_status()
        data = response.json()

        if not data.get("success", False):
            raise HTTPException(status_code=400, detail=f"Lookup failed: {data.get('message', 'Unknown error')}")

        conn = data.get("connection") or {}
        lat = data.get("latitude")
        lon = data.get("longitude")
        return {
            "query": query,
            "resolved_ip": target_ip if is_domain else None,
            "country": data.get("country"),
            "region": data.get("region"),
            "city": data.get("city"),
            "isp": conn.get("isp"),
            "organization": conn.get("org"),
            "asn": conn.get("asn"),
            "is_mobile": False,
            "is_proxy": False,
            "lat": lat,
            "lon": lon,
            "map_url": f"https://www.google.com/maps/search/?api=1&query={lat},{lon}" if lat and lon else "#",
            "source": "https_ipwho",
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Offline GeoLite2 databases missing and external HTTPS geolocation service unavailable.",
        )


def _iter_cell_values(orig_name: str, content: bytes):
    """Yield cell string values from CSV or XLSX without requiring native C-extension loaders."""
    lower = orig_name.lower()
    if lower.endswith(".csv"):
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        next(reader, None)  # Skip header
        for row in reader:
            for val in row:
                if val is not None and str(val).strip():
                    yield str(val).strip()
    elif lower.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                continue
            for val in row:
                if val is not None and str(val).strip():
                    yield str(val).strip()
        wb.close()
    elif lower.endswith(".xls"):
        import pandas as pd
        df = pd.read_excel(io.BytesIO(content), dtype=str)
        for col in df.columns:
            for val in df[col].dropna():
                s = str(val).strip()
                if s:
                    yield s


@router.post("/analyze-tower-dump")
async def analyze_tower_dump(
    files: list[UploadFile] = File(...),
    current_user: models.User = Depends(get_current_active_user),
):
    """
    TOWER DUMP & FINANCIAL ANALYSIS
    Input: Multiple Excel/CSV files.
    Output: Common Mobile Numbers, Bank Accounts, and UPI IDs present in ALL files.
    """
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Please upload at least 2 files to compare.")
    if len(files) > MAX_TOWER_DUMP_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files. Maximum allowed: {MAX_TOWER_DUMP_FILES}.")

    payloads = []
    for file in files:
        orig_name = file.filename or ""
        ext = os.path.splitext(orig_name)[1].lower()
        if ext not in (".csv", ".xls", ".xlsx"):
            raise HTTPException(status_code=400, detail="Invalid file type. Only .csv, .xls, and .xlsx are supported.")
        content = await read_upload_with_limit(file, config.MAX_FILE_SIZE_BYTES)
        is_safe, safety_err = validate_file_magic_and_zip(content, ext)
        if not is_safe:
            raise HTTPException(status_code=400, detail=safety_err)
        payloads.append((orig_name, content))

    def _run_intersection() -> dict:
        common_mobile = set()
        common_account = set()
        common_upi = set()
        first_file = True
        file_stats = []

        for orig_name, content in payloads:
            if not orig_name.lower().endswith((".csv", ".xls", ".xlsx")):
                continue

            file_mobile = set()
            file_account = set()
            file_upi = set()

            for val_str in _iter_cell_values(orig_name, content):
                clean_mobile = re.sub(r"\D", "", val_str)
                if len(clean_mobile) >= 10:
                    potential_mobile = clean_mobile[-10:]
                    if potential_mobile.startswith(("6", "7", "8", "9")):
                        file_mobile.add(potential_mobile)
                if "@" in val_str and " " not in val_str and len(val_str) > 5:
                    file_upi.add(val_str.lower())
                if re.match(r"^\d{9,18}$", val_str) and not re.match(r"^[6-9]\d{9}$", val_str):
                    file_account.add(val_str)

            file_stats.append({
                "filename": orig_name,
                "mobiles": len(file_mobile),
                "accounts": len(file_account),
                "upis": len(file_upi),
            })

            if first_file:
                common_mobile = file_mobile
                common_account = file_account
                common_upi = file_upi
                first_file = False
            else:
                common_mobile = common_mobile.intersection(file_mobile)
                common_account = common_account.intersection(file_account)
                common_upi = common_upi.intersection(file_upi)

        return {
            "common_numbers": list(common_mobile),
            "common_accounts": list(common_account),
            "common_upis": list(common_upi),
            "counts": {
                "mobile": len(common_mobile),
                "account": len(common_account),
                "upi": len(common_upi),
            },
            "file_stats": file_stats,
            "message": "Analysis Complete",
        }

    try:
        return await run_in_threadpool(_run_intersection)
    except Exception:
        logger.exception("Tower dump analysis failed")
        raise HTTPException(status_code=500, detail="Tower dump analysis failed due to an internal processing error.")
