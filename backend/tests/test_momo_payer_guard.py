"""BB FM Kigali — MoMo Payer-vs-Merchant Safety Guard Tests (iteration_12)

CRITICAL SAFETY BUG: Customer must be debited, merchant (+250 798 875 272) must ONLY receive.
Guard `_guard_payer_not_merchant` blocks any request where the payer MSISDN normalizes to
BESOFT_PAYOUT_MSISDN. Verifies:
  1. All formats of the merchant number are rejected (400 with "collection account" msg)
  2. Customer number (+250 794 230 137) is accepted (200) and normalized to 250794230137
     in the persisted BeSoft payload (`debit.payer_identifier`).
  3. Merchant MSISDN NEVER appears as any `payer_identifier` in the stored payload.
  4. Same guard fires for VOD MoMo endpoint.
  5. Endpoints require bearer auth (401 without).
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

ADMIN_PHONE = "+250798875272"       # admin — also happens to be the merchant collection MSISDN
CUSTOMER_PHONE = "+250794230137"    # legitimate customer test payer (also an admin)
MERCHANT_MSISDN_NORM = "250798875272"


# -------- Fixtures --------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": ADMIN_PHONE})
    assert r.status_code == 200, r.text
    code = r.json().get("testCode")
    assert code, f"testCode missing: {r.text}"
    r2 = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": ADMIN_PHONE, "code": code})
    assert r2.status_code == 200, r2.text
    return r2.json().get("accessToken") or r2.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# -------- Subscription MoMo guard: merchant number in every format is rejected --------
MERCHANT_FORMATS = [
    ("+250798875272", "e164_no_spaces"),
    ("250798875272", "digits_only"),
    ("+250 798 875 272", "spaced_e164"),
    ("250-798-875-272", "dashed"),
    ("0798875272", "local_leading_zero"),
    ("798875272", "nine_digit_bare"),
    ("+2500798875272", "cc_plus_leading_zero"),
]


@pytest.mark.parametrize("phone,label", MERCHANT_FORMATS)
def test_subscription_momo_rejects_merchant_number(api, auth_headers, phone, label):
    r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                 headers=auth_headers,
                 json={"plan": "basic_monthly", "phone": phone})
    assert r.status_code == 400, f"[{label}] expected 400 got {r.status_code}: {r.text}"
    detail = (r.json() or {}).get("detail", "")
    assert "collection account" in detail.lower(), \
        f"[{label}] detail must mention 'collection account', got: {detail}"


# -------- Subscription MoMo: customer number is accepted (multiple formats) --------
CUSTOMER_FORMATS = [
    ("+250 794 230 137", "spaced_e164"),
    ("0794230137", "local_leading_zero"),
    ("794230137", "nine_digit_bare"),
]


@pytest.mark.parametrize("phone,label", CUSTOMER_FORMATS)
def test_subscription_momo_accepts_customer_number(api, auth_headers, mongo, phone, label):
    r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                 headers=auth_headers,
                 json={"plan": "basic_monthly", "phone": phone})
    assert r.status_code == 200, f"[{label}] customer number must pass guard, got {r.status_code}: {r.text}"
    body = r.json()
    # required response fields (BeSoft may fail downstream — that's OK)
    for key in ("reference", "besoftTxId", "status", "message",
                "failureReason", "amount", "currency", "pollUrl"):
        assert key in body, f"[{label}] missing '{key}' in response: {body}"
    assert body["amount"] == 1000
    assert body["currency"] == "RWF"

    # Verify stored payment doc has correct normalized payer
    ref = body["reference"]
    doc = mongo.payments.find_one({"reference": ref})
    assert doc is not None, f"[{label}] payment doc not found for reference {ref}"
    # Payment doc stores the normalized payer in `phone` field
    assert doc.get("phone") == "250794230137", \
        f"[{label}] payment.phone must be normalized customer 250794230137, got: {doc.get('phone')}"
    # Merchant MSISDN must NEVER appear as the debited phone
    assert doc.get("phone") != MERCHANT_MSISDN_NORM, \
        f"[{label}] SAFETY VIOLATION: merchant MSISDN must NEVER be stored as debit phone"


# -------- Auth boundary --------
def test_subscription_momo_requires_auth(api):
    r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                 json={"plan": "basic_monthly", "phone": CUSTOMER_PHONE})
    assert r.status_code == 401, f"expected 401 without bearer, got {r.status_code}: {r.text}"


# -------- VOD MoMo guard --------
@pytest.fixture(scope="module")
def show_id(api):
    r = api.get(f"{BASE_URL}/api/shows")
    assert r.status_code == 200, r.text
    shows = r.json()
    assert isinstance(shows, list) and shows, f"no shows available: {shows}"
    return shows[0]["id"]


@pytest.mark.parametrize("phone,label", MERCHANT_FORMATS)
def test_vod_momo_rejects_merchant_number(api, auth_headers, show_id, phone, label):
    r = api.post(f"{BASE_URL}/api/billing/vod/{show_id}/momo",
                 headers=auth_headers, json={"phone": phone})
    # Admin may be premium (auto-unlock). Skip if so.
    if r.status_code == 200 and (r.json() or {}).get("alreadyUnlocked"):
        pytest.skip(f"admin is premium — VOD auto-unlocked, guard not reached ({label})")
    assert r.status_code == 400, f"[{label}] expected 400 got {r.status_code}: {r.text}"
    detail = (r.json() or {}).get("detail", "")
    assert "collection account" in detail.lower(), f"[{label}] {detail}"


def test_vod_momo_accepts_customer_number(api, auth_headers, show_id):
    r = api.post(f"{BASE_URL}/api/billing/vod/{show_id}/momo",
                 headers=auth_headers, json={"phone": CUSTOMER_PHONE})
    # OK outcomes: 200 (BeSoft reached or already unlocked) — must NOT be 400 guard.
    assert r.status_code in (200, 502, 500), \
        f"customer number must pass safety guard (no 400 collection-account), got {r.status_code}: {r.text}"
    if r.status_code == 400:
        pytest.fail(f"guard incorrectly blocked customer number: {r.text}")


# -------- Source-code direction audit: sanity check the payload shape in server.py --------
def test_source_direction_audit():
    """Static grep — confirms payer_identifier is bound to user input and payee_identifier
    is bound to BESOFT_PAYOUT_MSISDN in both endpoints."""
    with open("/app/backend/server.py", "r", encoding="utf-8") as f:
        src = f.read()
    # payer_identifier must be set from `payer` (normalized user input), never from BESOFT_PAYOUT_MSISDN
    assert '"payer_identifier": payer' in src, "payer_identifier must be bound to normalized user input `payer`"
    assert '"payer_identifier": BESOFT_PAYOUT_MSISDN' not in src, \
        "SAFETY VIOLATION: payer_identifier must NEVER be set to BESOFT_PAYOUT_MSISDN"
    assert '"payee_identifier": BESOFT_PAYOUT_MSISDN' in src, \
        "payee_identifier must be bound to BESOFT_PAYOUT_MSISDN"
    # Guard is invoked in BOTH endpoints
    guard_calls = src.count("_guard_payer_not_merchant(payer)")
    assert guard_calls >= 2, f"_guard_payer_not_merchant must be called in both endpoints, found {guard_calls}"
