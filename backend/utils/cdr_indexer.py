"""Index parsed CDR MSISDN & IMEI entries into CdrIndexEntry for fast Universal Search."""
from collections import Counter, defaultdict
from sqlalchemy.orm import Session

from backend import models
from backend.utils.cdr_parser import _read_tabular_rows


def index_cdr_bytes(
    db: Session,
    case_id: int,
    evidence_id: int,
    file_content: bytes,
    filename: str,
) -> int:
    """Extract unique MSISDN/IMEI pairs and call counts from CDR CSV/XLSX into CdrIndexEntry."""
    lower = (filename or "").lower()
    if not lower.endswith((".csv", ".xlsx", ".xls")):
        return 0

    # Idempotent: skip if already indexed for this evidence_id
    existing = db.query(models.CdrIndexEntry.id).filter(
        models.CdrIndexEntry.evidence_id == evidence_id
    ).first()
    if existing:
        return 0

    try:
        headers, rows = _read_tabular_rows(file_content, filename)
    except Exception:
        return 0

    if not headers or not rows:
        return 0

    norm_to_orig = {h.lower().strip(): h for h in headers}

    # Format 1: Subscriber Summary CDR (e.g. real_telecom_cdr.csv)
    if "phone number" in norm_to_orig and ("day calls" in norm_to_orig or "day mins" in norm_to_orig):
        phone_col = norm_to_orig["phone number"]
        call_cols = [norm_to_orig[k] for k in ("day calls", "eve calls", "night calls", "intl calls") if k in norm_to_orig]
        counts: Counter = Counter()
        for row in rows:
            ph = (row.get(phone_col) or "").strip()
            if not ph:
                continue
            total = 0
            for c in call_cols:
                try:
                    total += int(float(row.get(c) or 0))
                except ValueError:
                    pass
            counts[ph] += max(1, total)

        entries = [
            models.CdrIndexEntry(
                case_id=case_id,
                evidence_id=evidence_id,
                msisdn=ph,
                imei=None,
                call_count=cnt,
            )
            for ph, cnt in counts.items()
        ]
        if entries:
            db.bulk_save_objects(entries)
            db.commit()
        return len(entries)

    # Format 2: DoT 22-field / Event-level CDR
    src_col = next((norm_to_orig[k] for k in ("a_party", "calling_no", "calling_party", "source", "caller", "from") if k in norm_to_orig), None)
    dst_col = next((norm_to_orig[k] for k in ("b_party", "called_no", "called_party", "destination", "callee", "to") if k in norm_to_orig), None)
    imei_col = next((norm_to_orig[k] for k in ("imei", "imei_no", "a_imei", "handset_imei") if k in norm_to_orig), None)
    if not src_col and not dst_col and not imei_col:
        return 0

    pair_counts: Counter = Counter()
    for row in rows:
        src = (row.get(src_col) or "").strip() if src_col else ""
        dst = (row.get(dst_col) or "").strip() if dst_col else ""
        imei = (row.get(imei_col) or "").strip() if imei_col else ""
        if src:
            pair_counts[(src, imei or None)] += 1
        if dst:
            pair_counts[(dst, None)] += 1

    entries = [
        models.CdrIndexEntry(
            case_id=case_id,
            evidence_id=evidence_id,
            msisdn=msisdn,
            imei=imei,
            call_count=cnt,
        )
        for (msisdn, imei), cnt in pair_counts.items()
    ]
    if entries:
        db.bulk_save_objects(entries)
        db.commit()
    return len(entries)
