"""BB FM Kigali - Radio + VOD backend."""
import os
import uuid
import logging
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Literal

import jwt
import httpx
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Request
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ.get("JWT_SECRET", "bbfm-kigali-dev-secret-change-me")
JWT_ALG = "HS256"
MOCK_OTP_CODE = "123456"
YOUTUBE_LIVE_ID = "wPD77ygQKfo"
YOUTUBE_LIVE_URL = f"https://www.youtube.com/watch?v={YOUTUBE_LIVE_ID}"
YOUTUBE_EMBED_URL = f"https://www.youtube.com/embed/{YOUTUBE_LIVE_ID}?autoplay=1&playsinline=1&rel=0"
DEMO_AUDIO_STREAM = "https://stream.zeno.fm/0r0xa792kwzuv"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://radio-vod-platform.preview.emergentagent.com")

# PayPal config
PAYPAL_ENV = os.environ.get("PAYPAL_ENV", "sandbox").lower()
PAYPAL_BASE = "https://api-m.paypal.com" if PAYPAL_ENV == "live" else "https://api-m.sandbox.paypal.com"
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")
PAYPAL_WEBHOOK_ID = os.environ.get("PAYPAL_WEBHOOK_ID", "")
PAYPAL_RETURN_URL = os.environ.get("PAYPAL_RETURN_URL", f"{PUBLIC_BASE_URL}/paypal/success")
PAYPAL_CANCEL_URL = os.environ.get("PAYPAL_CANCEL_URL", f"{PUBLIC_BASE_URL}/paypal/cancel")
PAYPAL_CURRENCY = os.environ.get("PAYPAL_CURRENCY", "EUR")
PAYPAL_PRICES = {
    "basic_monthly":   os.environ.get("PAYPAL_PRICE_BASIC_MONTHLY", "1.00"),
    "basic_yearly":    os.environ.get("PAYPAL_PRICE_BASIC_YEARLY", "10.00"),
    "premium_monthly": os.environ.get("PAYPAL_PRICE_PREMIUM_MONTHLY", "3.00"),
    "premium_yearly":  os.environ.get("PAYPAL_PRICE_PREMIUM_YEARLY", "30.00"),
}

# BeSoft (MTN MoMo) config
BESOFT_BASE_URL = os.environ.get("BESOFT_BASE_URL", "https://payment.besoft.info/api/v1").rstrip("/")
BESOFT_API_KEY = os.environ.get("BESOFT_API_KEY", "")
BESOFT_API_SECRET = os.environ.get("BESOFT_API_SECRET", "")
BESOFT_PAYOUT_MSISDN = os.environ.get("BESOFT_PAYOUT_MSISDN", "")
# BeSoft's SSL cert is currently expired — set BESOFT_VERIFY_SSL=true once they renew.
BESOFT_VERIFY_SSL = os.environ.get("BESOFT_VERIFY_SSL", "false").lower() == "true"
# Admin phones — first-time OTP verify from these numbers auto-promotes to admin role
ADMIN_PHONES = {p.strip() for p in os.environ.get("ADMIN_PHONES", "").split(",") if p.strip()}
VOD_PRICE_EUR = os.environ.get("VOD_PRICE_EUR", "1.00")
VOD_PRICE_RWF = os.environ.get("VOD_PRICE_RWF", "1000")

# Route Mobile SMSPLUS Bulk HTTP API
SMS_API_URL = os.environ.get("SMS_API_URL", "").strip()
SMS_USERNAME = os.environ.get("SMS_USERNAME", "").strip()
SMS_PASSWORD = os.environ.get("SMS_PASSWORD", "").strip()
SMS_SENDER_ID = os.environ.get("SMS_SENDER_ID", "BBKIGALI").strip()
SMS_VERIFY_SSL = os.environ.get("SMS_VERIFY_SSL", "false").lower() == "true"
SMS_DEV_RETURN_CODE = os.environ.get("SMS_DEV_RETURN_CODE", "false").lower() == "true"

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="BB FM Kigali API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("bbfm")


# ---------- Models ----------
class OTPStartIn(BaseModel):
    phone: str

class OTPVerifyIn(BaseModel):
    phone: str
    code: str

class AuthOut(BaseModel):
    accessToken: str
    user: dict

class UserOut(BaseModel):
    id: str
    phone: Optional[str] = None
    email: Optional[str] = None
    displayName: Optional[str] = None
    picture: Optional[str] = None
    tier: Literal["free", "basic", "premium"] = "free"
    role: Literal["user", "admin"] = "user"
    subscriptionExpiresAt: Optional[str] = None


class GoogleSessionIn(BaseModel):
    session_id: str

class SubscribeIn(BaseModel):
    plan: Literal["basic_monthly", "basic_yearly", "premium_monthly", "premium_yearly"]
    method: Literal["stripe", "paypal", "mtn_momo", "airtel"]
    phone: Optional[str] = None  # for mobile money

class ProfileUpdateIn(BaseModel):
    displayName: Optional[str] = None


# ---------- Helpers ----------
def sign_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    # 1) Try JWT (phone OTP flow)
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if user:
            return await _tier_refresh(user)
    except jwt.PyJWTError:
        pass
    # 2) Try Emergent session_token (Google OAuth flow)
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if session:
        exp = session.get("expires_at")
        if exp:
            try:
                exp_dt = datetime.fromisoformat(exp) if isinstance(exp, str) else exp
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if exp_dt >= datetime.now(timezone.utc):
                    user = await db.users.find_one({"id": session["user_id"]}, {"_id": 0})
                    if user:
                        return await _tier_refresh(user)
            except Exception:
                pass
    raise HTTPException(401, "Invalid or expired token")


async def _tier_refresh(user: dict) -> dict:
    if user.get("subscriptionExpiresAt"):
        try:
            exp = datetime.fromisoformat(user["subscriptionExpiresAt"])
            if exp < datetime.now(timezone.utc):
                await db.users.update_one({"id": user["id"]}, {"$set": {"tier": "free"}})
                user["tier"] = "free"
        except Exception:
            pass
    return user


def user_public(u: dict) -> dict:
    return {
        "id": u["id"],
        "phone": u.get("phone"),
        "email": u.get("email"),
        "displayName": u.get("displayName"),
        "picture": u.get("picture"),
        "tier": u.get("tier", "free"),
        "role": u.get("role", "user"),
        "subscriptionExpiresAt": u.get("subscriptionExpiresAt"),
    }


async def require_admin(user = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return user


PLAN_CATALOG = {
    "basic_monthly":   {"tier": "basic",   "amount": 1000,  "currency": "RWF", "period": "monthly", "days": 30,  "label": "Basic Monthly"},
    "basic_yearly":    {"tier": "basic",   "amount": 10000, "currency": "RWF", "period": "yearly",  "days": 365, "label": "Basic Yearly"},
    "premium_monthly": {"tier": "premium", "amount": 3000,  "currency": "RWF", "period": "monthly", "days": 30,  "label": "Premium Monthly"},
    "premium_yearly":  {"tier": "premium", "amount": 30000, "currency": "RWF", "period": "yearly",  "days": 365, "label": "Premium Yearly"},
}


# ---------- Auth ----------
async def _send_sms(destination: str, message: str) -> tuple[bool, str]:
    """Send SMS via Route Mobile SMSPLUS Bulk HTTP API. Returns (ok, provider_response)."""
    if not SMS_API_URL or not SMS_USERNAME or not SMS_PASSWORD:
        return False, "sms_not_configured"
    params = {
        "username": SMS_USERNAME,
        "password": SMS_PASSWORD,
        "type": "0",              # plain text (GSM 03.38)
        "dlr": "1",               # delivery report requested
        "destination": destination.lstrip("+"),
        "source": SMS_SENDER_ID,
        "message": message,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=SMS_VERIFY_SSL) as c:
            r = await c.get(SMS_API_URL, params=params)
    except httpx.RequestError as e:
        logger.warning("SMS network error: %s", e)
        return False, f"network:{e}"
    body = (r.text or "").strip()
    logger.info("SMS provider response: %s %s", r.status_code, body[:200])
    # Success format: 1701|<cell>|<msgid>
    ok = body.startswith("1701") and r.status_code < 400
    return ok, body


@api.post("/auth/otp/start")
async def otp_start(body: OTPStartIn):
    phone = body.phone.strip()
    if len(phone) < 7:
        raise HTTPException(400, "Invalid phone number")

    normalized = phone.lstrip("+").strip()
    is_admin_phone = phone in ADMIN_PHONES or normalized in ADMIN_PHONES

    # Generate a fresh 6-digit code. Admin phones + missing SMS credentials => keep the universal test code 123456.
    if is_admin_phone or not (SMS_API_URL and SMS_USERNAME and SMS_PASSWORD):
        code = MOCK_OTP_CODE
    else:
        import secrets as _secrets
        code = f"{_secrets.randbelow(1_000_000):06d}"

    await db.otp_challenges.update_one(
        {"phone": phone},
        {"$set": {
            "phone": phone,
            "code": code,
            "attempts": 0,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )

    # Attempt to send SMS via Route Mobile. Non-fatal — dev fallback returns the code in the response.
    sms_sent = False
    provider_resp = "sms_not_attempted"
    if not is_admin_phone and SMS_API_URL and SMS_USERNAME and SMS_PASSWORD:
        message = f"BB Kigali 89.7 FM: your verification code is {code}. Valid 10 min."
        sms_sent, provider_resp = await _send_sms(normalized, message)

    resp: dict = {"ok": True, "smsSent": sms_sent}
    if is_admin_phone:
        resp["message"] = "Admin phone — use 123456"
        resp["testCode"] = MOCK_OTP_CODE
    elif not sms_sent and SMS_DEV_RETURN_CODE:
        resp["message"] = f"SMS delivery failed ({provider_resp[:60]}) — dev mode: use the code below."
        resp["testCode"] = code
    elif sms_sent:
        resp["message"] = "OTP sent via SMS."
    else:
        resp["message"] = "OTP recorded. If you don't receive the SMS, contact support."
    return resp


@api.post("/auth/otp/verify", response_model=AuthOut)
async def otp_verify(body: OTPVerifyIn):
    phone = body.phone.strip()
    challenge = await db.otp_challenges.find_one({"phone": phone}, {"_id": 0})
    if not challenge:
        raise HTTPException(401, "No OTP challenge. Request a new code.")
    submitted = body.code.strip()
    expected = challenge.get("code") or MOCK_OTP_CODE
    if submitted != expected:
        await db.otp_challenges.update_one({"phone": phone}, {"$inc": {"attempts": 1}})
        raise HTTPException(401, "Invalid code")
    user = await db.users.find_one({"phone": phone}, {"_id": 0})
    normalized_phone = phone.lstrip("+").strip()
    is_admin_phone = phone in ADMIN_PHONES or normalized_phone in ADMIN_PHONES
    if not user:
        role = "admin" if is_admin_phone else "user"
        user = {
            "id": str(uuid.uuid4()),
            "phone": phone,
            "displayName": None,
            "tier": "free",
            "role": role,
            "subscriptionExpiresAt": None,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user.copy())
    else:
        # Auto-promote to admin if phone is in the admin list (idempotent)
        if is_admin_phone and user.get("role") != "admin":
            await db.users.update_one({"id": user["id"]}, {"$set": {"role": "admin"}})
            user["role"] = "admin"
    await db.otp_challenges.delete_one({"phone": phone})
    return {"accessToken": sign_jwt(user["id"]), "user": user_public(user)}


@api.get("/auth/me", response_model=UserOut)
async def me(user = Depends(get_current_user)):
    return user_public(user)


@api.post("/auth/session")
async def google_session(body: GoogleSessionIn):
    """Exchange an Emergent session_id (from Google OAuth redirect) for a 7-day session_token.
    Upserts the user by email so Google users share the same account as phone-OTP users with the same email."""
    session_id = body.session_id.strip()
    if not session_id:
        raise HTTPException(400, "Missing session_id")
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id},
            )
    except httpx.RequestError as e:
        raise HTTPException(502, f"Auth provider unreachable: {e}")
    if r.status_code != 200:
        raise HTTPException(401, "Invalid or expired session")
    data = r.json() or {}
    email = (data.get("email") or "").strip().lower()
    name = data.get("name") or ""
    picture = data.get("picture") or None
    session_token = data.get("session_token")
    if not email or not session_token:
        raise HTTPException(401, "Incomplete session data")

    # Upsert user by email (share with any existing phone-signup user whose email later matches)
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        is_admin = email.lower() in {a.lower() for a in ADMIN_PHONES}
        user = {
            "id": str(uuid.uuid4()),
            "phone": None,
            "email": email,
            "displayName": name or (email.split("@")[0] if email else None),
            "picture": picture,
            "tier": "free",
            "role": "admin" if is_admin else "user",
            "subscriptionExpiresAt": None,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user.copy())
    else:
        updates = {}
        if name and not user.get("displayName"):
            updates["displayName"] = name
        if picture and not user.get("picture"):
            updates["picture"] = picture
        if updates:
            await db.users.update_one({"id": user["id"]}, {"$set": updates})
            user.update(updates)

    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    await db.user_sessions.update_one(
        {"session_token": session_token},
        {"$set": {
            "session_token": session_token,
            "user_id": user["id"],
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    return {"session_token": session_token, "user": user_public(user)}


@api.patch("/auth/me", response_model=UserOut)
async def update_me(body: ProfileUpdateIn, user = Depends(get_current_user)):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if updates:
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
    fresh = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    return user_public(fresh)


# ---------- Radio ----------
@api.get("/radio/now-playing")
async def now_playing():
    doc = await db.radio_state.find_one({"key": "current"}, {"_id": 0})
    if not doc:
        doc = {
            "key": "current",
            "streamUrl": DEMO_AUDIO_STREAM,
            "youtubeVideoId": YOUTUBE_LIVE_ID,
            "youtubeEmbedUrl": YOUTUBE_EMBED_URL,
            "youtubeWatchUrl": YOUTUBE_LIVE_URL,
            "showTitle": "BB FM Kigali Live",
            "djName": "Live on YouTube",
            "description": "Watch BB FM Kigali live — streaming 24/7 from Rwanda.",
            "coverImage": f"https://img.youtube.com/vi/{YOUTUBE_LIVE_ID}/maxresdefault.jpg",
            "isLive": True,
        }
    return {k: v for k, v in doc.items() if k != "key"}


@api.get("/radio/schedule")
async def schedule():
    items = await db.schedule.find({}, {"_id": 0}).sort("order", 1).to_list(50)
    return items


# ---------- Shows / VOD / Podcasts ----------
@api.get("/shows")
async def list_shows(category: Optional[str] = None):
    q = {}
    if category and category.lower() != "all":
        q = {"category": category.lower()}
    items = await db.shows.find(q, {"_id": 0}).sort("createdAt", -1).to_list(200)
    return items


@api.get("/shows/{show_id}")
async def get_show(show_id: str, user = Depends(get_current_user)):
    show = await db.shows.find_one({"id": show_id}, {"_id": 0})
    if not show:
        raise HTTPException(404, "Show not found")
    # Premium users get all VOD free. Non-premium users must purchase per-VOD (1 EUR).
    if user.get("tier") == "premium":
        return {**show, "locked": False, "unlockedFor": "premium"}
    # Check if user already purchased this specific VOD
    owned = await db.vod_purchases.find_one({"userId": user["id"], "showId": show_id, "status": "success"}, {"_id": 0})
    if owned:
        return {**show, "locked": False, "unlockedFor": "purchase"}
    # Locked — client should prompt to upgrade to premium OR pay 1 EUR one-time
    return {**show, "locked": True, "videoUrl": None, "unlockPrice": VOD_PRICE_EUR, "unlockCurrency": "EUR", "unlockPriceRwf": VOD_PRICE_RWF}


# ---------- News ----------
@api.get("/news")
async def list_news():
    items = await db.news.find({}, {"_id": 0}).sort("publishedAt", -1).to_list(100)
    return items


@api.get("/news/{news_id}")
async def get_news(news_id: str):
    item = await db.news.find_one({"id": news_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "News not found")
    return item


# ---------- Subscriptions & Payments ----------
@api.get("/billing/plans")
async def list_plans():
    return [{"id": pid, **p} for pid, p in PLAN_CATALOG.items()]


@api.post("/billing/subscribe")
async def subscribe(body: SubscribeIn, user = Depends(get_current_user)):
    plan = PLAN_CATALOG.get(body.plan)
    if not plan:
        raise HTTPException(400, "Invalid plan")
    # MOCK: instantly mark as paid (in production, redirect to Stripe/PayPal or poll MoMo)
    payment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=plan["days"])
    payment = {
        "id": payment_id,
        "userId": user["id"],
        "plan": body.plan,
        "planLabel": plan["label"],
        "amount": plan["amount"],
        "currency": plan["currency"],
        "method": body.method,
        "phone": body.phone,
        "status": "success",
        "createdAt": now.isoformat(),
    }
    await db.payments.insert_one(payment.copy())
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "tier": plan["tier"],
            "subscriptionExpiresAt": expires.isoformat(),
            "currentPlan": body.plan,
        }}
    )
    return {
        "ok": True,
        "paymentId": payment_id,
        "tier": plan["tier"],
        "expiresAt": expires.isoformat(),
        "amount": plan["amount"],
        "currency": plan["currency"],
        "method": body.method,
        "mocked": True,
        "note": f"Payment via {body.method} was processed in demo mode.",
    }


@api.get("/billing/history")
async def payment_history(user = Depends(get_current_user)):
    items = await db.payments.find({"userId": user["id"]}, {"_id": 0}).sort("createdAt", -1).to_list(100)
    return items


# ---------- MTN MoMo (BeSoft Pay - LIVE) ----------
# Real integration with BeSoft merchant API.
# Docs: https://payment.besoft.info/docs  |  https://payment.besoft.info/api/v1/openapi.yaml
# All debit amounts settle to BESOFT_PAYOUT_MSISDN configured on the merchant profile.
class MoMoInitiateIn(BaseModel):
    plan: Literal["basic_monthly", "basic_yearly", "premium_monthly", "premium_yearly"]
    phone: str  # payer MSISDN, may include + or country code


def _besoft_headers():
    if not BESOFT_API_KEY or not BESOFT_API_SECRET:
        raise HTTPException(500, "BeSoft credentials not configured on server")
    return {
        "X-API-Key": BESOFT_API_KEY,
        "X-API-Secret": BESOFT_API_SECRET,
        "Content-Type": "application/json",
    }


def _normalize_msisdn(phone: str) -> str:
    """Strip +, spaces. Ensure starts with a country code. Assume 250 (Rwanda) if 9 digits (e.g. 78xxxxxxx)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 9 and digits.startswith(("7", "0")):
        digits = "250" + digits.lstrip("0")
    return digits


@api.post("/billing/momo/initiate")
async def momo_initiate(body: MoMoInitiateIn, user = Depends(get_current_user)):
    plan = PLAN_CATALOG.get(body.plan)
    if not plan:
        raise HTTPException(400, "Invalid plan")
    payer = _normalize_msisdn(body.phone)
    if len(payer) < 10:
        raise HTTPException(400, "Invalid payer phone number")

    reference = f"bbfm-{uuid.uuid4().hex[:16]}"
    debit_amount = float(plan["amount"])
    # Merchant charge_percent is 0 on this account (confirmed via /transfer response). Adjust if BeSoft changes it.
    credit_amount = debit_amount
    payload = {
        "idempotency_key": reference,
        "debit": {
            "amount": debit_amount,
            "currency": plan["currency"],  # RWF
            "payment_method": "mtn_momo_collection",
            "payer_identifier": payer,
            "description": f"BB FM Kigali — {plan['label']}",
            "idempotency_key": reference + "-d",
            "country": "RW",
            "metadata": {"userId": user["id"], "plan": body.plan},
        },
        "credits": [{
            "amount": credit_amount,
            "currency": plan["currency"],
            "payment_method": "mtn_momo_disbursement",
            "payee_identifier": BESOFT_PAYOUT_MSISDN,
            "description": f"Payout to BB FM Kigali — {plan['label']}",
            "idempotency_key": reference + "-c1",
            "country": "RW",
        }],
    }

    now = datetime.now(timezone.utc)
    payment_doc = {
        "id": reference,
        "reference": reference,
        "userId": user["id"],
        "plan": body.plan,
        "planLabel": plan["label"],
        "amount": plan["amount"],
        "currency": plan["currency"],
        "method": "mtn_momo",
        "phone": payer,
        "status": "pending",
        "createdAt": now.isoformat(),
    }
    await db.payments.insert_one(payment_doc.copy())

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=BESOFT_VERIFY_SSL) as c:
            r = await c.post(f"{BESOFT_BASE_URL}/public/payments/debit-credit", headers=_besoft_headers(), json=payload)
    except httpx.RequestError as e:
        await db.payments.update_one({"reference": reference}, {"$set": {"status": "failed", "error": f"network: {e}"}})
        raise HTTPException(502, f"Unable to reach payment provider: {e}")

    if r.status_code >= 300:
        logger.error("BeSoft transfer failed %s %s", r.status_code, r.text)
        await db.payments.update_one({"reference": reference}, {"$set": {"status": "failed", "error": r.text[:500]}})
        raise HTTPException(502, f"MoMo provider rejected the request: {r.text[:200]}")

    data = r.json().get("data") or {}
    debit = (data.get("debit") or {}) if isinstance(data, dict) else {}
    besoft_tx_id = debit.get("id") or data.get("id")
    besoft_status = (debit.get("status") or data.get("status") or "pending").lower()

    await db.payments.update_one(
        {"reference": reference},
        {"$set": {"besoftTxId": besoft_tx_id, "besoftPayload": data, "status": besoft_status if besoft_status in ("pending", "processing", "success", "failed") else "pending"}},
    )

    return {
        "reference": reference,
        "besoftTxId": besoft_tx_id,
        "status": besoft_status,
        "message": "Approve the payment on your phone. We'll notify you when it completes.",
        "amount": plan["amount"],
        "currency": plan["currency"],
        "pollUrl": f"{PUBLIC_BASE_URL}/api/billing/momo/{reference}",
    }


@api.post("/billing/momo/callback")
async def momo_callback(request: Request):
    """Webhook receiver for BeSoft Pay. Configure this URL as your merchant webhook_url on BeSoft."""
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid_json"}
    logger.info("BeSoft webhook: %s", payload)
    # Payload may contain: { transaction_id, external_id, status, transaction_type, amount, currency, provider_ref, ... }
    tx = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    besoft_tx_id = tx.get("id") or tx.get("transaction_id")
    external_id = tx.get("external_id") or tx.get("idempotency_key")
    raw_status = (tx.get("status") or "").lower()
    tx_type = (tx.get("transaction_type") or "debit").lower()

    query = {}
    if external_id:
        # our reference == idempotency_key (before -d suffix) or reference itself
        base_ref = external_id.split("-d")[0] if external_id.endswith("-d") else external_id
        query = {"reference": base_ref}
    elif besoft_tx_id:
        query = {"besoftTxId": besoft_tx_id}
    if not query:
        return {"ok": False, "error": "no_match_key"}

    payment = await db.payments.find_one(query, {"_id": 0})
    if not payment:
        # Maybe it's a VOD one-time purchase
        vod = await db.vod_purchases.find_one(query, {"_id": 0}) if "reference" in query else None
        if not vod and besoft_tx_id:
            vod = await db.vod_purchases.find_one({"besoftTxId": besoft_tx_id}, {"_id": 0})
        if vod:
            raw = (tx.get("status") or "").lower()
            final_status_v = "success" if raw in ("success", "completed") else \
                             "failed"  if raw in ("failed", "reversed", "expired", "cancelled") else \
                             "processing" if raw == "processing" else "pending"
            await db.vod_purchases.update_one({"reference": vod["reference"]}, {"$set": {
                "status": final_status_v, "besoftCallback": payload,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
            }})
            return {"ok": True, "status": final_status_v, "reference": vod["reference"], "kind": "vod"}
        return {"ok": True, "note": "no matching payment"}

    final_status = "success" if raw_status in ("success", "completed") else \
                   "failed"  if raw_status in ("failed", "reversed", "expired", "cancelled") else \
                   "processing" if raw_status == "processing" else "pending"

    await db.payments.update_one({"reference": payment["reference"]}, {"$set": {
        "status": final_status,
        "besoftCallback": payload,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }})

    # Upgrade tier only when the DEBIT leg reaches success (money left the payer)
    if final_status == "success" and tx_type in ("debit", ""):
        p = PLAN_CATALOG.get(payment["plan"])
        if p:
            expires = datetime.now(timezone.utc) + timedelta(days=p["days"])
            await db.users.update_one(
                {"id": payment["userId"]},
                {"$set": {"tier": p["tier"], "subscriptionExpiresAt": expires.isoformat(), "currentPlan": payment["plan"]}},
            )
    return {"ok": True, "status": final_status, "reference": payment["reference"]}


@api.get("/billing/momo/{reference}")
async def momo_status(reference: str, user = Depends(get_current_user)):
    p = await db.payments.find_one({"reference": reference, "userId": user["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Payment not found")

    # If still pending/processing and we have a BeSoft tx id, poll BeSoft for fresh status
    if p.get("status") in ("pending", "processing") and p.get("besoftTxId"):
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=BESOFT_VERIFY_SSL) as c:
                r = await c.get(f"{BESOFT_BASE_URL}/public/payments/{p['besoftTxId']}/status", headers=_besoft_headers())
            if r.status_code == 200:
                data = (r.json().get("data") or {}) if isinstance(r.json(), dict) else {}
                raw_status = (data.get("status") or "").lower()
                new_status = "success" if raw_status in ("success", "completed") else \
                             "failed"  if raw_status in ("failed", "reversed", "expired", "cancelled") else \
                             "processing" if raw_status == "processing" else "pending"
                if new_status != p["status"]:
                    await db.payments.update_one({"reference": reference}, {"$set": {"status": new_status, "besoftStatusPayload": data, "updatedAt": datetime.now(timezone.utc).isoformat()}})
                    p["status"] = new_status
                    # Upgrade tier on success
                    if new_status == "success":
                        plan = PLAN_CATALOG.get(p["plan"])
                        if plan:
                            expires = datetime.now(timezone.utc) + timedelta(days=plan["days"])
                            await db.users.update_one({"id": user["id"]}, {"$set": {"tier": plan["tier"], "subscriptionExpiresAt": expires.isoformat(), "currentPlan": p["plan"]}})
        except httpx.RequestError as e:
            logger.warning("BeSoft status poll failed: %s", e)

    return {"reference": reference, "status": p["status"], "amount": p["amount"], "currency": p["currency"], "besoftTxId": p.get("besoftTxId")}


# ---------- PayPal (real live-mode) ----------
PLAN_META = {
    "basic_monthly":   {"tier": "basic",   "period": "monthly", "days": 30,  "label": "Basic Monthly",   "interval_unit": "MONTH", "interval_count": 1},
    "basic_yearly":    {"tier": "basic",   "period": "yearly",  "days": 365, "label": "Basic Yearly",    "interval_unit": "YEAR",  "interval_count": 1},
    "premium_monthly": {"tier": "premium", "period": "monthly", "days": 30,  "label": "Premium Monthly", "interval_unit": "MONTH", "interval_count": 1},
    "premium_yearly":  {"tier": "premium", "period": "yearly",  "days": 365, "label": "Premium Yearly",  "interval_unit": "YEAR",  "interval_count": 1},
}


async def _paypal_token() -> str:
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        raise HTTPException(500, "PayPal credentials not configured on server")
    basic = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()).decode()
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            f"{PAYPAL_BASE}/v1/oauth2/token",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            content="grant_type=client_credentials",
        )
    if r.status_code >= 300:
        logger.error("PayPal oauth failed %s %s", r.status_code, r.text)
        raise HTTPException(502, f"PayPal OAuth failed: {r.text}")
    return r.json()["access_token"]


async def _paypal_ensure_plans() -> dict:
    """Create Product + 4 Plans on PayPal if not yet stored. Returns plan_key -> plan_id map."""
    existing = await db.paypal_plans.find_one({"env": PAYPAL_ENV}, {"_id": 0})
    if existing and all(k in existing.get("plans", {}) for k in PLAN_META):
        return existing["plans"]

    token = await _paypal_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as c:
        # 1) Product
        product_id = existing.get("productId") if existing else None
        if not product_id:
            pr = await c.post(
                f"{PAYPAL_BASE}/v1/catalogs/products",
                headers={**headers, "PayPal-Request-Id": str(uuid.uuid4())},
                json={
                    "name": "BB FM Kigali Subscription",
                    "description": "Access to BB FM Kigali live radio, VOD, and podcasts.",
                    "type": "SERVICE",
                    "category": "ENTERTAINMENT_AND_MEDIA",
                },
            )
            if pr.status_code >= 300:
                logger.error("PayPal product create %s %s", pr.status_code, pr.text)
                raise HTTPException(502, f"PayPal product create failed: {pr.text}")
            product_id = pr.json()["id"]

        # 2) Plans
        plans_map: dict = (existing or {}).get("plans", {}) if existing else {}
        for key, meta in PLAN_META.items():
            if plans_map.get(key):
                continue
            price = PAYPAL_PRICES[key]
            body = {
                "product_id": product_id,
                "name": f"BB FM {meta['label']}",
                "description": f"BB FM Kigali {meta['label']}",
                "status": "ACTIVE",
                "billing_cycles": [{
                    "frequency": {"interval_unit": meta["interval_unit"], "interval_count": meta["interval_count"]},
                    "tenure_type": "REGULAR",
                    "sequence": 1,
                    "total_cycles": 0,
                    "pricing_scheme": {"fixed_price": {"value": price, "currency_code": PAYPAL_CURRENCY}},
                }],
                "payment_preferences": {
                    "auto_bill_outstanding": True,
                    "setup_fee_failure_action": "CONTINUE",
                    "payment_failure_threshold": 2,
                },
            }
            plr = await c.post(
                f"{PAYPAL_BASE}/v1/billing/plans",
                headers={**headers, "PayPal-Request-Id": str(uuid.uuid4())},
                json=body,
            )
            if plr.status_code >= 300:
                logger.error("PayPal plan create %s %s", plr.status_code, plr.text)
                raise HTTPException(502, f"PayPal plan create failed for {key}: {plr.text}")
            plans_map[key] = plr.json()["id"]

    await db.paypal_plans.update_one(
        {"env": PAYPAL_ENV},
        {"$set": {"env": PAYPAL_ENV, "productId": product_id, "plans": plans_map, "updatedAt": datetime.now(timezone.utc).isoformat()}},
        upsert=True,
    )
    logger.info("PayPal plans ensured: %s", plans_map)
    return plans_map


class PayPalCreateIn(BaseModel):
    plan: Literal["basic_monthly", "basic_yearly", "premium_monthly", "premium_yearly"]


@api.post("/billing/paypal/create-subscription")
async def paypal_create(body: PayPalCreateIn, user = Depends(get_current_user)):
    plan_meta = PLAN_META[body.plan]
    plans = await _paypal_ensure_plans()
    plan_id = plans.get(body.plan)
    if not plan_id:
        raise HTTPException(500, "PayPal plan not provisioned")
    token = await _paypal_token()
    payload = {
        "plan_id": plan_id,
        "custom_id": user["id"],
        "application_context": {
            "brand_name": "BB FM Kigali",
            "user_action": "SUBSCRIBE_NOW",
            "return_url": PAYPAL_RETURN_URL,
            "cancel_url": PAYPAL_CANCEL_URL,
        },
    }
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            f"{PAYPAL_BASE}/v1/billing/subscriptions",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "PayPal-Request-Id": str(uuid.uuid4())},
            json=payload,
        )
    if r.status_code >= 300:
        logger.error("PayPal subscribe %s %s", r.status_code, r.text)
        raise HTTPException(502, f"PayPal create-subscription failed: {r.text}")
    data = r.json()
    approve_url = next((l["href"] for l in data.get("links", []) if l.get("rel") == "approve"), None)
    if not approve_url:
        raise HTTPException(502, "PayPal did not return an approval URL")
    # Persist pending payment
    now = datetime.now(timezone.utc)
    payment = {
        "id": data["id"],
        "reference": data["id"],
        "userId": user["id"],
        "plan": body.plan,
        "planLabel": plan_meta["label"],
        "amount": float(PAYPAL_PRICES[body.plan]),
        "currency": PAYPAL_CURRENCY,
        "method": "paypal",
        "status": "pending",
        "paypalSubscriptionId": data["id"],
        "createdAt": now.isoformat(),
    }
    await db.payments.insert_one(payment.copy())
    return {
        "subscriptionId": data["id"],
        "approveUrl": approve_url,
        "status": data.get("status", "APPROVAL_PENDING"),
    }


@api.post("/billing/paypal/verify/{subscription_id}")
async def paypal_verify(subscription_id: str, user = Depends(get_current_user)):
    """Called by the app after the WebView redirects back on approval — polls PayPal for real status."""
    token = await _paypal_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(
            f"{PAYPAL_BASE}/v1/billing/subscriptions/{subscription_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if r.status_code >= 300:
        raise HTTPException(502, f"PayPal fetch subscription failed: {r.text}")
    data = r.json()
    status_raw = (data.get("status") or "").upper()
    payment = await db.payments.find_one({"reference": subscription_id, "userId": user["id"]}, {"_id": 0})
    if not payment:
        raise HTTPException(404, "Payment record not found")
    final_status = "success" if status_raw in ("ACTIVE", "APPROVED") else \
                   "failed"  if status_raw in ("CANCELLED", "EXPIRED", "SUSPENDED") else "pending"
    await db.payments.update_one(
        {"reference": subscription_id},
        {"$set": {"status": final_status, "providerPayload": data, "updatedAt": datetime.now(timezone.utc).isoformat()}},
    )
    if final_status == "success":
        pm = PLAN_META[payment["plan"]]
        expires = datetime.now(timezone.utc) + timedelta(days=pm["days"])
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"tier": pm["tier"], "subscriptionExpiresAt": expires.isoformat(), "currentPlan": payment["plan"]}},
        )
    return {"status": final_status, "paypalStatus": status_raw, "subscriptionId": subscription_id}


@api.post("/billing/paypal/webhook")
async def paypal_webhook(request: Request):
    """Public webhook — configure this URL in PayPal Dashboard → Apps & Credentials → Webhooks."""
    raw = await request.body()
    try:
        payload = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid_json"}
    event_type = payload.get("event_type", "")
    resource = payload.get("resource", {}) or {}
    logger.info("PayPal webhook: %s", event_type)
    # OPTIONAL: verify signature if PAYPAL_WEBHOOK_ID is set (skipped when blank)
    if PAYPAL_WEBHOOK_ID:
        try:
            token = await _paypal_token()
            verify_body = {
                "auth_algo": request.headers.get("paypal-auth-algo"),
                "cert_url": request.headers.get("paypal-cert-url"),
                "transmission_id": request.headers.get("paypal-transmission-id"),
                "transmission_sig": request.headers.get("paypal-transmission-sig"),
                "transmission_time": request.headers.get("paypal-transmission-time"),
                "webhook_id": PAYPAL_WEBHOOK_ID,
                "webhook_event": payload,
            }
            async with httpx.AsyncClient(timeout=15.0) as c:
                vr = await c.post(
                    f"{PAYPAL_BASE}/v1/notifications/verify-webhook-signature",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=verify_body,
                )
            if vr.status_code >= 300 or vr.json().get("verification_status") != "SUCCESS":
                logger.warning("PayPal webhook signature verification failed: %s", vr.text)
                return {"ok": False, "error": "signature_verification_failed"}
        except Exception as e:
            logger.warning("PayPal webhook verify exception: %s", e)

    sub_id = resource.get("id") or resource.get("billing_agreement_id")
    if not sub_id:
        return {"ok": True}
    payment = await db.payments.find_one({"reference": sub_id}, {"_id": 0})
    if not payment:
        return {"ok": True, "note": "no matching payment"}
    if event_type in ("BILLING.SUBSCRIPTION.ACTIVATED", "PAYMENT.SALE.COMPLETED", "BILLING.SUBSCRIPTION.CREATED", "PAYMENT.CAPTURE.COMPLETED"):
        pm = PLAN_META[payment["plan"]]
        expires = datetime.now(timezone.utc) + timedelta(days=pm["days"])
        await db.payments.update_one({"reference": sub_id}, {"$set": {"status": "success", "providerPayload": payload, "updatedAt": datetime.now(timezone.utc).isoformat()}})
        await db.users.update_one({"id": payment["userId"]}, {"$set": {"tier": pm["tier"], "subscriptionExpiresAt": expires.isoformat(), "currentPlan": payment["plan"]}})
    elif event_type in ("BILLING.SUBSCRIPTION.CANCELLED", "BILLING.SUBSCRIPTION.EXPIRED", "BILLING.SUBSCRIPTION.SUSPENDED"):
        await db.payments.update_one({"reference": sub_id}, {"$set": {"status": "failed", "providerPayload": payload, "updatedAt": datetime.now(timezone.utc).isoformat()}})
        await db.users.update_one({"id": payment["userId"]}, {"$set": {"tier": "free"}})
    return {"ok": True}


@api.get("/billing/paypal/config")
async def paypal_config(user = Depends(get_current_user)):
    """Frontend fetches non-secret PayPal config for display (currency, prices, return URLs)."""
    return {
        "env": PAYPAL_ENV,
        "currency": PAYPAL_CURRENCY,
        "prices": PAYPAL_PRICES,
        "returnUrl": PAYPAL_RETURN_URL,
        "cancelUrl": PAYPAL_CANCEL_URL,
        "clientId": PAYPAL_CLIENT_ID,  # public — safe to expose
    }


# ---------- VOD one-time unlock (PayPal Orders API for non-premium users) ----------
@api.post("/billing/vod/{show_id}/create")
async def vod_purchase_create(show_id: str, user = Depends(get_current_user)):
    show = await db.shows.find_one({"id": show_id}, {"_id": 0})
    if not show:
        raise HTTPException(404, "Show not found")
    if user.get("tier") == "premium":
        return {"alreadyUnlocked": True, "reason": "premium tier"}
    owned = await db.vod_purchases.find_one({"userId": user["id"], "showId": show_id, "status": "success"}, {"_id": 0})
    if owned:
        return {"alreadyUnlocked": True, "reason": "already purchased"}
    token = await _paypal_token()
    order_body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": f"vod-{show_id}",
            "description": f"BB FM Kigali VOD: {show['title']}",
            "custom_id": f"{user['id']}|{show_id}",
            "amount": {"currency_code": "EUR", "value": VOD_PRICE_EUR},
        }],
        "application_context": {
            "brand_name": "BB FM Kigali",
            "user_action": "PAY_NOW",
            "return_url": PAYPAL_RETURN_URL,
            "cancel_url": PAYPAL_CANCEL_URL,
            "shipping_preference": "NO_SHIPPING",
            "landing_page": "NO_PREFERENCE",  # PayPal decides card-guest vs login based on merchant settings
        },
    }
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            f"{PAYPAL_BASE}/v2/checkout/orders",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "PayPal-Request-Id": str(uuid.uuid4())},
            json=order_body,
        )
    if r.status_code >= 300:
        logger.error("PayPal order create failed %s %s", r.status_code, r.text)
        raise HTTPException(502, f"PayPal order create failed: {r.text[:200]}")
    data = r.json()
    approve_url = next((l["href"] for l in data.get("links", []) if l.get("rel") == "approve"), None)
    if not approve_url:
        raise HTTPException(502, "PayPal did not return an approval URL")
    await db.vod_purchases.insert_one({
        "id": data["id"],
        "orderId": data["id"],
        "userId": user["id"],
        "showId": show_id,
        "amount": float(VOD_PRICE_EUR),
        "currency": "EUR",
        "status": "pending",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    })
    return {"orderId": data["id"], "approveUrl": approve_url, "amount": VOD_PRICE_EUR, "currency": "EUR"}


@api.post("/billing/vod/{show_id}/capture/{order_id}")
async def vod_purchase_capture(show_id: str, order_id: str, user = Depends(get_current_user)):
    token = await _paypal_token()
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(
            f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
    if r.status_code >= 300:
        # If already captured, PayPal returns 422; treat that as success and just poll status
        async with httpx.AsyncClient(timeout=15.0) as c2:
            gr = await c2.get(
                f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
        if gr.status_code < 300:
            data = gr.json()
        else:
            logger.error("PayPal order capture failed %s %s", r.status_code, r.text)
            raise HTTPException(502, f"PayPal capture failed: {r.text[:200]}")
    else:
        data = r.json()
    status_raw = (data.get("status") or "").upper()
    final = "success" if status_raw == "COMPLETED" else "pending" if status_raw in ("APPROVED", "CREATED", "SAVED") else "failed"
    await db.vod_purchases.update_one(
        {"orderId": order_id, "userId": user["id"], "showId": show_id},
        {"$set": {"status": final, "providerPayload": data, "updatedAt": datetime.now(timezone.utc).isoformat()}},
    )
    return {"status": final, "paypalStatus": status_raw, "showId": show_id}


@api.get("/billing/vod/owned")
async def vod_owned(user = Depends(get_current_user)):
    """List show IDs the current user has unlocked (via purchase). Premium users own everything implicitly."""
    if user.get("tier") == "premium":
        return {"premium": True, "showIds": []}
    docs = await db.vod_purchases.find({"userId": user["id"], "status": "success"}, {"_id": 0, "showId": 1}).to_list(500)
    return {"premium": False, "showIds": [d["showId"] for d in docs]}


class VodMoMoIn(BaseModel):
    phone: str


@api.post("/billing/vod/{show_id}/momo")
async def vod_purchase_momo(show_id: str, body: VodMoMoIn, user = Depends(get_current_user)):
    """Buy a single VOD via MTN MoMo (BeSoft debit-credit). Non-premium users pay VOD_PRICE_RWF."""
    show = await db.shows.find_one({"id": show_id}, {"_id": 0})
    if not show:
        raise HTTPException(404, "Show not found")
    if user.get("tier") == "premium":
        return {"alreadyUnlocked": True, "reason": "premium tier"}
    owned = await db.vod_purchases.find_one({"userId": user["id"], "showId": show_id, "status": "success"}, {"_id": 0})
    if owned:
        return {"alreadyUnlocked": True, "reason": "already purchased"}
    payer = _normalize_msisdn(body.phone)
    if len(payer) < 10:
        raise HTTPException(400, "Invalid payer phone number")
    reference = f"vod-{show_id[:8]}-{uuid.uuid4().hex[:10]}"
    amount = float(VOD_PRICE_RWF)
    payload = {
        "idempotency_key": reference,
        "debit": {
            "amount": amount, "currency": "RWF", "payment_method": "mtn_momo_collection",
            "payer_identifier": payer, "description": f"BB FM VOD: {show['title']}",
            "idempotency_key": reference + "-d", "country": "RW",
            "metadata": {"userId": user["id"], "showId": show_id, "kind": "vod_unlock"},
        },
        "credits": [{
            "amount": amount, "currency": "RWF", "payment_method": "mtn_momo_disbursement",
            "payee_identifier": BESOFT_PAYOUT_MSISDN,
            "description": f"VOD payout — {show['title']}",
            "idempotency_key": reference + "-c1", "country": "RW",
        }],
    }
    await db.vod_purchases.insert_one({
        "id": reference, "orderId": reference, "reference": reference,
        "userId": user["id"], "showId": show_id,
        "amount": amount, "currency": "RWF", "method": "mtn_momo",
        "phone": payer, "status": "pending",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    })
    try:
        async with httpx.AsyncClient(timeout=30.0, verify=BESOFT_VERIFY_SSL) as c:
            r = await c.post(f"{BESOFT_BASE_URL}/public/payments/debit-credit", headers=_besoft_headers(), json=payload)
    except httpx.RequestError as e:
        await db.vod_purchases.update_one({"reference": reference}, {"$set": {"status": "failed", "error": str(e)}})
        raise HTTPException(502, f"Unable to reach payment provider: {e}")
    if r.status_code >= 300:
        await db.vod_purchases.update_one({"reference": reference}, {"$set": {"status": "failed", "error": r.text[:400]}})
        raise HTTPException(502, f"MoMo provider rejected the request: {r.text[:200]}")
    data = r.json().get("data") or {}
    debit = (data.get("debit") or {}) if isinstance(data, dict) else {}
    besoft_tx_id = debit.get("id") or data.get("id")
    besoft_status = (debit.get("status") or "pending").lower()
    normalized = besoft_status if besoft_status in ("pending", "processing", "success", "failed") else "pending"
    await db.vod_purchases.update_one({"reference": reference}, {"$set": {"besoftTxId": besoft_tx_id, "besoftPayload": data, "status": normalized}})
    return {"reference": reference, "besoftTxId": besoft_tx_id, "status": normalized, "amount": amount, "currency": "RWF"}


@api.get("/billing/vod/{show_id}/momo/{reference}")
async def vod_momo_status(show_id: str, reference: str, user = Depends(get_current_user)):
    p = await db.vod_purchases.find_one({"reference": reference, "userId": user["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Purchase not found")
    if p.get("status") in ("pending", "processing") and p.get("besoftTxId"):
        try:
            async with httpx.AsyncClient(timeout=15.0, verify=BESOFT_VERIFY_SSL) as c:
                r = await c.get(f"{BESOFT_BASE_URL}/public/payments/{p['besoftTxId']}/status", headers=_besoft_headers())
            if r.status_code == 200:
                data = (r.json().get("data") or {}) if isinstance(r.json(), dict) else {}
                raw_status = (data.get("status") or "").lower()
                new_status = "success" if raw_status in ("success", "completed") else \
                             "failed"  if raw_status in ("failed", "reversed", "expired", "cancelled") else \
                             "processing" if raw_status == "processing" else "pending"
                if new_status != p["status"]:
                    await db.vod_purchases.update_one({"reference": reference}, {"$set": {"status": new_status, "besoftStatusPayload": data, "updatedAt": datetime.now(timezone.utc).isoformat()}})
                    p["status"] = new_status
        except httpx.RequestError as e:
            logger.warning("BeSoft VOD status poll failed: %s", e)
    return {"reference": reference, "status": p["status"], "amount": p.get("amount"), "currency": p.get("currency")}


# ---------- Programs (curated show categories) ----------
@api.get("/programs")
async def list_programs():
    items = await db.programs.find({"isActive": {"$ne": False}}, {"_id": 0}).sort("order", 1).to_list(50)
    return items


# ---------- Settings ----------
@api.get("/settings")
async def get_settings():
    doc = await db.settings.find_one({"key": "global"}, {"_id": 0, "key": 0})
    if not doc:
        return {}
    return doc


# ---------- Admin ----------
class AdminSettingsIn(BaseModel):
    radioStreamUrl: Optional[str] = None      # audio-only FM stream (icecast/shoutcast)
    youtubeLiveUrl: Optional[str] = None      # https://www.youtube.com/watch?v=...
    stationName: Optional[str] = None
    stationTagline: Optional[str] = None
    frequency: Optional[str] = None
    logoUrl: Optional[str] = None


@api.get("/admin/settings")
async def admin_get_settings(_ = Depends(require_admin)):
    doc = await db.settings.find_one({"key": "global"}, {"_id": 0, "key": 0})
    return doc or {}


@api.put("/admin/settings")
async def admin_put_settings(body: AdminSettingsIn, _ = Depends(require_admin)):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    updates["updatedAt"] = datetime.now(timezone.utc).isoformat()
    await db.settings.update_one({"key": "global"}, {"$set": {"key": "global", **updates}}, upsert=True)
    # Reflect to radio_state so /radio/now-playing serves fresh data
    reflect: dict = {}
    if body.youtubeLiveUrl:
        # Extract video id
        vid = _extract_yt_id(body.youtubeLiveUrl)
        if vid:
            reflect["youtubeVideoId"] = vid
            reflect["youtubeWatchUrl"] = body.youtubeLiveUrl
            reflect["youtubeEmbedUrl"] = f"https://www.youtube.com/embed/{vid}?autoplay=1&playsinline=1&rel=0"
            reflect["coverImage"] = f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
    if body.radioStreamUrl:
        reflect["streamUrl"] = body.radioStreamUrl
    if body.stationName:
        reflect["showTitle"] = body.stationName + " Live"
    if reflect:
        await db.radio_state.update_one({"key": "current"}, {"$set": reflect}, upsert=True)
    doc = await db.settings.find_one({"key": "global"}, {"_id": 0, "key": 0})
    return doc


def _extract_yt_id(url: str) -> Optional[str]:
    """Best-effort extraction of YouTube video ID from a watch or short URL."""
    import re as _re
    m = _re.search(r"(?:v=|/embed/|youtu\.be/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


class ProgramIn(BaseModel):
    name: str
    description: Optional[str] = ""
    coverImage: Optional[str] = None
    embedUrl: Optional[str] = None          # YouTube playlist or single-video embed URL
    youtubePlaylistId: Optional[str] = None  # PLxxxx
    youtubeVideoId: Optional[str] = None     # single featured video
    order: int = 100
    isActive: bool = True


@api.get("/admin/programs")
async def admin_list_programs(_ = Depends(require_admin)):
    items = await db.programs.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    return items


@api.post("/admin/programs")
async def admin_create_program(body: ProgramIn, _ = Depends(require_admin)):
    doc = {"id": str(uuid.uuid4()), **body.dict(), "createdAt": datetime.now(timezone.utc).isoformat()}
    await db.programs.insert_one(doc.copy())
    return doc


@api.put("/admin/programs/{program_id}")
async def admin_update_program(program_id: str, body: ProgramIn, _ = Depends(require_admin)):
    await db.programs.update_one({"id": program_id}, {"$set": body.dict()})
    return await db.programs.find_one({"id": program_id}, {"_id": 0})


@api.delete("/admin/programs/{program_id}")
async def admin_delete_program(program_id: str, _ = Depends(require_admin)):
    await db.programs.delete_one({"id": program_id})
    return {"ok": True}


class ShowIn(BaseModel):
    title: str
    category: str = "vod"                # vod | podcast | interview
    description: Optional[str] = ""
    thumbnail: Optional[str] = None
    videoUrl: str                        # https://www.youtube.com/embed/... or full URL (we normalize)
    duration: Optional[str] = "0:00"
    premium: bool = False                 # deprecated flag (kept for backward compat)


@api.post("/admin/shows")
async def admin_create_show(body: ShowIn, _ = Depends(require_admin)):
    url = body.videoUrl
    if url and "youtube.com/watch" in url:
        vid = _extract_yt_id(url)
        if vid:
            url = f"https://www.youtube.com/embed/{vid}"
    doc = {
        "id": str(uuid.uuid4()),
        "title": body.title,
        "category": body.category.lower(),
        "description": body.description or "",
        "thumbnail": body.thumbnail or (f"https://img.youtube.com/vi/{_extract_yt_id(body.videoUrl)}/maxresdefault.jpg" if _extract_yt_id(body.videoUrl) else None),
        "videoUrl": url,
        "duration": body.duration or "0:00",
        "premium": body.premium,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await db.shows.insert_one(doc.copy())
    return doc


@api.delete("/admin/shows/{show_id}")
async def admin_delete_show(show_id: str, _ = Depends(require_admin)):
    await db.shows.delete_one({"id": show_id})
    return {"ok": True}


# ---------- Categories (dynamic, admin-managed) ----------
def _slugify(name: str) -> str:
    import re as _re
    s = (name or "").strip().lower()
    s = _re.sub(r"[^a-z0-9]+", "-", s)
    s = _re.sub(r"^-+|-+$", "", s)
    return s or "category"


class CategoryIn(BaseModel):
    name: str
    order: int = 100
    isActive: bool = True


@api.get("/categories")
async def list_categories():
    """Public — returns active categories sorted by order."""
    items = await db.categories.find(
        {"isActive": {"$ne": False}},
        {"_id": 0},
    ).sort("order", 1).to_list(200)
    return items


@api.get("/admin/categories")
async def admin_list_categories(_ = Depends(require_admin)):
    items = await db.categories.find({}, {"_id": 0}).sort("order", 1).to_list(200)
    return items


@api.post("/admin/categories")
async def admin_create_category(body: CategoryIn, _ = Depends(require_admin)):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "Category name is required")
    slug = _slugify(name)
    # Prevent duplicates by slug
    if await db.categories.find_one({"slug": slug}):
        raise HTTPException(409, f"Category '{name}' already exists")
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "slug": slug,
        "order": body.order,
        "isActive": body.isActive,
        "isDefault": False,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    await db.categories.insert_one(doc.copy())
    return doc


@api.put("/admin/categories/{category_id}")
async def admin_update_category(category_id: str, body: CategoryIn, _ = Depends(require_admin)):
    existing = await db.categories.find_one({"id": category_id})
    if not existing:
        raise HTTPException(404, "Category not found")
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "Category name is required")
    new_slug = _slugify(name)
    # Check duplicate slug on OTHER records
    dup = await db.categories.find_one({"slug": new_slug, "id": {"$ne": category_id}})
    if dup:
        raise HTTPException(409, f"Another category already uses '{name}'")
    old_slug = existing.get("slug")
    updates = {
        "name": name,
        "slug": new_slug,
        "order": body.order,
        "isActive": body.isActive,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    await db.categories.update_one({"id": category_id}, {"$set": updates})
    # If slug changed, cascade-update shows using the old slug
    if old_slug and old_slug != new_slug:
        await db.shows.update_many({"category": old_slug}, {"$set": {"category": new_slug}})
    return await db.categories.find_one({"id": category_id}, {"_id": 0})


@api.delete("/admin/categories/{category_id}")
async def admin_delete_category(category_id: str, _ = Depends(require_admin)):
    existing = await db.categories.find_one({"id": category_id})
    if not existing:
        raise HTTPException(404, "Category not found")
    slug = existing.get("slug")
    # Count shows referencing this category
    count = await db.shows.count_documents({"category": slug}) if slug else 0
    if count > 0:
        raise HTTPException(
            409,
            f"Cannot delete: {count} show(s) still use this category. Move or delete them first.",
        )
    await db.categories.delete_one({"id": category_id})
    return {"ok": True}


# ---------- Root health ----------
@api.get("/")
async def root():
    return {"service": "BB FM Kigali", "ok": True}


# ---------- Seed data ----------
async def seed():
    # ----- Categories (dynamic, admin-managed) -----
    default_cats = [
        {"name": "VOD", "slug": "vod", "order": 1},
        {"name": "Podcast", "slug": "podcast", "order": 2},
        {"name": "Interview", "slug": "interview", "order": 3},
    ]
    for c in default_cats:
        if not await db.categories.find_one({"slug": c["slug"]}):
            await db.categories.insert_one({
                "id": str(uuid.uuid4()),
                "name": c["name"],
                "slug": c["slug"],
                "order": c["order"],
                "isActive": True,
                "isDefault": True,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            })

    # ----- Shows (VOD/podcasts/interviews) -----
    if not await db.shows.count_documents({}):
        shows = [
            {"id": str(uuid.uuid4()), "title": "BB Kigali Featured Video", "category": "vod",
             "description": "Featured video from B&B Kigali 89.7 FM.",
             "thumbnail": "https://img.youtube.com/vi/Jsi8atSWGbg/maxresdefault.jpg",
             "videoUrl": "https://www.youtube.com/embed/Jsi8atSWGbg",
             "duration": "—", "premium": False,
             "createdAt": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "title": "Kigali Nights Live", "category": "vod",
             "description": "Live concert footage from downtown Kigali.",
             "thumbnail": "https://images.pexels.com/photos/26447525/pexels-photo-26447525.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "videoUrl": "https://www.youtube.com/embed/dQw4w9WgXcQ",
             "duration": "1:24:30", "premium": False,
             "createdAt": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "title": "Morning Show Recap", "category": "podcast",
             "description": "Highlights from this week's morning shows.",
             "thumbnail": "https://images.pexels.com/photos/6883808/pexels-photo-6883808.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "videoUrl": "https://www.youtube.com/embed/M7lc1UVf-VE",
             "duration": "42:10", "premium": False,
             "createdAt": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "title": "BBSPORTSTALK — Weekly Sports", "category": "interview",
             "description": "The most-watched sports program on B&B Kigali.",
             "thumbnail": "https://images.pexels.com/photos/28435464/pexels-photo-28435464.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "videoUrl": "https://www.youtube.com/embed/9bZkp7q19f0",
             "duration": "28:45", "premium": True,
             "createdAt": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "title": "B&B SPORTS BAR — Fan Reactions", "category": "vod",
             "description": "The bar. The talk. The passion.",
             "thumbnail": "https://images.pexels.com/photos/23384428/pexels-photo-23384428.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "videoUrl": "https://www.youtube.com/embed/kJQP7kiw5Fk",
             "duration": "58:12", "premium": True,
             "createdAt": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "title": "#IMPUMEKOYIWACU — Our Voices", "category": "podcast",
             "description": "Kinyarwanda podcast celebrating our voices.",
             "thumbnail": "https://images.pexels.com/photos/38586686/pexels-photo-38586686.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "videoUrl": "https://www.youtube.com/embed/y6120QOlsfU",
             "duration": "51:00", "premium": False,
             "createdAt": datetime.now(timezone.utc).isoformat()},
        ]
        await db.shows.insert_many(shows)
    else:
        # Ensure the user-specified featured video is present
        if not await db.shows.find_one({"videoUrl": {"$regex": "Jsi8atSWGbg"}}):
            await db.shows.insert_one({
                "id": str(uuid.uuid4()),
                "title": "BB Kigali Featured Video",
                "category": "vod",
                "description": "Featured video from B&B Kigali 89.7 FM.",
                "thumbnail": "https://img.youtube.com/vi/Jsi8atSWGbg/maxresdefault.jpg",
                "videoUrl": "https://www.youtube.com/embed/Jsi8atSWGbg",
                "duration": "—", "premium": False,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            })

    # ----- Programs (BBSPORTSTALK, B&B SPORTS BAR, #IMPUMEKOYIWACU) -----
    if not await db.programs.count_documents({}):
        programs = [
            {"id": str(uuid.uuid4()), "name": "BBSPORTSTALK", "order": 1,
             "description": "The most popular show on B&B Kigali — weekly sports talk in Kinyarwanda & English.",
             "coverImage": "https://images.pexels.com/photos/28435464/pexels-photo-28435464.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "youtubeVideoId": "Jsi8atSWGbg",
             "embedUrl": "https://www.youtube.com/embed?listType=search&list=BBSPORTSTALK+bbkigalifm",
             "isActive": True,
             "createdAt": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "name": "B&B SPORTS BAR", "order": 2,
             "description": "The bar. The talk. The passion. Fan reactions live.",
             "coverImage": "https://images.pexels.com/photos/23384428/pexels-photo-23384428.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "embedUrl": "https://www.youtube.com/embed?listType=search&list=B%26B+SPORTS+BAR+bbkigalifm",
             "isActive": True,
             "createdAt": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "name": "#IMPUMEKOYIWACU", "order": 3,
             "description": "Our voices. Kinyarwanda social-affairs podcast.",
             "coverImage": "https://images.pexels.com/photos/38586686/pexels-photo-38586686.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "embedUrl": "https://www.youtube.com/embed?listType=search&list=IMPUMEKOYIWACU+bbkigalifm",
             "isActive": True,
             "createdAt": datetime.now(timezone.utc).isoformat()},
        ]
        await db.programs.insert_many(programs)

    # ----- Global settings (admin-editable) -----
    if not await db.settings.count_documents({"key": "global"}):
        await db.settings.insert_one({
            "key": "global",
            "stationName": "B&B Kigali",
            "stationTagline": "#MuriSiporonIgitego",
            "frequency": "89.7 FM",
            "logoUrl": None,
            "radioStreamUrl": DEMO_AUDIO_STREAM,
            "youtubeLiveUrl": YOUTUBE_LIVE_URL,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        })

    if not await db.news.count_documents({}):
        now = datetime.now(timezone.utc)
        news = [
            {"id": str(uuid.uuid4()), "title": "B&B Kigali 89.7 FM launches new mobile app",
             "excerpt": "Listen live, watch VOD, and subscribe from your phone.",
             "body": "Today, B&B Kigali 89.7 FM proudly launches its brand new mobile app. #MuriSiporonIgitego — Listen live, watch on-demand videos, subscribe to premium, and follow every match from anywhere.",
             "thumbnail": "https://images.pexels.com/photos/28435464/pexels-photo-28435464.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "publishedAt": now.isoformat()},
            {"id": str(uuid.uuid4()), "title": "BBSPORTSTALK returns for a new season",
             "excerpt": "The most-watched sports program is back with weekly deep dives.",
             "body": "BBSPORTSTALK is back — with more analysis, more guests, and more #MuriSiporonIgitego. Tune in live every week or catch every episode on demand inside this app.",
             "thumbnail": "https://images.pexels.com/photos/26447525/pexels-photo-26447525.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "publishedAt": (now - timedelta(hours=5)).isoformat()},
            {"id": str(uuid.uuid4()), "title": "B&B SPORTS BAR — new episode this Friday",
             "excerpt": "Join the fans, live from the bar.",
             "body": "This Friday's B&B SPORTS BAR features the biggest fan panel yet.",
             "thumbnail": "https://images.pexels.com/photos/6883808/pexels-photo-6883808.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "publishedAt": (now - timedelta(days=1)).isoformat()},
            {"id": str(uuid.uuid4()), "title": "#IMPUMEKOYIWACU: our new season is here",
             "excerpt": "The voices of our community — a fresh season.",
             "body": "New episodes weekly. Real stories from Rwandans, for Rwandans.",
             "thumbnail": "https://images.pexels.com/photos/23384428/pexels-photo-23384428.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "publishedAt": (now - timedelta(days=2)).isoformat()},
        ]
        await db.news.insert_many(news)

    if not await db.schedule.count_documents({}):
        sched = [
            {"id": str(uuid.uuid4()), "order": 1, "time": "06:00 - 10:00", "showTitle": "Morning Drive", "djName": "DJ Karisa", "isLive": True},
            {"id": str(uuid.uuid4()), "order": 2, "time": "10:00 - 13:00", "showTitle": "Kigali Beats", "djName": "MC Ineza", "isLive": False},
            {"id": str(uuid.uuid4()), "order": 3, "time": "13:00 - 16:00", "showTitle": "Afternoon Groove", "djName": "DJ Muteti", "isLive": False},
            {"id": str(uuid.uuid4()), "order": 4, "time": "16:00 - 19:00", "showTitle": "Rush Hour", "djName": "DJ Mugabo", "isLive": False},
            {"id": str(uuid.uuid4()), "order": 5, "time": "19:00 - 22:00", "showTitle": "Night Vibes", "djName": "DJ Uwase", "isLive": False},
        ]
        await db.schedule.insert_many(sched)

    if not await db.radio_state.count_documents({}):
        await db.radio_state.insert_one({
            "key": "current",
            "streamUrl": DEMO_AUDIO_STREAM,
            "youtubeVideoId": YOUTUBE_LIVE_ID,
            "youtubeEmbedUrl": YOUTUBE_EMBED_URL,
            "youtubeWatchUrl": YOUTUBE_LIVE_URL,
            "showTitle": "BB FM Kigali Live",
            "djName": "Live on YouTube",
            "description": "Watch BB FM Kigali live — streaming 24/7 from Rwanda.",
            "coverImage": f"https://img.youtube.com/vi/{YOUTUBE_LIVE_ID}/maxresdefault.jpg",
            "isLive": True,
        })
    else:
        # Ensure existing radio_state row is updated with YouTube live details on redeploy
        await db.radio_state.update_one(
            {"key": "current"},
            {"$set": {
                "youtubeVideoId": YOUTUBE_LIVE_ID,
                "youtubeEmbedUrl": YOUTUBE_EMBED_URL,
                "youtubeWatchUrl": YOUTUBE_LIVE_URL,
                "showTitle": "BB FM Kigali Live",
                "djName": "Live on YouTube",
                "description": "Watch BB FM Kigali live — streaming 24/7 from Rwanda.",
                "coverImage": f"https://img.youtube.com/vi/{YOUTUBE_LIVE_ID}/maxresdefault.jpg",
                "isLive": True,
            }}
        )


@app.on_event("startup")
async def on_startup():
    await seed()
    logger.info("BB FM Kigali seed complete")


@app.on_event("shutdown")
async def on_shutdown():
    client.close()


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
