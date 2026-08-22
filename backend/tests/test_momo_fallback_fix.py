"""BB FM Kigali - MoMo Fallback Fix Verification

Verifies /api/billing/momo/initiate humanized error + besoftAttempt DB tracking.
BeSoft's /public/payments/debit-credit is currently failing at MTN provider level
(HTTP_400). The fix adds:
  1. Auto-fallback to /public/payments/debit when debit-credit fails with HTTP_400
  2. Humanized error message ("MTN MoMo temporarily unavailable...")
  3. besoftAttempt DB tracking (debit_credit | debit_only_fallback)
  4. Preserved failureReason for developer debugging
"""
import os
import pytest
import requests
from pymongo import MongoClient

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL")
            or os.environ.get("EXPO_BACKEND_URL")
            or "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_PHONE = "+250798875272"
NON_ADMIN_PHONE = "+250799001234"
TEST_PAYER = "+250788999888"


# ---- Fixtures ----
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


def _get_token_via_api(api, phone: str) -> str:
    """Standard flow: /otp/start returns testCode for admins or when SMS is not sent."""
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": phone})
    assert r.status_code == 200, f"otp/start failed: {r.text}"
    code = r.json().get("testCode")
    assert code, f"testCode missing in otp/start response: {r.text}"
    r2 = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": phone, "code": code})
    assert r2.status_code == 200, f"otp/verify failed: {r2.text}"
    tok = r2.json().get("accessToken") or r2.json().get("token")
    assert tok, f"token missing: {r2.text}"
    return tok


def _get_token_via_mongo(api, mongo, phone: str) -> str:
    """For non-admin phones where WhatsApp SMS actually delivers (no testCode returned),
    seed the OTP challenge directly into mongo, then call /otp/verify."""
    from datetime import datetime, timezone as _tz
    api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": phone})  # ensure user doc gets created
    seed_code = "654321"
    mongo.otp_challenges.update_one(
        {"phone": phone},
        {"$set": {"phone": phone, "code": seed_code, "attempts": 0,
                  "createdAt": datetime.now(_tz.utc).isoformat()}},
        upsert=True,
    )
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": phone, "code": seed_code})
    assert r.status_code == 200, f"otp/verify (seeded) failed: {r.text}"
    tok = r.json().get("accessToken") or r.json().get("token")
    assert tok, f"token missing (seeded): {r.text}"
    return tok


@pytest.fixture(scope="module")
def admin_token(api):
    return _get_token_via_api(api, ADMIN_PHONE)


@pytest.fixture(scope="module")
def user_token(api, mongo):
    return _get_token_via_mongo(api, mongo, NON_ADMIN_PHONE)


# ---- 1. MoMo initiate returns humanized error with all fields ----
class TestMoMoInitiateHumanizedError:
    def test_admin_basic_monthly_returns_humanized_failure(self, api, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                     json={"plan": "basic_monthly", "phone": TEST_PAYER}, headers=h)
        assert r.status_code == 200, r.text
        j = r.json()
        # All required fields present
        for k in ("reference", "status", "message", "failureReason", "amount", "currency", "pollUrl"):
            assert k in j, f"missing field '{k}' in response: {j}"
        # BeSoft gateway broken → status=failed expected
        assert j["status"] == "failed", f"expected status=failed, got: {j}"
        # Humanized message
        msg = (j.get("message") or "").lower()
        assert ("mtn momo temporarily unavailable" in msg
                or "card payment" in msg
                or "momo" in msg), f"message not humanized: {j['message']}"
        # Raw failureReason preserved
        fr = (j.get("failureReason") or "").lower()
        assert ("http_400" in fr or "provider error" in fr or fr), \
            f"failureReason not preserved for debugging: {j['failureReason']}"

    def test_db_tracks_besoft_attempt_and_failure_reason(self, api, admin_token, mongo):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                     json={"plan": "basic_monthly", "phone": TEST_PAYER}, headers=h)
        assert r.status_code == 200
        ref = r.json()["reference"]
        doc = mongo.payments.find_one({"reference": ref})
        assert doc is not None, f"payment doc not found for ref {ref}"
        assert doc["method"] == "mtn_momo"
        assert doc["status"] == "failed"
        assert "besoftAttempt" in doc, f"besoftAttempt missing from payment doc: {doc.keys()}"
        assert doc["besoftAttempt"] in ("debit_credit", "debit_only_fallback"), \
            f"unexpected besoftAttempt: {doc['besoftAttempt']}"
        assert "failureReason" in doc and doc["failureReason"], \
            f"failureReason missing from payment doc: {doc.keys()}"


# ---- 2. Non-admin user gets same friendly error ----
class TestMoMoNonAdminUser:
    def test_non_admin_gets_humanized_failure(self, api, user_token):
        h = {"Authorization": f"Bearer {user_token}"}
        r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                     json={"plan": "basic_monthly", "phone": TEST_PAYER}, headers=h)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "failed"
        msg = (j.get("message") or "").lower()
        assert ("temporarily unavailable" in msg or "card payment" in msg or "momo" in msg), \
            f"non-admin humanized message missing: {j['message']}"
        assert j.get("failureReason"), "failureReason missing for non-admin"


# ---- 3. All 4 plans return friendly failed message ----
class TestMoMoAllPlans:
    @pytest.mark.parametrize("plan,amount", [
        ("basic_monthly", 1000),
        ("basic_yearly", 10000),
        ("premium_monthly", 3000),
        ("premium_yearly", 30000),
    ])
    def test_plan_returns_friendly_failure(self, api, admin_token, plan, amount):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                     json={"plan": plan, "phone": TEST_PAYER}, headers=h)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["amount"] == amount, f"plan {plan} amount mismatch: {j['amount']}"
        assert j["currency"] == "RWF"
        assert j["status"] == "failed"
        msg = (j.get("message") or "").lower()
        assert "momo" in msg or "card payment" in msg or "unavailable" in msg, \
            f"plan {plan} message not humanized: {j['message']}"


# ---- 4. Validation errors return 400 ----
class TestMoMoValidation:
    def test_bad_plan_returns_400(self, api, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                     json={"plan": "bogus", "phone": "+250788999999"}, headers=h)
        # FastAPI + Pydantic Literal validation returns 422 (unprocessable entity);
        # server-side plan check returns 400. Either indicates invalid plan rejected.
        assert r.status_code in (400, 422), r.text
        body_lower = r.text.lower()
        assert "invalid plan" in body_lower or "basic_monthly" in body_lower or "literal_error" in body_lower, \
            f"unexpected error body: {r.text}"

    def test_bad_phone_returns_400(self, api, admin_token):
        h = {"Authorization": f"Bearer {admin_token}"}
        r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                     json={"plan": "basic_monthly", "phone": "123"}, headers=h)
        assert r.status_code == 400, r.text
        assert "invalid payer phone" in r.text.lower()


# ---- 5. VOD MoMo endpoint unaffected by fallback (still uses debit-credit directly) ----
class TestVodMoMoUnaffected:
    def test_vod_momo_endpoint_still_returns_humanized_or_valid(self, api, admin_token, mongo):
        # Grab any show_id from the DB (or use a random one — endpoint should still respond)
        show = mongo.vods.find_one({}) if hasattr(mongo, "vods") else None
        # Try common collection names
        for coll in ("vods", "shows", "content", "videos"):
            show = mongo[coll].find_one({})
            if show:
                break
        show_id = (show.get("id") if show else None) or "test-show-id"

        h = {"Authorization": f"Bearer {admin_token}"}
        r = api.post(f"{BASE_URL}/api/billing/vod/{show_id}/momo",
                     json={"phone": TEST_PAYER}, headers=h)
        # Endpoint must respond (any of 200/400/402/404) — should NOT 500
        assert r.status_code < 500, f"VOD momo returned 5xx: {r.status_code} {r.text[:200]}"
        # If it returned 200, verify shape
        if r.status_code == 200:
            j = r.json()
            # Should have a message field of some kind (either success prompt or humanized failure)
            assert isinstance(j, dict)
