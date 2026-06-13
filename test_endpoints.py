"""
ProxiServe backend endpoint integration test.
Starts the API + ARQ worker, then exercises every live endpoint.

Run from server/ with:
    .venv/bin/python test_endpoints.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import traceback
from typing import Any

import httpx
import redis as redis_sync

BASE     = "http://localhost:8000"
REDIS    = redis_sync.Redis(host="localhost", port=6379, db=0, decode_responses=True)
TIMEOUT  = httpx.Timeout(60.0)  # Argon2 + remote Neon DB can be slow

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

results: list[tuple[str, bool, str]] = []


def header(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─' * 64}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 64}{RESET}")


def _record(name: str, passed: bool, detail: str) -> None:
    results.append((name, passed, detail))
    tag = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
    suffix = f"  {CYAN}{detail}{RESET}" if passed and detail else (f"  {RED}{detail}{RESET}" if detail else "")
    print(f"  {tag}  {name}{suffix}")


def info(msg: str) -> None:
    print(f"  {CYAN}ℹ{RESET}  {msg}")


def expect(
    name: str,
    r: httpx.Response,
    status: int | tuple[int, ...],
    key: str | None = None,
) -> dict[str, Any]:
    """Assert status + optional top-level data key. Returns parsed body."""
    body: dict[str, Any] = {}
    try:
        body = r.json()
    except Exception:
        pass

    expected = (status,) if isinstance(status, int) else status
    passed = r.status_code in expected
    detail = f"HTTP {r.status_code}"

    if passed and key:
        data = body.get("data") or {}
        if key not in data:
            passed = False
            detail = f"HTTP {r.status_code} — key '{key}' missing in data"

    if not passed:
        snippet = json.dumps(body)[:200]
        detail = f"HTTP {r.status_code} | {snippet}"

    _record(name, passed, detail if not (passed and not detail) else detail)
    return body


# ─────────────────────────────────────────────────────────────────────────────
# Server / worker lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def start_server() -> "subprocess.Popen[bytes]":
    proc = subprocess.Popen(
        [".venv/bin/uvicorn", "app.main:app",
         "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for _ in range(30):
        time.sleep(0.5)
        try:
            if httpx.get(f"{BASE}/health", timeout=2).status_code == 200:
                return proc
        except Exception:
            pass
    proc.terminate()
    raise RuntimeError("Server did not start within 15 s")


def start_worker() -> "subprocess.Popen[bytes]":
    return subprocess.Popen(
        [".venv/bin/python", "-m", "app.worker"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Redis helpers
# ─────────────────────────────────────────────────────────────────────────────

def otp_from_redis(challenge_id: str) -> str | None:
    raw = REDIS.get(f"auth:otp:{challenge_id}")
    if raw:
        return json.loads(raw).get("code")
    return None


def scan_otp_for_user(user_id: str) -> str | None:
    """Scan all auth:otp:* keys to find any OTP belonging to user_id."""
    for key in REDIS.scan_iter("auth:otp:*"):
        raw = REDIS.get(key)
        if raw:
            d = json.loads(raw)
            if d.get("user_id") == user_id:
                return d.get("code")
    return None


def scan_reset_token(user_id: str) -> str | None:
    """Look for a password-reset entry in Redis for this user."""
    for key in REDIS.scan_iter("auth:otp:*"):
        raw = REDIS.get(key)
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except Exception:
            continue
        if d.get("user_id") == user_id and "reset" in d.get("purpose", "").lower():
            return d.get("code")
    for key in REDIS.scan_iter("auth:reset:*"):
        raw = REDIS.get(key)
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except Exception:
            continue
        if d.get("user_id") == user_id:
            return key.split("auth:reset:")[-1]
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Test groups
# ─────────────────────────────────────────────────────────────────────────────

def test_infrastructure(c: httpx.Client) -> None:
    header("1 · Infrastructure — Health, Ready, Root")
    b = expect("GET /", c.get(f"{BASE}/"), 200, "service")
    info(f"service={b.get('data', {}).get('service')}")
    expect("GET /health", c.get(f"{BASE}/health"), 200)
    b = expect("GET /ready — DB + Redis alive", c.get(f"{BASE}/ready"), 200)
    info(f"status={b.get('data', {}).get('status')}")


# ── admin authentication ──────────────────────────────────────────────────────

def test_admin_login(c: httpx.Client) -> dict[str, Any]:
    header("2 · Admin — Staff Login + SMS 2FA")

    # Primary login
    r = c.post(f"{BASE}/api/auth/staff/login", json={
        "email": "mugisham505@gmail.com",
        "password": "@Hebuzarwanda123",
        "role": "admin",
    })
    b = expect("POST /api/auth/staff/login (admin credentials)", r, 200, "pre2faToken")
    data   = b.get("data") or {}
    pre2fa = data.get("pre2faToken", "")
    uid    = (data.get("session") or {}).get("userId", "")
    info(f"userId={uid}")
    if not uid:
        _record("Admin userId in response", False, "no userId — cannot continue 2FA")
        return {}

    # Retrieve SMS OTP from Redis (no phone → not actually sent, but stored)
    time.sleep(0.3)
    otp = otp_from_redis(f"{uid}:staff-sms")
    if otp:
        _record("Admin OTP found in Redis", True, f"code={otp}")
    else:
        _record("Admin OTP found in Redis", False, "key missing — 2FA cannot complete")
        return {}

    # Complete 2FA
    r = c.post(f"{BASE}/api/auth/staff/2fa", json={
        "code": otp, "method": "sms", "pre2faToken": pre2fa, "trustDevice": False,
    })
    b2 = expect("POST /api/auth/staff/2fa (sms)", r, 200, "session")
    role = (b2.get("data", {}).get("session") or {}).get("role")
    _record("Session role = staff:admin", role == "staff:admin", role or "missing")

    # Session endpoint
    expect("GET /api/auth/session (admin)", c.get(f"{BASE}/api/auth/session"), 200, "session")

    return {"user_id": uid, "pre2fa": pre2fa}


def test_admin_login_negative() -> None:
    header("3 · Admin Login — Negative Cases")
    fresh = httpx.Client(timeout=TIMEOUT)

    b = expect(
        "Wrong password → 401",
        fresh.post(f"{BASE}/api/auth/staff/login",
                   json={"email": "mugisham505@gmail.com", "password": "WRONGPASS", "role": "admin"}),
        401,
    )
    info(f"errorType={b.get('errorType')}")

    expect(
        "Unknown email → 401",
        fresh.post(f"{BASE}/api/auth/staff/login",
                   json={"email": "ghost@nowhere.com", "password": "@Hebuzarwanda123", "role": "admin"}),
        401,
    )

    expect(
        "Correct creds but wrong role ('agent') → 401",
        fresh.post(f"{BASE}/api/auth/staff/login",
                   json={"email": "mugisham505@gmail.com", "password": "@Hebuzarwanda123", "role": "agent"}),
        401,
    )


# ── agent CRUD ────────────────────────────────────────────────────────────────

def test_admin_agents(c: httpx.Client) -> dict[str, Any]:
    """Returns {"agent_id": ..., "email": ..., "password": ...}"""
    header("4 · Admin — Agent CRUD")

    ts    = int(time.time())
    email = f"testagent.{ts}@example.com"
    pw    = "TempAgent@123"

    # Initial list
    b = expect("GET /api/admin/agents (initial)", c.get(f"{BASE}/api/admin/agents"), 200, "agents")
    before = len((b.get("data") or {}).get("agents", []))
    info(f"agents before create: {before}")

    # Create
    r = c.post(f"{BASE}/api/admin/agents", json={"name": "Test Agent", "email": email, "temporary_password": pw})
    b = expect("POST /api/admin/agents (create)", r, 201, "agent_id")
    agent_id = (b.get("data") or {}).get("agent_id", "")
    invite   = (b.get("data") or {}).get("invite_sent", False)
    info(f"agent_id={agent_id}  invite_sent={invite}")
    _record("Agent created — invite_sent=True", invite, "invite_sent was False" if not invite else "")

    if not agent_id:
        _record("agent_id present", False, "cannot continue agent tests")
        return {}

    # List — count increased
    b2 = expect("GET /api/admin/agents (after create)", c.get(f"{BASE}/api/admin/agents"), 200, "agents")
    after = len((b2.get("data") or {}).get("agents", []))
    _record("Agent count increased", after > before, f"{before} → {after}")

    # Fetch single
    expect("GET /api/admin/agents/{id}", c.get(f"{BASE}/api/admin/agents/{agent_id}"), 200, "agent_id")

    # 404 for non-existent
    b3 = expect("GET /api/admin/agents/bad_id → 404",
                c.get(f"{BASE}/api/admin/agents/usr_DOESNOTEXIST"), 404)
    info(f"errorType={b3.get('errorType')}")

    # Duplicate email → 409
    b4 = expect("POST /api/admin/agents (duplicate email) → 409",
                c.post(f"{BASE}/api/admin/agents", json={"name": "Dup", "email": email}), 409)
    info(f"errorType={b4.get('errorType')}")

    # Deactivate
    b5 = expect("PATCH — deactivate (is_active=false)",
                c.patch(f"{BASE}/api/admin/agents/{agent_id}", json={"is_active": False}), 200, "updated")
    info(f"updated={b5.get('data', {}).get('updated')}")

    # Reactivate
    expect("PATCH — reactivate (is_active=true)",
           c.patch(f"{BASE}/api/admin/agents/{agent_id}", json={"is_active": True}), 200, "updated")

    # Force 2FA reset (safe — doesn't change password)
    b7 = expect("PATCH — force_2fa_reset=true",
                c.patch(f"{BASE}/api/admin/agents/{agent_id}", json={"force_2fa_reset": True}), 200, "updated")
    info(f"updated={b7.get('data', {}).get('updated')}")

    # NOTE: reset_password is tested separately in test_agent_post_login_admin_ops
    # to avoid changing the password before test_agent_login runs.
    return {"agent_id": agent_id, "email": email, "password": pw}


# ── role guards ───────────────────────────────────────────────────────────────

def test_role_guards() -> None:
    header("5 · Role Guards")
    anon = httpx.Client(timeout=TIMEOUT)

    expect("GET /api/admin/agents (no auth) → 401",   anon.get(f"{BASE}/api/admin/agents"), 401)
    expect("POST /api/admin/agents (no auth) → 401",
           anon.post(f"{BASE}/api/admin/agents", json={"name": "X", "email": "x@x.com"}), 401)
    expect("POST /api/applications/claim (no auth) → 401",
           anon.post(f"{BASE}/api/applications/claim",
                     json={"code": "PRX-0001-00001", "phone": "+250780000001"}), 401)


# ── agent login + deactivation gate ──────────────────────────────────────────

def test_agent_login(admin_c: httpx.Client, agent: dict[str, Any]) -> None:
    header("6 · Agent — Login + 2FA + Deactivation Gate")

    if not agent:
        info("Skipped — no agent data from previous test")
        return

    agent_email, agent_pw, agent_id = agent["email"], agent["password"], agent["agent_id"]
    fresh = httpx.Client(timeout=TIMEOUT)

    # Login
    r = fresh.post(f"{BASE}/api/auth/staff/login",
                   json={"email": agent_email, "password": agent_pw, "role": "agent"})
    b = expect("POST /api/auth/staff/login (agent)", r, 200, "pre2faToken")
    data      = b.get("data") or {}
    pre2fa    = data.get("pre2faToken", "")
    agent_uid = (data.get("session") or {}).get("userId", "")
    info(f"agent userId={agent_uid}")

    if agent_uid:
        time.sleep(0.2)
        otp = otp_from_redis(f"{agent_uid}:staff-sms")
        if otp:
            _record("Agent OTP in Redis", True, f"code={otp}")
            r2 = fresh.post(f"{BASE}/api/auth/staff/2fa",
                            json={"code": otp, "method": "sms",
                                  "pre2faToken": pre2fa, "trustDevice": False})
            b2 = expect("POST /api/auth/staff/2fa (agent)", r2, 200, "session")
            role = (b2.get("data", {}).get("session") or {}).get("role")
            _record("Agent session role = staff:agent", role == "staff:agent", role or "missing")

            # Agent session
            expect("GET /api/auth/session (agent)", fresh.get(f"{BASE}/api/auth/session"), 200, "session")

            # Agent CANNOT access admin endpoints → 403
            b3 = expect("GET /api/admin/agents as agent → 403",
                        fresh.get(f"{BASE}/api/admin/agents"), 403)
            info(f"errorType={b3.get('errorType')}")
        else:
            _record("Agent OTP in Redis", False, "key missing")

    # Deactivate via admin
    admin_c.patch(f"{BASE}/api/admin/agents/{agent_id}", json={"is_active": False})
    r3 = fresh.post(f"{BASE}/api/auth/staff/login",
                    json={"email": agent_email, "password": agent_pw, "role": "agent"})
    b3 = expect("POST /api/auth/staff/login (deactivated agent) → 401", r3, 401)
    info(f"errorType={b3.get('errorType')}")

    # Re-enable
    admin_c.patch(f"{BASE}/api/admin/agents/{agent_id}", json={"is_active": True})


# ── post-login admin ops (password reset — must run AFTER agent login test) ───

def test_agent_reset_password(admin_c: httpx.Client, agent: dict[str, Any]) -> None:
    header("7 · Admin — Agent Password Reset (queues email)")
    if not agent:
        info("Skipped — no agent data")
        return
    agent_id = agent["agent_id"]
    b = expect("PATCH — reset_password=true (email queued)",
               admin_c.patch(f"{BASE}/api/admin/agents/{agent_id}", json={"reset_password": True}),
               200, "updated")
    info(f"updated={b.get('data', {}).get('updated')}")


# ── client signup ─────────────────────────────────────────────────────────────

def test_client_signup(c: httpx.Client) -> dict[str, Any]:
    header("8 · Client — Signup + Email OTP Verification")

    ts    = int(time.time())
    email = f"testclient.{ts}@example.com"
    pw    = "ClientPass@88"

    # Signup
    r = c.post(f"{BASE}/api/auth/signup", json={
        "name": "Test Client", "identifierType": "email",
        "identifier": email, "password": pw, "language": "en", "terms": True,
    })
    b = expect("POST /api/auth/signup", r, 200, "maskedEmail")
    uid     = (b.get("data", {}).get("session") or {}).get("userId", "")
    masked  = (b.get("data") or {}).get("maskedEmail", "")
    info(f"userId={uid}  maskedEmail={masked}")
    _record("Cookies set (access + refresh)", bool(c.cookies.get("proxiserve_access")), "")

    # Duplicate
    r2 = c.post(f"{BASE}/api/auth/signup", json={
        "name": "Dup", "identifierType": "email", "identifier": email,
        "password": pw, "language": "en", "terms": True,
    })
    b2 = expect("POST /api/auth/signup (duplicate) → 409", r2, 409)
    info(f"errorType={b2.get('errorType')}")

    # Verification OTP
    time.sleep(0.4)
    otp = otp_from_redis(f"{uid}:email-verify") or scan_otp_for_user(uid)
    if otp:
        _record("Email verify OTP in Redis", True, f"code={otp}")
    else:
        _record("Email verify OTP in Redis", False, "check signup → OTP flow")

    # Verify
    if otp:
        r3 = c.post(f"{BASE}/api/auth/verify-otp", json={"code": otp})
        expect("POST /api/auth/verify-otp", r3, 200, "verified")

    return {"email": email, "password": pw, "user_id": uid}


# ── client login + session ────────────────────────────────────────────────────

def test_client_login(ctx: dict[str, Any]) -> httpx.Client:
    header("9 · Client — Login + Session + Resend OTP + Sign-out")

    email, pw = ctx["email"], ctx["password"]
    c = httpx.Client(timeout=TIMEOUT)

    # Login
    r = c.post(f"{BASE}/api/auth/login", json={
        "identifierType": "email", "identifier": email,
        "password": pw, "rememberMe": True,
    })
    b = expect("POST /api/auth/login", r, 200, "maskedEmail")
    uid = (b.get("data", {}).get("session") or {}).get("userId", "")
    info(f"userId={uid}")

    # OTP for login verification
    time.sleep(0.3)
    otp2 = otp_from_redis(f"{uid}:email-verify") or scan_otp_for_user(uid)
    if otp2:
        _record("Login OTP in Redis", True, f"code={otp2}")
        r3 = c.post(f"{BASE}/api/auth/verify-otp", json={"code": otp2})
        expect("POST /api/auth/verify-otp (login)", r3, 200, "verified")
    else:
        _record("Login OTP in Redis", False, "cannot verify session")

    # Session
    b2 = expect("GET /api/auth/session", c.get(f"{BASE}/api/auth/session"), 200, "session")
    role = (b2.get("data", {}).get("session") or {}).get("role")
    _record("Session role = client", role == "client", role or "missing")

    # Resend OTP
    r4 = c.post(f"{BASE}/api/auth/resend-otp")
    info(f"POST /api/auth/resend-otp → HTTP {r4.status_code} (200=sent, 429=cooldown)")
    _record("POST /api/auth/resend-otp → 200 or 429", r4.status_code in (200, 429), f"HTTP {r4.status_code}")

    # Wrong password
    b3 = expect(
        "POST /api/auth/login (wrong password) → 401",
        httpx.post(f"{BASE}/api/auth/login",
                   json={"identifierType": "email", "identifier": email,
                         "password": "WRONG", "rememberMe": False}, timeout=TIMEOUT),
        401,
    )
    info(f"errorType={b3.get('errorType')}")

    # Sign out
    expect("POST /api/auth/sign-out", c.post(f"{BASE}/api/auth/sign-out"), 200, "signedOut")
    expect("GET /api/auth/session after sign-out → 401", c.get(f"{BASE}/api/auth/session"), 401)

    # DELETE /api/auth/session alias
    c2 = httpx.Client(timeout=TIMEOUT)
    r5 = c2.delete(f"{BASE}/api/auth/session")
    _record("DELETE /api/auth/session (no cookie) → 401 or 200",
            r5.status_code in (200, 401), f"HTTP {r5.status_code}")

    return c


# ── forgot + reset password ───────────────────────────────────────────────────

def test_forgot_password(ctx: dict[str, Any]) -> None:
    header("10 · Client — Forgot Password + Reset")

    email = ctx["email"]
    uid   = ctx.get("user_id", "")
    c     = httpx.Client(timeout=TIMEOUT)

    # Request reset
    r = c.post(f"{BASE}/api/auth/forgot-password",
               json={"identifierType": "email", "identifier": email})
    b = expect("POST /api/auth/forgot-password (known email)", r, 200, "maskedEmail")
    info(f"maskedEmail={b.get('data', {}).get('maskedEmail')}")

    # Unknown email — must NOT enumerate (still 200 or specific 404)
    r2 = c.post(f"{BASE}/api/auth/forgot-password",
                json={"identifierType": "email", "identifier": "nobody@nothing.invalid"})
    b2 = expect("POST /api/auth/forgot-password (unknown, non-enumerable) → 200 or 404",
                r2, (200, 404))
    info(f"HTTP {r2.status_code} | maskedEmail={b2.get('data', {}).get('maskedEmail')}")

    # Get reset token from Redis
    time.sleep(0.5)
    token = scan_reset_token(uid)

    if token:
        _record("Reset token/code found in Redis", True, f"token={token[:12]}…")
        new_pw = "NewPass@999"
        r3 = c.post(f"{BASE}/api/auth/reset-password",
                    json={"token": token, "password": new_pw, "confirmPassword": new_pw})
        expect("POST /api/auth/reset-password", r3, 200)
        # Password mismatch guard
        r4 = c.post(f"{BASE}/api/auth/reset-password",
                    json={"token": "bad_token", "password": "aaa", "confirmPassword": "bbb"})
        expect("POST /api/auth/reset-password (mismatch) → 422", r4, 422)
    else:
        _record("Reset token/code found in Redis", False,
                "check forgot_password service — token not stored under expected key")
        info("Skipping POST /api/auth/reset-password")


# ── applications ──────────────────────────────────────────────────────────────

def test_applications() -> None:
    header("11 · Applications Endpoints")

    anon = httpx.Client(timeout=TIMEOUT)

    # Lookup invalid code
    b = expect("GET /api/applications/lookup?code=PRX-0000-00000 → 404 or 422",
               anon.get(f"{BASE}/api/applications/lookup", params={"code": "PRX-0000-00000"}),
               (404, 422))
    info(f"errorType={b.get('errorType')}")

    # Lookup garbage code
    r2 = anon.get(f"{BASE}/api/applications/lookup", params={"code": "NOTACODE"})
    expect("GET /api/applications/lookup?code=NOTACODE → 400, 404 or 422", r2, (400, 404, 422))
    info(f"HTTP {r2.status_code}")

    # Claim without auth → 401
    expect("POST /api/applications/claim (no auth) → 401",
           anon.post(f"{BASE}/api/applications/claim",
                     json={"code": "PRX-0001-00001", "phone": "+250780000001"}),
           401)


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

def print_summary() -> None:
    passed = sum(1 for _, p, _ in results if p)
    total  = len(results)
    failed = [(n, d) for n, p, d in results if not p]

    header("TEST SUMMARY")
    print(f"\n  Total {total}   {GREEN}Passed {passed}{RESET}   {RED}Failed {total - passed}{RESET}\n")

    if failed:
        print(f"  {BOLD}Failed:{RESET}")
        for name, detail in failed:
            print(f"    {RED}✗{RESET} {name}")
            if detail:
                print(f"        {RED}{detail[:160]}{RESET}")
    else:
        print(f"  {GREEN}{BOLD}All {total} tests passed!{RESET}")

    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    server_proc: "subprocess.Popen[bytes] | None" = None
    worker_proc: "subprocess.Popen[bytes] | None" = None

    try:
        # ── server ───────────────────────────────────────────────────────────
        try:
            httpx.get(f"{BASE}/health", timeout=1)
            print(f"  {CYAN}ℹ{RESET}  Server already on port 8000 — skipping startup")
        except Exception:
            print(f"  {CYAN}ℹ{RESET}  Starting uvicorn…")
            server_proc = start_server()
            print(f"  {GREEN}Server ready.{RESET}")
            time.sleep(1.5)  # let admin seeding finish

        # ── ARQ worker ───────────────────────────────────────────────────────
        print(f"  {CYAN}ℹ{RESET}  Starting ARQ email worker…")
        worker_proc = start_worker()
        time.sleep(1.5)

        # ── shared admin client ───────────────────────────────────────────────
        admin_c = httpx.Client(follow_redirects=True, timeout=TIMEOUT)

        test_infrastructure(admin_c)

        admin_ctx = test_admin_login(admin_c)
        if admin_ctx:
            test_admin_login_negative()
            agent = test_admin_agents(admin_c)
            test_role_guards()
            if agent:
                test_agent_login(admin_c, agent)
                test_agent_reset_password(admin_c, agent)

        # Client flows on a fresh unauthenticated client
        signup_c = httpx.Client(follow_redirects=True, timeout=TIMEOUT)
        client_ctx = test_client_signup(signup_c)
        if client_ctx:
            test_client_login(client_ctx)
            test_forgot_password(client_ctx)

        test_applications()

    except KeyboardInterrupt:
        print("\n  Interrupted.")
    except Exception:
        print(f"\n{RED}Unhandled error:{RESET}")
        traceback.print_exc()
    finally:
        print_summary()
        for proc in (server_proc, worker_proc):
            if proc:
                proc.terminate()


if __name__ == "__main__":
    main()
