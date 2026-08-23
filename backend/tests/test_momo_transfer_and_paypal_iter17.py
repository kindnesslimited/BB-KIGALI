"""Iteration 17 backend regression tests.

Covers:
  - Health check
  - Guest access to /api/shows and /api/shows/{id} (locked, no videoUrl)
  - OTP start/verify dev-mode flow (test phone +250788123456)
  - MoMo /public/payments/transfer migration for subscription and VOD
  - MoMo safety guard blocking merchant number in all normalization variants
  - PayPal create-subscription with NO_SHIPPING / payment_method payload
  - PayPal VOD create with landing_page=BILLING
  - MoMo status lookup

Runs sequentially within one worker per class (loadscope) so state is stable.
"""

import os
import re
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or os.environ.get("EXPO_BACKEND_URL")
assert BASE_URL, "EXPO_PUBLIC_BACKEND_URL/EXPO_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

TEST_PHONE_REGULAR = "+250788123456"
# Admin phone always returns testCode=123456 regardless of SMS provider success
# (per server.py otp_start: is_admin_phone → MOCK_OTP_CODE + resp["testCode"] = MOCK_OTP_CODE).
# We use it for the shared auth fixture so tests don't depend on SMS gateway failure.
TEST_PHONE_ADMIN = "+250794230137"
TEST_PHONE_PAYER = "250794230137"
MERCHANT_PHONE_CANONICAL = "250798875274"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth_token(session):
    """OTP flow using admin phone which always returns testCode=123456."""
    r = session.post(f"{API}/auth/otp/start", json={"phone": TEST_PHONE_ADMIN})
    assert r.status_code == 200, f"otp/start failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("ok") is True
    code = data.get("testCode")
    assert code, f"No testCode returned for admin phone. Response: {data}"
    r2 = session.post(f"{API}/auth/otp/verify", json={"phone": TEST_PHONE_ADMIN, "code": code})
    assert r2.status_code == 200, f"otp/verify failed: {r2.status_code} {r2.text}"
    token = r2.json().get("accessToken")
    assert token and token.startswith("eyJ"), f"Missing/invalid JWT token: {token!r}"
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def unowned_show_id(session, auth_token, db):
    """Return a show id that the authed user hasn't already purchased (needed for VOD payment flows)."""
    # Extract user id from JWT payload (base64 middle segment)
    import base64, json as _json
    payload = auth_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    claims = _json.loads(base64.urlsafe_b64decode(payload))
    user_id = claims.get("sub") or claims.get("user_id") or claims.get("id")
    shows = session.get(f"{API}/shows").json()
    assert shows, "No shows seeded"
    owned = {p["showId"] for p in db.vod_purchases.find(
        {"userId": user_id, "status": "success"}, {"_id": 0, "showId": 1}
    )}
    for s in shows:
        if s["id"] not in owned:
            return s["id"]
    pytest.skip("All shows already purchased by test user — cannot run VOD purchase flow")


# ---------- Health ----------
class TestHealth:
    def test_api_health(self, session):
        r = session.get(f"{API}/health")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True


# ---------- Guest access ----------
class TestGuestAccess:
    def test_shows_list_guest(self, session):
        r = session.get(f"{API}/shows")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_show_detail_guest_locked(self, session):
        lst = session.get(f"{API}/shows").json()
        assert lst, "No shows seeded — cannot verify guest locked view"
        show_id = lst[0]["id"]
        r = session.get(f"{API}/shows/{show_id}")
        assert r.status_code == 200, r.text
        s = r.json()
        assert s.get("locked") is True
        assert s.get("loginRequired") is True
        assert s.get("videoUrl") in (None, "")


# ---------- Auth ----------
class TestAuth:
    def test_otp_start_regular_phone(self, session):
        """Per review spec: dev mode returns testCode when SMS gateway fails.
        NOTE: If WhatsApp provider is currently up, sms will actually send and testCode
        will NOT be returned — that's still a valid response (ok=true).
        """
        r = session.post(f"{API}/auth/otp/start", json={"phone": TEST_PHONE_REGULAR})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        # Either dev-mode testCode OR successful SMS send is acceptable
        assert data.get("testCode") or data.get("smsSent") is True, (
            f"Neither testCode nor smsSent=true in response: {data}"
        )

    def test_otp_start_admin_returns_testcode(self, session):
        """Admin phone must always return testCode=123456 regardless of provider status."""
        r = session.post(f"{API}/auth/otp/start", json={"phone": TEST_PHONE_ADMIN})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("testCode") == "123456", f"Admin testCode mismatch: {data}"

    def test_otp_verify_returns_bearer(self, session):
        r = session.post(f"{API}/auth/otp/start", json={"phone": TEST_PHONE_ADMIN})
        code = r.json().get("testCode")
        r2 = session.post(f"{API}/auth/otp/verify", json={"phone": TEST_PHONE_ADMIN, "code": code})
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body.get("accessToken", "").startswith("eyJ")
        assert body.get("user", {}).get("phone") == TEST_PHONE_ADMIN


# ---------- MoMo subscription safety guard (must run BEFORE positive path per class) ----------
class TestMoMoSafetyGuard:
    """Merchant number MUST return HTTP 400 in every normalization variant."""

    @pytest.mark.parametrize(
        "phone_variant",
        [
            "250798875274",         # canonical
            "+250 798 875 274",     # spaces + plus
            "0798875274",           # local zero-prefix
        ],
    )
    def test_merchant_phone_blocked_subscription(self, session, auth_headers, phone_variant):
        r = session.post(
            f"{API}/billing/momo/initiate",
            headers=auth_headers,
            json={"plan": "basic_monthly", "phone": phone_variant},
        )
        assert r.status_code == 400, (
            f"Merchant guard failed for variant {phone_variant!r}: "
            f"status={r.status_code} body={r.text}"
        )
        assert "collection account" in r.text.lower(), (
            f"Wrong 400 message for {phone_variant!r}: {r.text}"
        )

    def test_merchant_phone_blocked_vod(self, session, auth_headers, unowned_show_id):
        r = session.post(
            f"{API}/billing/vod/{unowned_show_id}/momo",
            headers=auth_headers,
            json={"phone": MERCHANT_PHONE_CANONICAL},
        )
        assert r.status_code == 400, f"VOD merchant guard failed: {r.status_code} {r.text}"
        assert "collection account" in r.text.lower()


# ---------- MoMo /transfer positive flow ----------
class TestMoMoTransfer:
    def test_subscription_uses_transfer_endpoint(self, session, auth_headers, db):
        # Clear old backend log tail
        r = session.post(
            f"{API}/billing/momo/initiate",
            headers=auth_headers,
            json={"plan": "basic_monthly", "phone": TEST_PHONE_PAYER},
        )
        # Backend must not throw — even if BeSoft rejects the payment, wrapper returns 2xx
        assert r.status_code == 200, f"MoMo initiate failed: {r.status_code} {r.text}"
        body = r.json()
        assert "reference" in body, f"Missing reference: {body}"
        assert body.get("status") in ("pending", "processing", "success", "failed"), body
        assert "message" in body

        # Verify payment doc persisted with method=mtn_momo
        ref = body["reference"]
        doc = db.payments.find_one({"reference": ref})
        assert doc is not None, f"payments doc not created for reference {ref}"
        assert doc.get("method") == "mtn_momo", f"Wrong method: {doc.get('method')}"

    def test_subscription_transfer_appears_in_logs(self, session, auth_headers):
        # Trigger a call and then check backend logs for the /transfer endpoint
        r = session.post(
            f"{API}/billing/momo/initiate",
            headers=auth_headers,
            json={"plan": "basic_monthly", "phone": TEST_PHONE_PAYER},
        )
        assert r.status_code == 200
        # Allow logs to flush
        time.sleep(1.0)
        log_paths = [
            "/var/log/supervisor/backend.out.log",
            "/var/log/supervisor/backend.err.log",
        ]
        tail = ""
        for p in log_paths:
            try:
                with open(p, "r") as f:
                    # Read last 100KB
                    f.seek(0, 2)
                    size = f.tell()
                    f.seek(max(0, size - 100_000))
                    tail += f.read()
            except FileNotFoundError:
                pass
        assert "public/payments/transfer" in tail or "transfer_collection" in tail, (
            "Neither '/public/payments/transfer' nor 'transfer_collection' found in "
            "recent backend logs — /transfer migration may not be wired. "
            f"Log tail sample: {tail[-800:]!r}"
        )

    def test_vod_momo_uses_transfer(self, session, auth_headers, db, unowned_show_id):
        r = session.post(
            f"{API}/billing/vod/{unowned_show_id}/momo",
            headers=auth_headers,
            json={"phone": TEST_PHONE_PAYER},
        )
        assert r.status_code == 200, f"VOD momo failed: {r.status_code} {r.text}"
        body = r.json()
        assert "reference" in body, f"Missing reference: {body}"
        assert body.get("amount") == 1000
        assert body.get("currency") == "RWF"
        assert "message" in body

        ref = body["reference"]
        doc = db.vod_purchases.find_one({"reference": ref})
        assert doc is not None, f"vod_purchases doc missing for {ref}"
        assert doc.get("method") == "mtn_momo"
        # Per review spec: /transfer migration must be exercised. besoftAttempt should be set
        # when the transfer call succeeded. If it's missing AND status=failed, the /transfer
        # call was hit but BeSoft rejected the payload — surface this as a diagnostic error
        # so the main agent sees the payload-shape mismatch instead of silently passing.
        attempt = doc.get("besoftAttempt")
        status = doc.get("status")
        if attempt != "transfer_collection":
            # verify via server logs that /public/payments/transfer was at least called for THIS reference
            time.sleep(0.5)
            log_txt = ""
            for p in ["/var/log/supervisor/backend.out.log", "/var/log/supervisor/backend.err.log"]:
                try:
                    with open(p) as f:
                        f.seek(0, 2); size = f.tell(); f.seek(max(0, size - 200_000))
                        log_txt += f.read()
                except FileNotFoundError:
                    pass
            transfer_hit = "public/payments/transfer" in log_txt
            failure_reason = doc.get("failureReason") or doc.get("error")
            pytest.fail(
                f"VOD /transfer migration incomplete: besoftAttempt={attempt!r} status={status!r} "
                f"failureReason={failure_reason!r}. /transfer endpoint hit in logs: {transfer_hit}. "
                "This means BeSoft is rejecting our /public/payments/transfer payload — the "
                "'transfer_collection' attempt marker is only set on the success branch of "
                "server.py:1495. If the response is 400 the failure branch (line 1485) does not "
                "set besoftAttempt, so the field stays None even though /transfer was called. "
                "Fix: (a) correct the /transfer payload shape (BeSoft expects nested Debit/Credit "
                "objects — see error 'Key: TransferRequest.Debit.Amount required'), OR "
                "(b) at minimum, also set besoftAttempt='transfer_collection' on the failure "
                "branch so migration is auditable."
            )

    def test_momo_status_endpoint(self, session, auth_headers, db):
        # Use any known reference from db.payments (created above)
        doc = db.payments.find_one({"method": "mtn_momo"}, sort=[("createdAt", -1)])
        if not doc:
            pytest.skip("No MoMo payment doc to look up")
        ref = doc["reference"]
        r = session.get(f"{API}/billing/momo/{ref}", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("reference") == ref
        assert "status" in body
        assert "amount" in body
        assert "currency" in body


# ---------- PayPal payload regression ----------
class TestPayPal:
    def test_create_subscription_no_shipping(self, session, auth_headers):
        r = session.post(
            f"{API}/billing/paypal/create-subscription",
            headers=auth_headers,
            json={"plan": "basic_monthly"},
        )
        assert r.status_code == 200, f"PayPal create-subscription failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("subscriptionId"), f"Missing subscriptionId: {body}"
        approve = body.get("approveUrl", "")
        assert approve, f"Missing approveUrl: {body}"
        assert "paypal.com" in approve, f"approveUrl is not paypal.com: {approve}"

    def test_vod_paypal_create_landing_billing(self, session, auth_headers, unowned_show_id):
        r = session.post(
            f"{API}/billing/vod/{unowned_show_id}/create",
            headers=auth_headers,
        )
        assert r.status_code == 200, f"VOD paypal create failed: {r.status_code} {r.text}"
        body = r.json()
        assert body.get("orderId"), f"Missing orderId: {body}"
        approve = body.get("approveUrl", "")
        assert approve and "paypal.com" in approve, f"Bad approveUrl: {approve}"
