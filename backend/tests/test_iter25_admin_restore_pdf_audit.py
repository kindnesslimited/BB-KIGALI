"""iter25 backend tests — admin dashboard, revenue series, subs report, audit log, PDF receipt.

Reuses the same helper pattern as prior iters (OTP -> testCode -> verify -> Bearer).
"""
import os
import re
import time
import pytest
import requests
from datetime import datetime, timezone

BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"
ADMIN_PHONE = "+250794230137"
USER_PHONE = "+250788123456"


# ---------- helpers ----------
def _otp_token(phone: str) -> str:
    r = requests.post(f"{BASE}/auth/otp/start", json={"phone": phone}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    code = body.get("testCode")
    if not code:
        # fetch from DB (only needed for WhatsApp path; admin phone returns testCode)
        from pymongo import MongoClient
        m = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db_name = os.environ.get("DB_NAME", "test_database")
        row = m[db_name].otp_challenges.find_one({"phone": phone}) or \
              m[db_name].otp_challenges.find_one({"phone": phone.lstrip("+")})
        assert row and row.get("code"), f"no OTP challenge for {phone}: {row}"
        code = row["code"]
    v = requests.post(f"{BASE}/auth/otp/verify", json={"phone": phone, "code": code}, timeout=30)
    assert v.status_code == 200, v.text
    return v.json()["accessToken"]


@pytest.fixture(scope="module")
def admin_hdr():
    return {"Authorization": f"Bearer {_otp_token(ADMIN_PHONE)}"}


@pytest.fixture(scope="module")
def user_hdr():
    return {"Authorization": f"Bearer {_otp_token(USER_PHONE)}"}


# ==================== DASHBOARD ====================
class TestDashboard:
    def test_dashboard_admin(self, admin_hdr):
        r = requests.get(f"{BASE}/admin/analytics/dashboard", headers=admin_hdr, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("users", "subscriptions", "revenue", "transactions", "content"):
            assert k in d, f"missing key {k}: {list(d.keys())}"
        for k in ("total", "admins", "newThisWeek"):
            assert k in d["users"], f"users missing {k}"
        for k in ("active", "expired"):
            assert k in d["subscriptions"]
        for k in ("allTime", "last30Days", "last7Days", "today"):
            assert k in d["revenue"]
        for k in ("successThisMonth", "pending", "failedThisMonth", "breakdownByMethod"):
            assert k in d["transactions"]
        for k in ("shows", "programs", "news"):
            assert k in d["content"]

    def test_dashboard_forbidden_for_user(self, user_hdr):
        r = requests.get(f"{BASE}/admin/analytics/dashboard", headers=user_hdr, timeout=30)
        assert r.status_code == 403, r.text


# ==================== REVENUE SERIES ====================
class TestRevenueSeries:
    def test_day(self, admin_hdr):
        r = requests.get(f"{BASE}/admin/analytics/revenue?granularity=day&days=30", headers=admin_hdr, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        for row in rows:
            for k in ("period", "currency", "count", "amount"):
                assert k in row, f"row missing {k}: {row}"

    def test_week(self, admin_hdr):
        r = requests.get(f"{BASE}/admin/analytics/revenue?granularity=week&days=90", headers=admin_hdr, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_month(self, admin_hdr):
        r = requests.get(f"{BASE}/admin/analytics/revenue?granularity=month&days=180", headers=admin_hdr, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ==================== SUBSCRIPTIONS REPORT ====================
class TestSubsReport:
    def _check_rows(self, rows):
        now_iso = datetime.now(timezone.utc).isoformat()
        for u in rows:
            for k in ("id", "displayName", "phone", "tier", "subscriptionExpiresAt", "status"):
                assert k in u, f"missing {k}: {u.keys()}"
            assert u["tier"] in ("basic", "premium"), u["tier"]
        return now_iso

    def test_active(self, admin_hdr):
        r = requests.get(f"{BASE}/admin/analytics/subscriptions?status=active", headers=admin_hdr, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        now_iso = self._check_rows(rows)
        for u in rows:
            assert (u.get("subscriptionExpiresAt") or "") > now_iso, f"expired in active: {u}"
            assert u["status"] == "active"

    def test_expired(self, admin_hdr):
        r = requests.get(f"{BASE}/admin/analytics/subscriptions?status=expired", headers=admin_hdr, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        now_iso = self._check_rows(rows)
        for u in rows:
            assert (u.get("subscriptionExpiresAt") or "") <= now_iso
            assert u["status"] == "expired"

    def test_all(self, admin_hdr):
        r = requests.get(f"{BASE}/admin/analytics/subscriptions?status=all", headers=admin_hdr, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ==================== AUDIT LOG ====================
class TestAuditLog:
    def test_news_create_delete_audit(self, admin_hdr):
        start_iso = datetime.now(timezone.utc).isoformat()
        payload = {"title": f"AUDIT_TEST_{int(time.time())}", "body": "audit smoke", "type": "text"}
        c = requests.post(f"{BASE}/admin/news", json=payload, headers=admin_hdr, timeout=30)
        assert c.status_code in (200, 201), c.text
        nid = c.json().get("id")
        assert nid
        d = requests.delete(f"{BASE}/admin/news/{nid}", headers=admin_hdr, timeout=30)
        assert d.status_code in (200, 204), d.text
        # Poll audit log briefly
        found_create = found_delete = False
        for _ in range(3):
            r = requests.get(f"{BASE}/admin/audit-log?limit=50", headers=admin_hdr, timeout=30)
            assert r.status_code == 200
            docs = r.json()
            for row in docs:
                if row.get("targetId") == nid or (row.get("metadata") or {}).get("newsId") == nid:
                    if row["action"] == "news.create":
                        found_create = row
                    if row["action"] == "news.delete":
                        found_delete = row
            if found_create and found_delete:
                break
            time.sleep(1)
        assert found_create, f"news.create audit entry not found for id={nid}"
        assert found_delete, f"news.delete audit entry not found for id={nid}"
        for row in (found_create, found_delete):
            assert row.get("actorPhone") or row.get("actorName"), row
            assert row.get("targetType") == "news"
            assert row.get("createdAt") >= start_iso[:16]  # loose ISO compare

    def test_audit_filter_action(self, admin_hdr):
        r = requests.get(f"{BASE}/admin/audit-log?action=news.delete&limit=10", headers=admin_hdr, timeout=30)
        assert r.status_code == 200
        for row in r.json():
            assert row["action"] == "news.delete", row

    def test_audit_forbidden_for_user(self, user_hdr):
        r = requests.get(f"{BASE}/admin/audit-log", headers=user_hdr, timeout=30)
        assert r.status_code == 403


# ==================== USER UPDATE/DELETE AUDIT ====================
class TestUserAudit:
    def test_user_update_delete_audit(self, admin_hdr):
        # Bulk-invite a throwaway user
        phone = f"+2507{int(time.time()) % 100000000:08d}"
        inv = requests.post(
            f"{BASE}/admin/users/bulk-invite",
            json={"users": [{"phone": phone, "displayName": "TEST_audit"}]},
            headers=admin_hdr, timeout=30,
        )
        assert inv.status_code == 200, inv.text
        # Find the created user id via listing
        listr = requests.get(f"{BASE}/admin/users?limit=500", headers=admin_hdr, timeout=30)
        assert listr.status_code == 200
        users = listr.json()
        # users may be dict-wrapped
        rows = users if isinstance(users, list) else users.get("items") or users.get("users") or []
        target = next((u for u in rows if (u.get("phone") or "").lstrip("+") == phone.lstrip("+")), None)
        assert target, f"seeded user {phone} not in /admin/users listing"
        uid = target["id"]
        # PATCH displayName
        p = requests.patch(f"{BASE}/admin/users/{uid}", json={"displayName": "AuditTest"}, headers=admin_hdr, timeout=30)
        assert p.status_code == 200, p.text
        # DELETE
        d = requests.delete(f"{BASE}/admin/users/{uid}", headers=admin_hdr, timeout=30)
        assert d.status_code in (200, 204), d.text
        # Look for audit rows
        found_update = found_delete = False
        for _ in range(3):
            r = requests.get(f"{BASE}/admin/audit-log?limit=200", headers=admin_hdr, timeout=30)
            for row in r.json():
                if row.get("targetId") == uid:
                    if row["action"] == "user.update":
                        found_update = True
                    if row["action"] == "user.delete":
                        found_delete = True
            if found_update and found_delete:
                break
            time.sleep(1)
        assert found_update, f"user.update audit missing for {uid}"
        assert found_delete, f"user.delete audit missing for {uid}"


# ==================== PDF RECEIPT ====================
class TestReceiptPdf:
    def test_receipt_current_month(self, user_hdr):
        r = requests.get(f"{BASE}/billing/receipt", headers=user_hdr, timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("application/pdf"), r.headers
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        assert re.search(r'filename="bb-fm-receipt-\d{4}-\d{2}\.pdf"', cd), cd
        assert r.content[:5] == b"%PDF-", r.content[:20]

    def test_receipt_specific_month(self, user_hdr):
        r = requests.get(f"{BASE}/billing/receipt?year=2026&month=6", headers=user_hdr, timeout=60)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"
        cd = r.headers.get("content-disposition", "")
        assert 'bb-fm-receipt-2026-06.pdf' in cd, cd

    def test_receipt_requires_auth(self):
        r = requests.get(f"{BASE}/billing/receipt", timeout=30)
        assert r.status_code == 401, r.status_code


# ==================== REGRESSIONS ====================
class TestRegressions:
    def test_stripe_subscribe_non_admin_forbidden(self, user_hdr):
        r = requests.post(f"{BASE}/billing/subscribe",
                          json={"plan": "premium_monthly", "method": "stripe"},
                          headers=user_hdr, timeout=30)
        assert r.status_code == 403

    def test_stripe_checkout_live(self, user_hdr):
        r = requests.post(f"{BASE}/billing/stripe/create-checkout",
                          json={"purchase_type": "subscription", "plan": "premium_monthly",
                                "originUrl": "https://radio-vod-platform.preview.emergentagent.com"},
                          headers=user_hdr, timeout=45)
        assert r.status_code == 200, r.text
        body = r.json()
        url = body.get("url") or body.get("checkoutUrl") or ""
        sid = body.get("sessionId") or ""
        assert sid.startswith("cs_live_"), sid
        assert "cs_live_" in url, url
        # session-status paid:false on new session
        s = requests.get(f"{BASE}/billing/stripe/session-status/{sid}", headers=user_hdr, timeout=30)
        assert s.status_code == 200
        assert s.json().get("paid") in (False, None)

    def test_momo_initiate_and_guard(self, user_hdr):
        r = requests.post(f"{BASE}/billing/momo/initiate",
                          json={"phone": "250794230137", "plan": "basic_monthly"},
                          headers=user_hdr, timeout=45)
        assert r.status_code in (200, 202), r.text
        # Safety guard: merchant number must not be debited
        g = requests.post(f"{BASE}/billing/momo/initiate",
                          json={"phone": "250798875274", "plan": "basic_monthly"},
                          headers=user_hdr, timeout=30)
        assert g.status_code == 400, g.text

    def test_youtube_sync(self, admin_hdr):
        r = requests.post(f"{BASE}/admin/youtube/sync", headers=admin_hdr, timeout=120)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        chans = body.get("channels") or []
        handles = " ".join(str(c) for c in chans).lower()
        assert "bbkigalifm" in handles, chans
        assert "bbsportsbar" in handles, chans
