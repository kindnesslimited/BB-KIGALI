"""BB Kigali 89.7 FM — Admin panel, VOD PayPal, Programs, Branding & MoMo debit-credit tests.

Covers review request iteration 3:
  - Admin role auto-promotion on OTP verify
  - Programs API (public + admin CRUD)
  - Settings API (branding + live URLs)
  - Per-VOD PayPal one-time purchase for non-premium users
  - New show https://www.youtube.com/watch?v=Jsi8atSWGbg
  - MoMo debit-credit payload verification (Mongo)
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://radio-vod-platform.preview.emergentagent.com").rstrip("/")
OTP = "123456"
ADMIN_PHONE = "+250798875272"
ADMIN_PHONE_NO_PLUS = "250798875272"
MOMO_PAYER = "250794230137"
NON_ADMIN_PHONE = "+250788119901"
EXPECTED_YT_ID = "Jsi8atSWGbg"


# --------------------- helpers ---------------------
def _api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(api, phone):
    r = api.post(f"{BASE_URL}/api/auth/otp/start", json={"phone": phone})
    assert r.status_code == 200, r.text
    r = api.post(f"{BASE_URL}/api/auth/otp/verify", json={"phone": phone, "code": OTP})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def api():
    return _api()


@pytest.fixture(scope="session")
def admin_session(api):
    return _login(api, ADMIN_PHONE)


@pytest.fixture(scope="session")
def admin_headers(admin_session):
    return {"Authorization": f"Bearer {admin_session['accessToken']}"}


@pytest.fixture(scope="session")
def user_session(api):
    return _login(api, NON_ADMIN_PHONE)


@pytest.fixture(scope="session")
def user_headers(user_session):
    return {"Authorization": f"Bearer {user_session['accessToken']}"}


# --------------------- (a) Admin role auto-promotion ---------------------
class TestAdminAutoPromotion:
    def test_admin_phone_with_plus_gets_admin_role(self, api):
        j = _login(api, ADMIN_PHONE)
        assert j["user"]["role"] == "admin", f"expected role=admin, got {j['user'].get('role')}"

    def test_admin_phone_without_plus_gets_admin_role(self, api):
        j = _login(api, ADMIN_PHONE_NO_PLUS)
        assert j["user"]["role"] == "admin"

    def test_non_admin_phone_gets_user_role(self, api):
        j = _login(api, NON_ADMIN_PHONE)
        # role should be either 'user' or absent-but-not-admin
        assert j["user"].get("role") != "admin"


# --------------------- (b) Programs API ---------------------
class TestPrograms:
    def test_programs_list_returns_three_ordered(self, api):
        r = api.get(f"{BASE_URL}/api/programs")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) == 3, f"expected 3, got {len(items)}"
        # backend schema uses 'name' (see ProgramIn); accept either name/title
        names = [p.get("name") or p.get("title") for p in items]
        assert names[0] == "BBSPORTSTALK", f"1st program should be BBSPORTSTALK, got {names}"
        assert names[1] == "B&B SPORTS BAR"
        assert names[2] == "#IMPUMEKOYIWACU"
        # order field asc
        orders = [p.get("order") for p in items]
        assert orders == sorted(orders), f"programs not sorted by order: {orders}"


# --------------------- (c) Settings — branding ---------------------
class TestSettings:
    def test_settings_returns_branding(self, api):
        r = api.get(f"{BASE_URL}/api/settings")
        assert r.status_code == 200
        j = r.json()
        assert j.get("stationName") == "B&B Kigali", f"stationName={j.get('stationName')}"
        assert j.get("frequency") == "89.7 FM", f"frequency={j.get('frequency')}"
        assert j.get("tagline") == "MURI SPORTS, NI IGITEGO!" or j.get("stationTagline") == "MURI SPORTS, NI IGITEGO!", (
            f"tagline={j.get('tagline')} stationTagline={j.get('stationTagline')}"
        )


# --------------------- (d) New show with Jsi8atSWGbg ---------------------
class TestNewShowSeeded:
    def test_shows_contains_new_youtube_video(self, api):
        r = api.get(f"{BASE_URL}/api/shows")
        assert r.status_code == 200
        shows = r.json()
        matches = [s for s in shows if s.get("videoUrl") and EXPECTED_YT_ID in s["videoUrl"]]
        assert len(matches) >= 1, f"no show with videoUrl containing {EXPECTED_YT_ID}"


# --------------------- (e) Admin settings PUT updates radio_state ---------------------
class TestAdminSettingsUpdate:
    def test_admin_can_update_youtube_live_url_and_reflected_in_now_playing(self, api, admin_headers):
        new_yt = f"https://www.youtube.com/watch?v={EXPECTED_YT_ID}"
        # get current
        cur = api.get(f"{BASE_URL}/api/settings").json()
        original_yt = cur.get("youtubeLiveUrl") or "https://www.youtube.com/watch?v=wPD77ygQKfo"
        try:
            r = api.put(f"{BASE_URL}/api/admin/settings",
                        json={"youtubeLiveUrl": new_yt},
                        headers=admin_headers)
            assert r.status_code == 200, r.text
            # small delay
            time.sleep(0.5)
            np = api.get(f"{BASE_URL}/api/radio/now-playing").json()
            assert np.get("youtubeVideoId") == EXPECTED_YT_ID, f"now-playing youtubeVideoId={np.get('youtubeVideoId')}"
        finally:
            # restore
            api.put(f"{BASE_URL}/api/admin/settings",
                    json={"youtubeLiveUrl": original_yt},
                    headers=admin_headers)


# --------------------- (f) Non-admin can't hit admin endpoints ---------------------
class TestAdminAccessControl:
    def test_non_admin_put_admin_settings_403(self, api, user_headers):
        r = api.put(f"{BASE_URL}/api/admin/settings",
                    json={"tagline": "hacked"},
                    headers=user_headers)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"

    def test_unauth_put_admin_settings_401(self, api):
        r = api.put(f"{BASE_URL}/api/admin/settings", json={"tagline": "x"})
        assert r.status_code in (401, 403)


# --------------------- (g) Admin Programs CRUD ---------------------
class TestAdminProgramsCRUD:
    _created_id = None

    def test_admin_create_program(self, api, admin_headers):
        payload = {"name": "TEST_PROG", "description": "test", "order": 99}
        r = api.post(f"{BASE_URL}/api/admin/programs", json=payload, headers=admin_headers)
        assert r.status_code in (200, 201), r.text
        j = r.json()
        assert j.get("name") == "TEST_PROG"
        assert "id" in j
        TestAdminProgramsCRUD._created_id = j["id"]

    def test_admin_update_program(self, api, admin_headers):
        assert TestAdminProgramsCRUD._created_id, "create must run first"
        r = api.put(f"{BASE_URL}/api/admin/programs/{TestAdminProgramsCRUD._created_id}",
                    json={"name": "TEST_PROG", "description": "updated desc", "order": 99},
                    headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json().get("description") == "updated desc"

    def test_admin_delete_program(self, api, admin_headers):
        assert TestAdminProgramsCRUD._created_id
        r = api.delete(f"{BASE_URL}/api/admin/programs/{TestAdminProgramsCRUD._created_id}",
                       headers=admin_headers)
        assert r.status_code in (200, 204), r.text
        # verify removed
        remaining = api.get(f"{BASE_URL}/api/programs").json()
        assert TestAdminProgramsCRUD._created_id not in {p["id"] for p in remaining}


# --------------------- (h) Admin adds a new show ---------------------
class TestAdminShowsCreate:
    def test_admin_can_create_show(self, api, admin_headers):
        payload = {
            "title": "TEST_SHOW_DELETE_ME",
            "description": "created by test",
            "category": "podcast",
            "premium": False,
            "videoUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }
        r = api.post(f"{BASE_URL}/api/admin/shows", json=payload, headers=admin_headers)
        assert r.status_code in (200, 201), r.text
        j = r.json()
        assert j.get("title") == "TEST_SHOW_DELETE_ME"
        show_id = j["id"]
        # cleanup — best-effort
        api.delete(f"{BASE_URL}/api/admin/shows/{show_id}", headers=admin_headers)


# --------------------- (i) VOD lock/unlock for non-premium ---------------------
class TestVodLocking:
    def test_non_premium_sees_lock_with_price(self, api, user_headers):
        me = api.get(f"{BASE_URL}/api/auth/me", headers=user_headers).json()
        # ensure not premium (fresh user OTP-signed just now)
        shows = api.get(f"{BASE_URL}/api/shows").json()
        # pick a premium show
        target = next((s for s in shows if s.get("premium")), None)
        assert target is not None, "no premium show seeded"
        r = api.get(f"{BASE_URL}/api/shows/{target['id']}", headers=user_headers)
        assert r.status_code == 200
        j = r.json()
        if me.get("tier") != "premium":
            assert j.get("locked") is True, f"expected locked=true, got {j}"
            assert str(j.get("unlockPrice")) == "1.00", f"unlockPrice={j.get('unlockPrice')}"
            assert j.get("unlockCurrency") == "EUR", f"unlockCurrency={j.get('unlockCurrency')}"


# --------------------- (j) PayPal one-time VOD purchase ---------------------
class TestVodPayPalCreate:
    def test_non_premium_create_returns_paypal_approve_url(self, api, user_headers):
        shows = api.get(f"{BASE_URL}/api/shows").json()
        target = next((s for s in shows if s.get("premium")), None)
        assert target is not None
        r = api.post(f"{BASE_URL}/api/billing/vod/{target['id']}/create",
                     json={}, headers=user_headers)
        # user might already have unlocked from earlier test — allow either shape
        assert r.status_code == 200, r.text
        j = r.json()
        if j.get("alreadyUnlocked"):
            pytest.skip("user already unlocked this show; can't verify approveUrl in same session")
        assert "orderId" in j, f"missing orderId: {j}"
        assert "approveUrl" in j and "paypal.com" in j["approveUrl"], f"bad approveUrl: {j}"


# --------------------- (k) MoMo debit-credit payload in Mongo ---------------------
class TestMoMoDebitCredit:
    def test_momo_initiate_with_real_msisdn_writes_debit_credit_payload(self, api, user_headers):
        r = api.post(f"{BASE_URL}/api/billing/momo/initiate",
                     json={"plan": "basic_monthly", "phone": MOMO_PAYER},
                     headers=user_headers)
        # BeSoft accepts payload but MTN provider may return failed — response should still be 200 with reference
        assert r.status_code == 200, r.text
        j = r.json()
        assert "reference" in j and j["reference"], f"no reference: {j}"

        # Verify Mongo payload
        try:
            from pymongo import MongoClient
        except ImportError:
            pytest.skip("pymongo not installed in test env")
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "test_database")
        client = MongoClient(mongo_url)
        db = client[db_name]
        doc = db.payments.find_one({"reference": j["reference"]})
        assert doc is not None, "payment doc not persisted"
        payload = doc.get("besoftPayload") or {}
        debit = payload.get("debit") or {}
        meta = debit.get("metadata") or {}
        assert meta.get("kind") == "debit_credit", f"metadata.kind={meta.get('kind')}: {meta}"
        credits = meta.get("credits") or []
        assert len(credits) >= 1, f"credits empty: {meta}"
        assert credits[0].get("payee_identifier") == "250798875272", credits[0]
