"""Tamper-evident hash-chained AuditLog helpers."""
import hashlib
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from backend import models

GENESIS_HASH = "0" * 64


def _compute_entry_hash(
    prev_hash: str,
    user_id: Optional[int],
    action: str,
    details: Optional[str],
    ts_iso: str,
) -> str:
    payload = f"{prev_hash}|{user_id}|{action}|{details or ''}|{ts_iso}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def record_audit_log(
    db: Session,
    user_id: Optional[int],
    action: str,
    details: Optional[str] = None,
    commit: bool = False,
) -> models.AuditLog:
    """Append a hash-chained AuditLog entry linked to the previous entry's SHA-256."""
    last = db.query(models.AuditLog).order_by(models.AuditLog.id.desc()).first()
    prev_hash = last.entry_hash if (last and last.entry_hash) else GENESIS_HASH
    ts = datetime.now(timezone.utc).replace(microsecond=0)
    entry_hash = _compute_entry_hash(prev_hash, user_id, action, details, ts.isoformat())

    entry = models.AuditLog(
        user_id=user_id,
        action=action,
        details=details,
        timestamp=ts,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    return entry


def verify_audit_chain(db: Session) -> dict:
    """Verify hash-chain integrity across all AuditLog rows."""
    rows = db.query(models.AuditLog).order_by(models.AuditLog.id.asc()).all()
    expected_prev = GENESIS_HASH
    for row in rows:
        if not row.prev_hash or not row.entry_hash:
            return {"valid": False, "broken_id": row.id, "reason": "Missing hash fields"}
        if row.prev_hash != expected_prev:
            return {"valid": False, "broken_id": row.id, "reason": "Previous hash mismatch"}
        ts_val = row.timestamp
        if ts_val is not None and ts_val.tzinfo is None:
            ts_val = ts_val.replace(tzinfo=timezone.utc)
        ts_iso = ts_val.replace(microsecond=0).isoformat() if ts_val else ""
        recomputed = _compute_entry_hash(
            row.prev_hash, row.user_id, row.action, row.details, ts_iso
        )
        if recomputed != row.entry_hash:
            return {"valid": False, "broken_id": row.id, "reason": "Entry hash tampered"}
        expected_prev = row.entry_hash
    return {"valid": True, "checked_entries": len(rows)}
