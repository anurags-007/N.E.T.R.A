from datetime import datetime, timedelta

def calculate_entity_risk(investigation_data):
    """
    Calculates a Risk Score (0-100) and Priority Level for an entity 
    based on investigation data.
    
    Formula adapted for UP Police Context:
    Risk = (0.4 * RepeatOffense) + (0.3 * MoneyFlow) + (0.3 * Network)
    """
    
    stats = investigation_data.get("summary_stats", {})
    cases = investigation_data.get("cases", [])
    financials = investigation_data.get("financial_entities", [])
    timeline = investigation_data.get("transaction_timeline", [])
    
    # 1. Repeat Offense Score (40%)
    # - More than 1 case = repeat offender
    # - 5+ cases = max score
    case_count = stats.get("total_cases", 0)
    repeat_score = min(case_count / 5, 1.0) * 100
    
    # 2. Money Flow Score (30%)
    # - Threshold: ₹1,00,000 (Generic threshold for high priority in local stations)
    total_amount = stats.get("total_transaction_amount", 0.0)
    money_score = min(total_amount / 100000, 1.0) * 100
    
    # 3. Network/Connectivity Score (30%)
    # - Measures how "connected" this entity is (number of evidences/requests)
    evidence_count = stats.get("total_evidence_files", 0)
    request_count = stats.get("total_telecom_requests", 0)
    connections = evidence_count + request_count
    network_score = min(connections / 5, 1.0) * 100
    
    # --- FINAL WEIGHTED SCORE ---
    final_score = (0.4 * repeat_score) + (0.3 * money_score) + (0.3 * network_score)
    final_score = round(final_score, 1)
    
    # --- Determine Risk Level & Priority ---
    if final_score >= 75:
        risk_level = "CRITICAL"
        priority = "IMMEDIATE ACTION"
        color_code = "danger" # Red
    elif final_score >= 40:
        risk_level = "HIGH"
        priority = "PRIORITY INVESTIGATION"
        color_code = "warning" # Yellow
    else:
        risk_level = "MODERATE"
        priority = "ROUTINE CHECK"
        color_code = "success" # Green (or Blue)
        
    # --- Generate Intelligence Tags (Explainability) ---
    tags = []
    
    if case_count > 1:
        tags.append(f"🔁 SERIAL OFFENDER ({case_count} Cases)")
    
    if total_amount > 200000:
        tags.append("💰 HIGH VALUE FRAUD")
    elif total_amount > 0 and total_amount < 10000:
        tags.append("📉 LOW VALUE / POSSIBLE MULE")
        
    # Check for mule behavior (High inflows, minimal holding - simplified Logic)
    # If linked to financial fraud case but amount is high
    if "financial" in [c.get("case_category", "") for c in cases]:
         tags.append("🏦 BANK FRAUD LINK")
         
    # Inter-district check (using Police Station names)
    stations = set(c.get("police_station", "").lower() for c in cases if c.get("police_station"))
    if len(stations) > 1:
        tags.append(f"🌐 INTER-DISTRICT GANG ({len(stations)} Stations)")
        
    # Recency Check
    recent_activity = False
    if timeline:
        last_event = timeline[0].get("event_timestamp") # Assuming sorted desc
        if last_event:
            last_date = datetime.fromisoformat(last_event)
            if (datetime.now() - last_date).days < 7:
                 tags.append("🔥 RECENTLY ACTIVE (Last 7 Days)")
                 recent_activity = True

    return {
        "score": final_score,
        "level": risk_level,
        "priority": priority,
        "color": color_code,
        "tags": tags,
        "breakdown": {
            "repeat_offense_score": round(repeat_score, 1),
            "money_flow_score": round(money_score, 1),
            "network_score": round(network_score, 1)
        }
    }
