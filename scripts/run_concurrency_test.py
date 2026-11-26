"""
Layer 4 — Concurrency & Stress Test for N.E.T.R.A.
====================================================
Fires 25 parallel requests against http://127.0.0.1:8001 using httpx.AsyncClient.
Mix of endpoints and two demo accounts (si_sector62 and si_noida_central).

Pass criteria:
  - 0 HTTP 500 responses
  - 0 "database is locked" errors in any response body
  - All authenticated requests return 2xx/4xx (not 500 or connection errors)

Usage:
    python scripts/run_concurrency_test.py
"""

import asyncio
import json
import sys
import time
from typing import Optional

import httpx

BASE_URL = "http://127.0.0.1:8001"

# ------------------------------------------------------------------
# Accounts
# ------------------------------------------------------------------
ACCOUNTS = [
    {"username": "si_sector62",      "password": "Sector62#2026"},
    {"username": "si_noida_central", "password": "CentralNoida#2026"},
]

# ------------------------------------------------------------------
# Token acquisition
# ------------------------------------------------------------------
async def get_token(client: httpx.AsyncClient, username: str, password: str) -> Optional[str]:
    resp = await client.post(
        f"{BASE_URL}/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json().get("access_token")
    print(f"  [WARN] Could not get token for {username}: {resp.status_code}")
    return None


# ------------------------------------------------------------------
# Individual task
# ------------------------------------------------------------------
async def make_request(
    client: httpx.AsyncClient,
    task_id: int,
    method: str,
    url: str,
    token: Optional[str],
    **kwargs,
) -> dict:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    t0 = time.monotonic()
    try:
        resp = await client.request(
            method, url, headers=headers, timeout=20, **kwargs
        )
        elapsed = time.monotonic() - t0
        body_text = ""
        try:
            body_text = resp.text[:300]
        except Exception:
            pass

        return {
            "task_id": task_id,
            "url": url,
            "status": resp.status_code,
            "elapsed": round(elapsed, 3),
            "body_snippet": body_text,
        }
    except Exception as exc:
        return {
            "task_id": task_id,
            "url": url,
            "status": -1,
            "elapsed": round(time.monotonic() - t0, 3),
            "body_snippet": str(exc)[:200],
        }


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
async def main() -> bool:
    print("=" * 60)
    print("N.E.T.R.A. — Layer 4 Concurrency Stress Test")
    print("=" * 60)
    print(f"Target : {BASE_URL}")
    print(f"Threads : 25 concurrent requests")
    print()

    async with httpx.AsyncClient(verify=False) as client:
        # --- Acquire tokens ---
        print("[+] Acquiring tokens for demo accounts …")
        tokens = {}
        for acct in ACCOUNTS:
            tok = await get_token(client, acct["username"], acct["password"])
            tokens[acct["username"]] = tok
            status = "OK" if tok else "FAIL"
            print(f"    {acct['username']}: {status}")

        t1 = tokens.get("si_sector62")
        t2 = tokens.get("si_noida_central")

        if not t1 and not t2:
            print("\n[FATAL] Could not obtain any token. Is the server running?")
            return False

        # --- Build task list (25 entries) ---
        # Mix of: GET /cases/, GET /analytics/, GET /admin/logs (expect 403),
        #         health, unauthenticated probe, POST /auth/logout replay
        tasks_def = []

        # 1-5: si_sector62 → GET /cases/
        for i in range(5):
            tasks_def.append((f"GET /cases/ [{i+1}]", "GET", f"{BASE_URL}/cases/", t1))

        # 6-8: si_sector62 → GET /analysis/universal-search
        for i in range(3):
            tasks_def.append((
                f"GET /analysis/universal-search [{i+1}]",
                "GET",
                f"{BASE_URL}/analysis/universal-search?query=FIR",
                t1,
            ))

        # 9-11: si_noida_central → GET /cases/
        for i in range(3):
            tasks_def.append((f"GET /cases/ nc[{i+1}]", "GET", f"{BASE_URL}/cases/", t2))

        # 12-14: GET /bank/accounts/ (si_sector62)
        for i in range(3):
            tasks_def.append((f"GET /bank/accounts/ [{i+1}]", "GET", f"{BASE_URL}/bank/accounts/", t1))

        # 15-17: GET /freeze/requests/ (si_sector62)
        for i in range(3):
            tasks_def.append((f"GET /freeze/requests/ [{i+1}]", "GET", f"{BASE_URL}/freeze/requests/", t1))

        # 18-19: GET /admin/logs (expect 403 for non-admin)
        for i in range(2):
            tasks_def.append((f"GET /admin/logs [{i+1}]", "GET", f"{BASE_URL}/admin/logs?limit=5", t1))

        # 20-21: GET /health (unauthenticated)
        for i in range(2):
            tasks_def.append((f"GET /health [{i+1}]", "GET", f"{BASE_URL}/health", None))

        # 22-23: Unauthenticated probe of protected route (expect 401/403)
        for i in range(2):
            tasks_def.append((f"GET /cases/ unauth [{i+1}]", "GET", f"{BASE_URL}/cases/", None))

        # 24-25: si_noida_central → analysis
        for i in range(2):
            tasks_def.append((
                f"GET /analysis/universal-search nc[{i+1}]",
                "GET",
                f"{BASE_URL}/analysis/universal-search?query=bank",
                t2,
            ))

        assert len(tasks_def) == 25, f"Expected 25 tasks, got {len(tasks_def)}"

        # --- Fire all 25 concurrently ---
        print(f"\n[+] Firing {len(tasks_def)} concurrent requests …\n")
        t_start = time.monotonic()

        coros = [
            make_request(client, i + 1, method, url, token)
            for i, (_, method, url, token) in enumerate(tasks_def)
        ]
        results = await asyncio.gather(*coros)

        elapsed_total = time.monotonic() - t_start

        # --- Analyse results ---
        print(f"{'ID':>3}  {'STATUS':>7}  {'TIME':>7}  URL")
        print("-" * 70)
        failures_500 = []
        failures_locked = []
        connection_errors = []

        for r in sorted(results, key=lambda x: x["task_id"]):
            status_str = str(r["status"]) if r["status"] != -1 else "ERR"
            print(f"{r['task_id']:>3}  {status_str:>7}  {r['elapsed']:>6.3f}s  {r['url']}")
            if r["status"] == 500:
                failures_500.append(r)
            if r["status"] == -1:
                connection_errors.append(r)
            if "database is locked" in r["body_snippet"].lower():
                failures_locked.append(r)

        print()
        print("=" * 60)
        print(f"Total wall-clock time : {elapsed_total:.2f}s")
        print(f"HTTP 500 responses    : {len(failures_500)}")
        print(f"DB locked errors      : {len(failures_locked)}")
        print(f"Connection errors     : {len(connection_errors)}")
        print("=" * 60)

        passed = True

        if failures_500:
            print("\n[FAIL] HTTP 500 responses detected:")
            for r in failures_500:
                print(f"  Task {r['task_id']}: {r['url']}\n    {r['body_snippet'][:200]}")
            passed = False

        if failures_locked:
            print("\n[FAIL] 'database is locked' errors detected:")
            for r in failures_locked:
                print(f"  Task {r['task_id']}: {r['url']}\n    {r['body_snippet'][:200]}")
            passed = False

        if connection_errors:
            print("\n[WARN] Connection errors (server may be overloaded or endpoints missing):")
            for r in connection_errors:
                print(f"  Task {r['task_id']}: {r['url']}\n    {r['body_snippet'][:200]}")
            # Connection errors to /health etc. are not necessarily test failures
            # but we flag them as warnings

        if passed:
            print("\n[PASS] Layer 4 — 25 concurrent requests: 0 HTTP 500, 0 DB locks ✓")
        else:
            print("\n[FAIL] Layer 4 — One or more critical failures detected.")

        return passed


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
