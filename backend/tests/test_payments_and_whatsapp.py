"""Backend tests for the new Payment History Dashboard admin endpoints,
plus verification that the rotated WhatsApp API token actually delivers
(nostress.vip returns code=110) and that /api/auth/otp/start records
delivery attempts in db.sms_deliveries.

Run:
    python -m pytest backend/tests/test_payments_and_whatsapp.py -v -o addopts=''
"""
import os
import time
import uuid
import asyncio
import httpx
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = (
    os.environ.get("EXPO_PUBLIC_BACKEND_URL")
    or os.environ.get("EXPO_BACKEND_URL")
    or "https://radio-vod-platform.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_PHONE = "+250798875272"
NON_ADMIN_PHONE = f"+2507990{int(time.time()) % 100000:05d}"  # unique-ish per run
MOCK_OTP = "123456"


# ---------------------- Fixtures ----------------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/otp/start", json={"phone": ADMIN_PHONE})
    assert r.status_code == 200, f"otp/start failed: {r.status_code} {r.text}"
    code = r.json().get("testCode") or MOCK_OTP
    r = requests.post(f"{API}/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code})
    assert r.status_code == 200, f"otp/verify failed: {r.status_code} {r.text}"
    return r.json()["accessToken"]


@pytest.fixture(scope="module")
def user_token():
    """Get a non-admin user token. Since WhatsApp now delivers real messages,
    the /auth/otp/start endpoint no longer returns testCode for non-admins.
    Insert a known OTP challenge directly into mongo so we can verify."""
    phone = f"+250788{int(time.time()) % 1000000:06d}"
    known_code = "999888"

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")

    async def _seed():
        from datetime import datetime, timezone
        client = AsyncIOMotorClient(mongo_url)
        try:
            await client[db_name].otp_challenges.update_one(
                {"phone": phone},
                {"$set": {
                    "phone": phone,
                    "code": known_code,
                    "attempts": 0,
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                }},
                upsert=True,
            )
        finally:
            client.close()

    asyncio.get_event_loop().run_until_complete(_seed())
    r = requests.post(f"{API}/auth/otp/verify", json={"phone": phone, "code": known_code})
    assert r.status_code == 200, f"otp verify failed: {r.text}"
    return r.json()["accessToken"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------- Admin: Payments Summary ----------------------
class TestAdminPaymentsSummary:
    def test_summary_shape(self, auth_headers):
        r = requests.get(f"{API}/admin/payments/summary?days=30", headers=auth_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["windowDays"] == 30
        for k in ("success", "pending", "failed", "count"):
            assert k in j["totals"]
            assert isinstance(j["totals"][k], int), f"{k} is {type(j['totals'][k])}"
        assert isinstance(j["byMethod"], list)
        assert isinstance(j["totalRevenue"], dict)
        assert isinstance(j["byDay"], list)

    def test_summary_days_1(self, auth_headers):
        r = requests.get(f"{API}/admin/payments/summary?days=1", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["windowDays"] == 1

    def test_summary_days_90(self, auth_headers):
        r = requests.get(f"{API}/admin/payments/summary?days=90", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["windowDays"] == 90

    def test_summary_days_365(self, auth_headers):
        r = requests.get(f"{API}/admin/payments/summary?days=365", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["windowDays"] == 365

    def test_summary_by_method_shape(self, auth_headers):
        r = requests.get(f"{API}/admin/payments/summary?days=365", headers=auth_headers)
        assert r.status_code == 200
        for m in r.json()["byMethod"]:
            assert "method" in m and "count" in m and "revenue" in m
            assert isinstance(m["revenue"], dict)


# ---------------------- Admin: Payments List ----------------------
class TestAdminPaymentsList:
    def test_list_returns_array(self, auth_headers):
        r = requests.get(f"{API}/admin/payments?days=30&limit=5", headers=auth_headers)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list)
        for p in arr:
            for k in ("id", "method", "status", "amount", "currency", "createdAt"):
                assert k in p, f"payment missing '{k}': {p}"

    def test_list_filter_method_stripe(self, auth_headers):
        r = requests.get(f"{API}/admin/payments?method=stripe&days=365&limit=200", headers=auth_headers)
        assert r.status_code == 200
        for p in r.json():
            assert p["method"] == "stripe"

    def test_list_filter_status_success(self, auth_headers):
        r = requests.get(f"{API}/admin/payments?status=success&days=365&limit=200", headers=auth_headers)
        assert r.status_code == 200
        for p in r.json():
            assert p["status"] == "success"

    def test_list_combined_filter(self, auth_headers):
        r = requests.get(
            f"{API}/admin/payments?method=stripe&status=success&days=90&limit=200",
            headers=auth_headers,
        )
        assert r.status_code == 200
        for p in r.json():
            assert p["method"] == "stripe" and p["status"] == "success"

    def test_list_desc_sorted(self, auth_headers):
        r = requests.get(f"{API}/admin/payments?days=365&limit=50", headers=auth_headers)
        assert r.status_code == 200
        items = r.json()
        if len(items) >= 2:
            times = [p["createdAt"] for p in items]
            assert times == sorted(times, reverse=True), "not sorted desc by createdAt"

    def test_list_enrichment_fields_present(self, auth_headers):
        """userPhone/userEmail/userName keys always present (even if None)."""
        r = requests.get(f"{API}/admin/payments?days=365&limit=10", headers=auth_headers)
        assert r.status_code == 200
        for p in r.json():
            assert "userPhone" in p
            assert "userEmail" in p
            assert "userName" in p


# ---------------------- Auth boundaries ----------------------
class TestAdminPaymentsAuth:
    def test_no_bearer_returns_401(self):
        r = requests.get(f"{API}/admin/payments?days=30")
        assert r.status_code in (401, 403), r.status_code

    def test_no_bearer_summary_returns_401(self):
        r = requests.get(f"{API}/admin/payments/summary?days=30")
        assert r.status_code in (401, 403), r.status_code

    def test_non_admin_returns_403(self, user_token):
        r = requests.get(
            f"{API}/admin/payments?days=30",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert r.status_code == 403, r.status_code

    def test_non_admin_summary_returns_403(self, user_token):
        r = requests.get(
            f"{API}/admin/payments/summary?days=30",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert r.status_code == 403


# ---------------------- WhatsApp OTP delivery ----------------------
class TestWhatsAppOtpDelivery:
    def test_admin_phone_returns_testcode(self):
        """Admin phones get MOCK OTP shortcut (no real SMS sent)."""
        r = requests.post(f"{API}/auth/otp/start", json={"phone": ADMIN_PHONE})
        assert r.status_code == 200
        j = r.json()
        assert j.get("testCode") == MOCK_OTP

    def test_direct_whatsapp_api_accepts_token(self):
        """The rotated token must be accepted by nostress.vip (code=110)."""
        url = "https://whatsapp.nostress.vip/api_com.php"
        r = requests.post(url, json={
            "action": "send",
            "auth": "f8237d8959e03355010bb85cc3dc46a46fb31110",
            "tel": "250799000999",
            "msg": "BB Kigali test — please ignore",
        }, headers={"Content-Type": "application/json"}, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert str(j.get("code")) == "110", f"expected code=110 (accepted), got {j}"

    def test_non_admin_otp_attempts_delivery_and_records(self):
        """Non-admin OTP request should attempt SMS chain and record every attempt."""
        r = requests.post(f"{API}/auth/otp/start", json={"phone": NON_ADMIN_PHONE})
        assert r.status_code == 200, r.text
        j = r.json()
        # dev fallback OR real delivery — either is acceptable
        assert "smsSent" in j
        # Give backend a moment
        time.sleep(1.0)

        # Query mongo directly
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "test_database")

        async def _fetch():
            client = AsyncIOMotorClient(mongo_url)
            try:
                dst = NON_ADMIN_PHONE.lstrip("+").strip()
                docs = await client[db_name].sms_deliveries.find(
                    {"destination": {"$in": [NON_ADMIN_PHONE, dst]}},
                    {"_id": 0},
                ).sort("createdAt", -1).to_list(20)
                return docs
            finally:
                client.close()

        docs = asyncio.get_event_loop().run_until_complete(_fetch())
        assert len(docs) >= 1, f"no sms_deliveries recorded for {NON_ADMIN_PHONE}"
        providers = {d["provider"] for d in docs}
        # Must include at least one of the configured providers
        assert providers & {"route_mobile", "whatsapp"}, f"unexpected providers: {providers}"

        # At least one should have success=True (whatsapp should deliver with the valid token)
        any_success = any(d.get("success") for d in docs)
        # If not success, print for debugging but do not hard-fail because whatsapp API may
        # rate-limit or be down. Still we assert at least one attempted whatsapp record.
        assert any(d["provider"] == "whatsapp" for d in docs), (
            f"no whatsapp attempt recorded — provider chain not exercised: {docs}"
        )
        if not any_success:
            # Surface details for report
            print("WARNING: no successful delivery — attempts:")
            for d in docs:
                print(f"  {d['provider']}: success={d.get('success')} resp={d.get('response', '')[:120]}")
        else:
            # Verify at least one success came from whatsapp
            wa_ok = [d for d in docs if d["provider"] == "whatsapp" and d.get("success")]
            assert wa_ok, "success flag set but not on whatsapp"

    def test_sms_provider_order_env(self):
        """Provider order should be simplified to route_mobile,whatsapp."""
        # Query via admin endpoint
        r = requests.post(f"{API}/auth/otp/start", json={"phone": ADMIN_PHONE})
        assert r.status_code == 200
        code = r.json().get("testCode") or MOCK_OTP
        r = requests.post(f"{API}/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code})
        token = r.json()["accessToken"]
        r = requests.get(f"{API}/admin/sms/providers", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        j = r.json()
        assert j["order"] == ["route_mobile", "whatsapp"], f"expected [route_mobile,whatsapp], got {j['order']}"
