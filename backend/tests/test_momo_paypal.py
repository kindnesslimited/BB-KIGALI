"""BB FM Kigali - LIVE integration tests: MoMo (BeSoft debit-credit) + PayPal."""
import os
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
TEST_PHONE_AUTH = "+250788199137"
TEST_PHONE_PAYER = "250794230137"  # real MTN Rwanda number provided by user
OTP = "123456"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def token(api):
    api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": TEST_PHONE_AUTH})
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": TEST_PHONE_AUTH, "code": OTP})
    assert r.status_code == 200, r.text
    return r.json()["accessToken"]


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


# ---- MoMo: /public/payments/debit-credit ----
def test_momo_initiate_hits_debit_credit_endpoint(api, token, mongo):
    """Verify our backend calls BeSoft's /debit-credit endpoint with correct payload.
    The MTN provider may return HTTP_400 (payer account inactive) — that's expected.
    We validate that BeSoft accepted the request and returned besoftTxId + kind=debit_credit."""
    headers = {"Authorization": f"Bearer {token}"}
    r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                 json={"plan": "basic_monthly", "phone": TEST_PHONE_PAYER}, headers=headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "reference" in j and j["reference"].startswith("bbfm-")
    assert j.get("besoftTxId"), "besoftTxId missing — provider did not accept request"
    assert j["status"] in ("pending", "processing", "success", "failed")
    assert j["amount"] == 1000 and j["currency"] == "RWF"

    # Verify Mongo record shows debit-credit metadata (proves correct endpoint used)
    time.sleep(0.5)
    doc = mongo.payments.find_one({"reference": j["reference"]})
    assert doc is not None
    bp = doc.get("besoftPayload") or {}
    debit = bp.get("debit") or {}
    meta = debit.get("metadata") or {}
    assert meta.get("kind") == "debit_credit", f"metadata.kind != debit_credit: {meta}"
    credits = meta.get("credits") or []
    assert len(credits) == 1, f"expected 1 credit, got {len(credits)}"
    assert credits[0].get("payee_identifier") == "250798875272"
    assert credits[0].get("amount") == 1000


def test_momo_status_polling(api, token):
    """Reference + status polling should work regardless of debit success."""
    headers = {"Authorization": f"Bearer {token}"}
    r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                 json={"plan": "basic_monthly", "phone": TEST_PHONE_PAYER}, headers=headers)
    assert r.status_code == 200
    ref = r.json()["reference"]
    poll = api.get(f"{BASE_URL}/api/billing/momo/{ref}", headers=headers)
    assert poll.status_code == 200
    pj = poll.json()
    assert pj["reference"] == ref
    assert "status" in pj
    assert pj["status"] in ("pending", "processing", "success", "failed")


# ---- Regression: other integrations ----
def test_otp_verify_regression(api):
    api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": TEST_PHONE_AUTH})
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": TEST_PHONE_AUTH, "code": OTP})
    assert r.status_code == 200
    assert r.json().get("accessToken")


def test_now_playing_youtube_id(api):
    r = api.get(f"{BASE_URL}/api/radio/now-playing")
    assert r.status_code == 200
    assert r.json().get("youtubeVideoId") == "wPD77ygQKfo"


def test_shows_at_least_six(api):
    r = api.get(f"{BASE_URL}/api/shows")
    assert r.status_code == 200
    assert len(r.json()) >= 6


def test_paypal_create_subscription_live(api, token):
    headers = {"Authorization": f"Bearer {token}"}
    r = api.post(f"{BASE_URL}/api/billing/paypal/create-subscription",
                 json={"plan": "basic_monthly"}, headers=headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "approveUrl" in j and "paypal.com" in j["approveUrl"]
    assert j.get("subscriptionId")
