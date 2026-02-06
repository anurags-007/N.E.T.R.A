import pandas as pd
import io

def parse_cdr(file_content: bytes, file_ext: str):
    """
    Parses CDR file (CSV/Excel) and returns analysis stats.
    Assumes standard columns often found in CDRs (Source, Destination, Duration, DateTime).
    In a real system, this would need robust column mapping logic.
    """
    try:
        if "csv" in file_ext.lower():
            df = pd.read_csv(io.BytesIO(file_content))
        else:
            df = pd.read_excel(io.BytesIO(file_content))
        
        # Normalize headers (demo: lowercase)
        df.columns = [c.lower().strip() for c in df.columns]
        
        # Identify key columns (simple keyword matching)
        col_map = {}
        for c in df.columns:
            if "date" in c or "time" in c:
                col_map['datetime'] = c
            elif "source" in c or "caller" in c or "origin" in c or "from" in c:
                col_map['source'] = c
            elif "dest" in c or "callee" in c or "term" in c or "to" in c:
                col_map['destination'] = c
            elif "dur" in c or "sec" in c:
                col_map['duration'] = c
            elif "imei" in c:
                col_map['imei'] = c
        
        # Check if we found minimal cols
        if 'source' not in col_map or 'destination' not in col_map:
            return {"error": "Could not identify Source/Destination columns. Please ensure CSV has headers like 'Source Number', 'Destination Number'."}
        
        # 1. Total Calls
        total_calls = len(df)
        
        # 2. Top Contacted Numbers (Outgoing)
        top_contacts = df[col_map['destination']].value_counts().head(10).to_dict()
        
        # 3. Top Incoming Numbers (if source varies)
        top_incoming = df[col_map['source']].value_counts().head(10).to_dict()
        
        # 4. Duration Analysis
        total_duration = 0
        if 'duration' in col_map:
            total_duration = df[col_map['duration']].sum()
        
        # 5. Time Analysis (Need valid datetime col)
        hourly_distribution = {}
        if 'datetime' in col_map:
            try:
                df['dt_parsed'] = pd.to_datetime(df[col_map['datetime']])
                hourly_distribution = df['dt_parsed'].dt.hour.value_counts().sort_index().to_dict()
            except Exception as e:
                # Often fmt issues
                pass
        
        return {
            "total_calls": int(total_calls),
            "total_duration": int(total_duration),
            "top_contacts_outgoing": top_contacts,
            "top_contacts_incoming": top_incoming,
            "hourly_stats": hourly_distribution,
            "column_mapping_used": col_map
        }
        
    except Exception as e:
        return {"error": f"Failed to parse file: {str(e)}"}
