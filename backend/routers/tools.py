from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from backend.routers.auth import get_current_active_user
from backend import models

import socket
import requests

router = APIRouter(
    prefix="/tools",
    tags=["tools"]
)

@router.get("/ip-lookup")
def ip_lookup(
    query: str,
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Resolve and Locate IP Address / Domain Name.
    Uses public APIs (ip-api.com) for geolocation.
    Respects privacy by not sending user-specific case data, only the IP query.
    """
    query = query.strip()
    
    # 1. Input Classification (IP vs Domain)
    import ipaddress
    target_ip = query
    is_domain = False
    is_valid_ip = False

    # Check if input is a valid IP (v4 or v6) first
    try:
        ip_obj = ipaddress.ip_address(query)
        is_valid_ip = True
        target_ip = str(ip_obj)
        
        # Check for Private/Local IP
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
                "note": "This is a Private IP. It exists only inside your local Network, not on the public internet."
            }

    except ValueError:
        # Not a valid IP, treat as Domain Name
        is_domain = True
        try:
            target_ip = socket.gethostbyname(query)
        except socket.gaierror:
            raise HTTPException(status_code=400, detail="Invalid Domain Name or IP address")

    # 2. Geo-Location Lookup
    # Using ip-api.com (Free for non-commercial, rate-limited)
    # Ideally, for a police system, we'd buy a MaxMind local DB.
    # For now, we wrap the external call.
    try:
        response = requests.get(f"http://ip-api.com/json/{target_ip}?fields=status,message,country,city,isp,org,as,mobile,proxy,query,lat,lon")
        data = response.json()
        
        if data['status'] == 'fail':
             raise HTTPException(status_code=400, detail=f"Lookup failed: {data.get('message')}")
             
        result = {
            "query": query,
            "resolved_ip": target_ip if is_domain else None,
            "country": data.get('country'),
            "city": data.get('city'),
            "isp": data.get('isp'),
            "organization": data.get('org'),
            "is_mobile": data.get('mobile', False), # Good for distinguishing Jio mobile vs Fiber
            "is_proxy": data.get('proxy', False),
            "lat": data.get('lat'),
            "lon": data.get('lon'),
            "map_url": f"https://www.google.com/maps/search/?api=1&query={data.get('lat')},{data.get('lon')}"
        }
        
        return result

    except Exception as e:
        # Fallback for Demo / Offline Mode
        # If external API fails, return a realistic mock response for demonstration
        print(f"IP Lookup Failed: {e}. Returning mock data.")
        return {
            "query": query,
            "resolved_ip": target_ip,
            "country": "India (Demo Result)",
            "city": "Lucknow",
            "isp": "Reliance Jio Infocomm Ltd",
            "organization": "Jio",
            "is_mobile": True,
            "is_proxy": False,
            "lat": 26.8467,
            "lon": 80.9462,
            "map_url": "https://www.google.com/maps/search/?api=1&query=26.8467,80.9462",
            "note": "External API Unreachable. Showing Demo Data."
        }


@router.post("/analyze-tower-dump")
async def analyze_tower_dump(
    files: list[UploadFile] = File(...),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    TOWER DUMP & FINANCIAL ANALYSIS
    Input: Multiple Excel/CSV files.
    Output: Common Mobile Numbers, Bank Accounts, and UPI IDs present in ALL files.
    """
    import pandas as pd
    import io
    import re
    
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Please upload at least 2 files to compare.")

    # Sets for intersection
    common_mobile = set()
    common_account = set()
    common_upi = set()
    
    first_file = True
    file_stats = []

    try:
        for file in files:
            content = await file.read()
            filename = file.filename.lower()
            
            # Read Data
            if filename.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(content), dtype=str)
            elif filename.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(io.BytesIO(content), dtype=str)
            else:
                continue # Skip non-data files

            # Local sets for this file
            file_mobile = set()
            file_account = set()
            file_upi = set()
            
            for col in df.columns:
                for val in df[col].dropna():
                    val_str = str(val).strip()
                    
                    # 1. Mobile Number (10 digits)
                    # Remove non-digits for mobile check
                    clean_mobile = re.sub(r'\D', '', val_str)
                    if len(clean_mobile) >= 10:
                        potential_mobile = clean_mobile[-10:]
                        if potential_mobile.startswith(('6','7','8','9')):
                            file_mobile.add(potential_mobile)
                    
                    # 2. UPI ID (contains @, no spaces)
                    if '@' in val_str and ' ' not in val_str and len(val_str) > 5:
                        file_upi.add(val_str.lower())
                        
                    # 3. Bank Account (9-18 digits, strictly numeric)
                    # We use strict regex to avoid confusing with other numeric IDs
                    if re.match(r'^\d{9,18}$', val_str):
                        # Simple heuristic: Accounts usually don't start with 6-9 if they are 10 digits (conflict with mobile)
                        # But to be safe, we add it. Overlap is handled by context usually.
                        file_account.add(val_str)
            
            file_stats.append({
                "filename": file.filename,
                "mobiles": len(file_mobile),
                "accounts": len(file_account),
                "upis": len(file_upi)
            })
            
            # Intersection Logic
            if first_file:
                common_mobile = file_mobile
                common_account = file_account
                common_upi = file_upi
                first_file = False
            else:
                common_mobile = common_mobile.intersection(file_mobile)
                common_account = common_account.intersection(file_account)
                common_upi = common_upi.intersection(file_upi)
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis Failed: {str(e)}")

    return {
        "common_numbers": list(common_mobile),
        "common_accounts": list(common_account),
        "common_upis": list(common_upi),
        "counts": {
            "mobile": len(common_mobile),
            "account": len(common_account),
            "upi": len(common_upi)
        },
        "file_stats": file_stats,
        "message": "Analysis Complete"
    }
