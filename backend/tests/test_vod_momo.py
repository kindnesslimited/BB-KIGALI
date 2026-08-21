"""BB FM Kigali - Iteration 4: parallel EUR/RWF display + per-VOD MoMo unlock tests."""
import os
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("EXPO_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# Non-admin, non-premium tester (E.164). "555444" is NOT in ADMIN_PHONES.
NON_ADMIN_PHONE = "+250788555444"
PAYER_MSISDN = "250794230137"  # NOTE: this IS in ADMIN_PHONES → don't use for auth, only as payer
OTP = "123456"


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def token(api):
    api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": NON_ADMIN_PHONE})
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": NON_ADMIN_PHONE, "code": OTP})
    assert r.status_code == 200, r.text
    j = r.json()
    # ensure this user is NON-admin, NON-premium
    assert j["user"].get("role") != "admin", f"phone {NON_ADMIN_PHONE} is unexpectedly admin"
    assert j["user"].get("tier") != "premium"
    return j["accessToken"]


@pytest.fixture(scope="module")
def premium_show_id(api):
    r = api.get(f"{BASE_URL}/api/shows")
    assert r.status_code == 200
    shows = r.json()
    prem = [s for s in shows if s.get("premium") or s.get("isPremium")]
    assert prem, "No premium show found"
    return prem[0]["id"]


# ---- (a) parallel pricing on locked show ----
def test_locked_show_returns_eur_and_rwf(api, token, premium_show_id):
    headers = {"Authorization": f"Bearer {token}"}
    r = api.get(f"{BASE_URL}/api/shows/{premium_show_id}", headers=headers)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("locked") is True
    assert j.get("unlockPrice") == "1.00"
    assert j.get("unlockCurrency") == "EUR"
    assert j.get("unlockPriceRwf") == "1000"
    assert j.get("videoUrl") is None


# ---- (b) POST /billing/vod/{id}/momo ----
def test_vod_momo_initiate(api, token, mongo, premium_show_id):
    headers = {"Authorization": f"Bearer {token}"}
    r = api.post(
        f"{BASE_URL}/api/billing/vod/{premium_show_id}/momo",
        json={"phone": PAYER_MSISDN},
        headers=headers,
    )
    # BeSoft-side may 502 if MTN provider hard-rejects; verify Mongo either way
    body = r.text
    # If backend returned 200 → assert response envelope
    if r.status_code == 200:
        j = r.json()
        assert "reference" in j and j["reference"].startswith("vod-")
        assert "besoftTxId" in j
        assert "status" in j and j["status"] in ("pending", "processing", "success", "failed")
        assert j.get("currency") == "RWF"
        assert j.get("amount") == 1000
        ref = j["reference"]
    else:
        # 502 acceptable if provider rejected but Mongo record must still exist
        assert r.status_code in (502,), f"unexpected status: {r.status_code} {body}"
        # Find most recent vod purchase for this user+show
        time.sleep(0.3)
        doc = mongo.vod_purchases.find_one(
            {"showId": premium_show_id, "method": "mtn_momo"},
            sort=[("createdAt", -1)],
        )
        assert doc is not None, "vod_purchases record missing after 502"
        ref = doc["reference"]

    time.sleep(0.4)
    doc = mongo.vod_purchases.find_one({"reference": ref})
    assert doc is not None
    assert doc["method"] == "mtn_momo"
    assert doc["amount"] == 1000
    assert doc["currency"] == "RWF"
    # besoftPayload may be None if BeSoft rejected before persisting; but request payload must have been built.
    # If provider accepted → verify metadata.kind=='debit_credit' + credits[0].payee_identifier
    bp = doc.get("besoftPayload") or {}
    if bp:
        debit = bp.get("debit") or {}
        meta = debit.get("metadata") or {}
        assert meta.get("kind") == "debit_credit", f"kind={meta.get('kind')}"
        credits = meta.get("credits") or []
        assert credits and credits[0].get("payee_identifier") == "250798875272", credits


# ---- (c) GET /billing/vod/{id}/momo/{ref} ----
def test_vod_momo_status_polling(api, token, mongo, premium_show_id):
    headers = {"Authorization": f"Bearer {token}"}
    # Grab most recent VOD purchase for this user
    r = api.get(f"{BASE_URL}/api/shows/{premium_show_id}", headers=headers)
    assert r.status_code == 200

    # Try to initiate fresh; if 502, fall back to last mongo doc
    init = api.post(
        f"{BASE_URL}/api/billing/vod/{premium_show_id}/momo",
        json={"phone": PAYER_MSISDN},
        headers=headers,
    )
    if init.status_code == 200:
        ref = init.json()["reference"]
    else:
        doc = mongo.vod_purchases.find_one(
            {"showId": premium_show_id, "method": "mtn_momo"},
            sort=[("createdAt", -1)],
        )
        assert doc, "no VOD momo doc to poll"
        ref = doc["reference"]

    poll = api.get(f"{BASE_URL}/api/billing/vod/{premium_show_id}/momo/{ref}", headers=headers)
    assert poll.status_code == 200, poll.text
    pj = poll.json()
    assert pj.get("reference") == ref
    assert "status" in pj
    assert pj["status"] in ("pending", "processing", "success", "failed")


def test_vod_momo_bad_phone_returns_400(api, token, premium_show_id):
    headers = {"Authorization": f"Bearer {token}"}
    r = api.post(
        f"{BASE_URL}/api/billing/vod/{premium_show_id}/momo",
        json={"phone": "abc"},
        headers=headers,
    )
    assert r.status_code == 400, r.text


def test_vod_momo_unauth(api, premium_show_id):
    r = api.post(
        f"{BASE_URL}/api/billing/vod/{premium_show_id}/momo",
        json={"phone": PAYER_MSISDN},
    )
    assert r.status_code in (401, 403)
