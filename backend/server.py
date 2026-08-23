"""BB FM Kigali - Radio + VOD backend."""
import os
import uuid
import asyncio
import logging
import base64
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Literal

import jwt
import httpx
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Request
from fastapi.responses import HTMLResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from youtube_sync import sync_channel as _yt_sync_channel, periodic_sync_loop as _yt_periodic_loop  # noqa: E402
from apple_auth import verify_apple_identity_token  # noqa: E402
from object_storage import upload_image_bytes, read_object  # noqa: E402
from fastapi import UploadFile, File
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
# JWT_SECRET is required — never fall back to a hardcoded value (would allow attackers to forge tokens if env fails to load).
JWT_SECRET = os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY")
if not JWT_SECRET:
    # Local dev convenience: generate an ephemeral secret so the server can boot, but log loudly.
    import secrets as _secrets
    JWT_SECRET = _secrets.token_urlsafe(48)
    logging.warning("JWT_SECRET not set in environment — generated an ephemeral secret. Existing sessions will be invalidated. Set JWT_SECRET in .env for production.")
JWT_ALG = "HS256"
MOCK_OTP_CODE = "123456"
YOUTUBE_LIVE_ID = "wPD77ygQKfo"
YOUTUBE_LIVE_URL = f"https://www.youtube.com/watch?v={YOUTUBE_LIVE_ID}"
YOUTUBE_EMBED_URL = f"https://www.youtube.com/embed/{YOUTUBE_LIVE_ID}?autoplay=1&playsinline=1&rel=0"
DEMO_AUDIO_STREAM = "https://stream.zeno.fm/0r0xa792kwzuv"
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://radio-vod-platform.preview.emergentagent.com")
EMERGENT_AUTH_SESSION_URL = os.environ.get(
    "EMERGENT_AUTH_SESSION_URL",
    "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
)

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
# Admin emails — first-time Google / Apple sign-in from these emails auto-promotes to admin role
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}
VOD_PRICE_EUR = os.environ.get("VOD_PRICE_EUR", "1.00")
VOD_PRICE_RWF = os.environ.get("VOD_PRICE_RWF", "1000")

# Stripe (LIVE)
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_CURRENCY = os.environ.get("STRIPE_CURRENCY", "eur").lower()

STRIPE_EUR_PRICES = {
    "basic_monthly":   os.environ.get("PAYPAL_PRICE_BASIC_MONTHLY",   "1.00"),
    "basic_yearly":    os.environ.get("PAYPAL_PRICE_BASIC_YEARLY",   "10.00"),
    "premium_monthly": os.environ.get("PAYPAL_PRICE_PREMIUM_MONTHLY", "3.00"),
    "premium_yearly":  os.environ.get("PAYPAL_PRICE_PREMIUM_YEARLY", "30.00"),
}
STRIPE_INTERVAL = {
    "basic_monthly":   "month",
    "basic_yearly":    "year",
    "premium_monthly": "month",
    "premium_yearly":  "year",
}

try:
    import stripe  # noqa: E402
    if STRIPE_SECRET_KEY:
        stripe.api_key = STRIPE_SECRET_KEY
except Exception:  # pragma: no cover
    stripe = None  # type: ignore

# SMS providers — chained fallback (tries each provider in order, uses first success)
# ------------------------------------------------------------------
# Provider 1: Route Mobile SMSPLUS Bulk HTTP API
SMS_API_URL = os.environ.get("SMS_API_URL", "").strip()
SMS_USERNAME = os.environ.get("SMS_USERNAME", "").strip()
SMS_PASSWORD = os.environ.get("SMS_PASSWORD", "").strip()
SMS_SENDER_ID = os.environ.get("SMS_SENDER_ID", "BBKIGALI").strip()
SMS_VERIFY_SSL = os.environ.get("SMS_VERIFY_SSL", "false").lower() == "true"

# Provider 2: Twilio (global — accepts API key auth, no IP whitelist)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM = os.environ.get("TWILIO_FROM", "").strip()  # phone number or messaging service SID

# Provider 3: Africa's Talking (best for Rwanda — cheap, native, API-key auth)
AT_USERNAME = os.environ.get("AT_USERNAME", "").strip()
AT_API_KEY = os.environ.get("AT_API_KEY", "").strip()
AT_SENDER_ID = os.environ.get("AT_SENDER_ID", "").strip()  # optional

# Provider 4: WhatsApp (via whatsapp.nostress.vip or any custom endpoint)
WHATSAPP_API_URL = os.environ.get("WHATSAPP_API_URL", "").strip()          # e.g. https://whatsapp.nostress.vip/api/send-message
WHATSAPP_API_TOKEN = os.environ.get("WHATSAPP_API_TOKEN", "").strip()       # API key / token
WHATSAPP_SESSION_ID = os.environ.get("WHATSAPP_SESSION_ID", "").strip()     # session/instance ID (some services)

# Provider ordering (comma-separated). Providers not in list are skipped.
# Options: route_mobile, twilio, africas_talking, whatsapp
SMS_PROVIDER_ORDER = [
    p.strip() for p in os.environ.get(
        "SMS_PROVIDER_ORDER", "route_mobile,africas_talking,twilio,whatsapp"
    ).split(",") if p.strip()
]
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


async def get_optional_user(authorization: Optional[str] = Header(None)):
    """Same as get_current_user but returns None instead of raising when no/invalid token.

    Used on public browse endpoints (like /shows/{id}) so guests can PREVIEW content
    metadata without logging in first. Playback still requires a real subscription check.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        return await get_current_user(authorization)
    except HTTPException:
        return None



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
async def _sms_route_mobile(destination: str, message: str) -> tuple[bool, str]:
    """Route Mobile SMSPLUS Bulk HTTP API. Returns (ok, provider_response)."""
    if not SMS_API_URL or not SMS_USERNAME or not SMS_PASSWORD:
        return False, "not_configured"
    params = {
        "username": SMS_USERNAME,
        "password": SMS_PASSWORD,
        "type": "0",
        "dlr": "1",
        "destination": destination.lstrip("+"),
        "source": SMS_SENDER_ID,
        "message": message,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, verify=SMS_VERIFY_SSL) as c:
            r = await c.get(SMS_API_URL, params=params)
    except httpx.RequestError as e:
        return False, f"network:{e}"
    body = (r.text or "").strip()
    logger.info("[route_mobile] %s %s", r.status_code, body[:200])
    return (body.startswith("1701") and r.status_code < 400), body


async def _sms_twilio(destination: str, message: str) -> tuple[bool, str]:
    """Twilio SMS API. Uses HTTP Basic auth with SID + auth token."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM:
        return False, "not_configured"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    dst = destination if destination.startswith("+") else "+" + destination.lstrip("+")
    from_field = TWILIO_FROM.strip()
    payload = {"To": dst, "Body": message}
    if from_field.startswith("MG"):
        payload["MessagingServiceSid"] = from_field
    else:
        payload["From"] = from_field
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(url, data=payload, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN))
    except httpx.RequestError as e:
        return False, f"network:{e}"
    logger.info("[twilio] %s %s", r.status_code, r.text[:200])
    return (200 <= r.status_code < 300), r.text[:200]


async def _sms_africas_talking(destination: str, message: str) -> tuple[bool, str]:
    """Africa's Talking SMS API — great for Rwanda MTN/Airtel."""
    if not AT_USERNAME or not AT_API_KEY:
        return False, "not_configured"
    # Production endpoint; sandbox users have a different URL but same shape
    url = "https://api.africastalking.com/version1/messaging"
    dst = destination if destination.startswith("+") else "+" + destination.lstrip("+")
    headers = {"apiKey": AT_API_KEY, "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    data = {"username": AT_USERNAME, "to": dst, "message": message}
    if AT_SENDER_ID:
        data["from"] = AT_SENDER_ID
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.post(url, data=data, headers=headers)
    except httpx.RequestError as e:
        return False, f"network:{e}"
    body = r.text[:300]
    logger.info("[africas_talking] %s %s", r.status_code, body)
    if r.status_code >= 300:
        return False, body
    try:
        j = r.json()
        recipients = j.get("SMSMessageData", {}).get("Recipients", [])
        # Success = at least one recipient status "Success"
        ok = any((rec.get("status") == "Success") for rec in recipients)
        return ok, body
    except Exception:
        return False, body


async def _sms_whatsapp(destination: str, message: str) -> tuple[bool, str]:
    """Send OTP via WhatsApp using the nostress.vip API.

    Documented format (https://whatsapp.nostress.vip/api/):
      POST https://whatsapp.nostress.vip/api_com.php
      Content-Type: application/json
      {"action":"send","auth":"<token>","tel":"<E.164 without +>","msg":"<text>"}
      → response {"code":"110","status":"request accepted","output":"Message sent"} on success
      → response {"code":"101","status":"Error: invalid token"} etc on failure
    """
    if not WHATSAPP_API_URL or not WHATSAPP_API_TOKEN:
        return False, "not_configured"
    tel = destination.lstrip("+").strip()
    payload = {
        "action": "send",
        "auth": WHATSAPP_API_TOKEN,
        "tel": tel,
        "msg": message,
    }
    if WHATSAPP_SESSION_ID:
        payload["session"] = WHATSAPP_SESSION_ID
    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(WHATSAPP_API_URL, json=payload, headers={"Content-Type": "application/json"})
    except httpx.RequestError as e:
        return False, f"network:{e}"
    body_txt = (r.text or "").strip()
    logger.info("[whatsapp] %s %s", r.status_code, body_txt[:200])
    if r.status_code >= 300:
        return False, body_txt[:200]
    # Parse structured response
    try:
        j = r.json()
        code = str(j.get("code", "")).strip()
        status = j.get("status", "")
        # nostress.vip uses code "110" for success ("request accepted")
        if code == "110" or "accepted" in status.lower() or "sent" in str(j.get("output", "")).lower():
            return True, f"code={code} {status}"[:120]
        return False, f"code={code} {status}"[:120]
    except Exception:
        # If not JSON, treat 200 as success only if body contains no "error"
        if "error" in body_txt.lower():
            return False, body_txt[:200]
        return True, body_txt[:120]


_SMS_PROVIDERS = {
    "route_mobile":    _sms_route_mobile,
    "twilio":          _sms_twilio,
    "africas_talking": _sms_africas_talking,
    "whatsapp":        _sms_whatsapp,
}


async def _send_sms(destination: str, message: str) -> tuple[bool, str]:
    """Try each configured provider in SMS_PROVIDER_ORDER. First success wins.

    Also records every attempt into db.sms_deliveries for analytics.
    """
    attempts: list[str] = []
    winning_provider = None
    winning_resp = ""
    now_iso = datetime.now(timezone.utc).isoformat()
    week_key = datetime.now(timezone.utc).strftime("%Y-W%V")
    for name in SMS_PROVIDER_ORDER:
        fn = _SMS_PROVIDERS.get(name)
        if not fn:
            continue
        ok, resp = await fn(destination, message)
        attempts.append(f"{name}:{resp[:60]}")
        # Record every attempt for analytics
        skipped = resp == "not_configured"
        try:
            await db.sms_deliveries.insert_one({
                "id": str(uuid.uuid4()),
                "provider": name,
                "destination": destination,
                "success": ok,
                "skipped": skipped,
                "response": resp[:400],
                "weekKey": week_key,
                "createdAt": now_iso,
            })
        except Exception as e:  # pragma: no cover
            logger.warning("Failed to record sms_delivery: %s", e)
        if ok:
            winning_provider = name
            winning_resp = resp
            logger.info("[sms] delivered via %s (attempts: %d)", name, len(attempts))
            return True, f"{name}|{resp}"
    combined = " | ".join(attempts) if attempts else "no_providers_configured"
    logger.warning("[sms] all providers failed: %s", combined)
    return False, combined


@api.post("/auth/otp/start")
async def otp_start(body: OTPStartIn):
    phone = body.phone.strip()
    if len(phone) < 7:
        raise HTTPException(400, "Invalid phone number")

    normalized = phone.lstrip("+").strip()
    is_admin_phone = phone in ADMIN_PHONES or normalized in ADMIN_PHONES

    # Any provider configured?
    any_provider_ready = any([
        SMS_API_URL and SMS_USERNAME and SMS_PASSWORD,
        TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM,
        AT_USERNAME and AT_API_KEY,
        WHATSAPP_API_URL and WHATSAPP_API_TOKEN,
    ])

    # Generate a fresh 6-digit code. Admin phones + missing SMS credentials => keep the universal test code 123456.
    if is_admin_phone or not any_provider_ready:
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

    # Attempt to send via the SMS provider chain. Non-fatal — falls through to dev code if all fail.
    sms_sent = False
    provider_resp = "sms_not_attempted"
    if not is_admin_phone and any_provider_ready:
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
        # provider_resp is "name|response" — extract provider name for user feedback
        provider_name = provider_resp.split("|", 1)[0]
        resp["message"] = f"OTP sent via {provider_name.replace('_', ' ')}."
        resp["provider"] = provider_name
    else:
        resp["message"] = "OTP recorded. If you don't receive it in 1 minute, contact support."
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
                EMERGENT_AUTH_SESSION_URL,
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
        is_admin = email in ADMIN_EMAILS
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
        # Re-promote to admin if email is in ADMIN_EMAILS but role isn't admin yet
        if email in ADMIN_EMAILS and user.get("role") != "admin":
            updates["role"] = "admin"
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


# ---------- Sign in with Apple ----------
class AppleSignInIn(BaseModel):
    identityToken: str
    fullName: Optional[str] = None
    email: Optional[str] = None


@api.post("/auth/apple", response_model=AuthOut)
async def auth_apple(body: AppleSignInIn):
    """Sign in with Apple. Verifies the identity token against Apple's JWKS.

    Apple returns fullName + email ONLY on first sign-in — persist them then and NEVER overwrite later.
    """
    try:
        claims = await verify_apple_identity_token(body.identityToken)
    except ValueError as e:
        raise HTTPException(401, str(e))

    apple_sub = claims.get("sub")
    if not apple_sub:
        raise HTTPException(401, "Apple token missing subject")
    token_email = claims.get("email") or body.email
    email_verified = claims.get("email_verified")
    is_private = claims.get("is_private_email") is True

    user = await db.users.find_one({"appleSub": apple_sub}, {"_id": 0})
    if not user and token_email:
        # Fall back to email lookup for accounts that first signed in via Google / phone with same email
        user = await db.users.find_one({"email": (token_email or "").lower()}, {"_id": 0})

    now_iso = datetime.now(timezone.utc).isoformat()
    if not user:
        is_admin_email = (token_email or "").lower() in ADMIN_EMAILS
        user = {
            "id": str(uuid.uuid4()),
            "phone": None,
            "email": (token_email or "").lower() or None,
            "displayName": (body.fullName or (token_email.split("@")[0] if token_email else None)),
            "picture": None,
            "tier": "free",
            "role": "admin" if is_admin_email else "user",
            "appleSub": apple_sub,
            "appleEmailPrivate": is_private,
            "subscriptionExpiresAt": None,
            "createdAt": now_iso,
        }
        await db.users.insert_one(user.copy())
    else:
        updates = {"appleSub": apple_sub}
        if body.fullName and not user.get("displayName"):
            updates["displayName"] = body.fullName
        if token_email and not user.get("email"):
            updates["email"] = token_email.lower()
        if is_private and not user.get("appleEmailPrivate"):
            updates["appleEmailPrivate"] = True
        if (user.get("email") or "").lower() in ADMIN_EMAILS and user.get("role") != "admin":
            updates["role"] = "admin"
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
        user.update(updates)

    return {"accessToken": sign_jwt(user["id"]), "user": user_public(user)}


# ---------- Account deletion (App Store 5.1.1(v) requirement) ----------
@api.delete("/auth/me")
async def delete_my_account(user = Depends(get_current_user)):
    """Permanently delete the requesting user account.

    Wipes user profile, active sessions, OTP challenges, and marks their payment history
    as anonymized (kept for legal/accounting record, not for reconstruction).
    """
    uid = user["id"]
    phone = user.get("phone")
    email = user.get("email")

    # 1. Delete auth artefacts
    await db.user_sessions.delete_many({"user_id": uid})
    if phone:
        await db.otp_challenges.delete_many({"phone": phone})

    # 2. Anonymize payments (keep for accounting, remove personal identifiers)
    await db.payments.update_many({"userId": uid}, {"$set": {"userId": f"deleted-{uid[:8]}", "phone": None, "deletedAt": datetime.now(timezone.utc).isoformat()}})
    await db.vod_purchases.update_many({"userId": uid}, {"$set": {"userId": f"deleted-{uid[:8]}", "phone": None, "deletedAt": datetime.now(timezone.utc).isoformat()}})

    # 3. Delete the user record itself
    await db.users.delete_one({"id": uid})

    logger.info("[delete-account] user=%s phone=%s email=%s wiped", uid, phone, email)
    return {"ok": True, "message": "Account and personal data deleted."}


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
async def get_show(show_id: str, user = Depends(get_optional_user)):
    show = await db.shows.find_one({"id": show_id}, {"_id": 0})
    if not show:
        raise HTTPException(404, "Show not found")
    # Guests (no login) see the preview only — locked with a login prompt.
    if not user:
        return {**show, "locked": True, "videoUrl": None, "unlockPrice": VOD_PRICE_EUR, "unlockCurrency": "EUR", "unlockPriceRwf": VOD_PRICE_RWF, "loginRequired": True}
    # Premium users get all VOD free. Non-premium users must purchase per-VOD (1 EUR).
    if user.get("tier") == "premium":
        # Also enforce expiry (once we have subscriptionExpiresAt in the future, _tier_refresh downgrades)
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
async def subscribe(body: SubscribeIn, current = Depends(get_current_user)):
    """DEPRECATED — this endpoint used to unconditionally grant a subscription without
    verifying any payment. It is now admin-only and only useful for manually granting
    complimentary/comp accounts. Regular users MUST use /billing/stripe/create-checkout,
    /billing/paypal/create-subscription or /billing/momo/initiate."""
    if current.get("role") != "admin":
        raise HTTPException(403, "Payment must be completed via Stripe, PayPal or MTN MoMo.")
    plan = PLAN_CATALOG.get(body.plan)
    if not plan:
        raise HTTPException(400, "Invalid plan")
    payment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires = now + timedelta(days=plan["days"])
    payment = {
        "id": payment_id,
        "userId": current["id"],
        "plan": body.plan,
        "planLabel": plan["label"],
        "amount": plan["amount"],
        "currency": plan["currency"],
        "method": body.method,
        "phone": body.phone,
        "status": "success",
        "note": "admin_comp",
        "createdAt": now.isoformat(),
    }
    await db.payments.insert_one(payment.copy())
    await db.users.update_one(
        {"id": current["id"]},
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
    """Normalize any Rwandan number to canonical E.164-without-plus: 250XXXXXXXXX (12 digits).

    Handles:
      +250 798 875 272 → 250798875272  (spaces, dashes, +)
      250 798 875 272  → 250798875272
      0798875272       → 250798875272  (local 10-digit starting with 0)
      798875272        → 250798875272  (9-digit MTN/Airtel format starting with 7)
      +2500798875272   → 250798875272  (country code + accidental leading 0)
    """
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 13 and digits.startswith("2500"):
        # Country code + accidental leading local zero
        return "250" + digits[4:]
    if len(digits) == 12 and digits.startswith("250"):
        return digits
    if len(digits) == 10 and digits.startswith("0"):
        return "250" + digits[1:]
    if len(digits) == 9 and digits.startswith("7"):
        return "250" + digits
    return digits


def _guard_payer_not_merchant(payer: str) -> None:
    """CRITICAL SAFETY CHECK: the customer's payer number MUST NOT equal the merchant collection account.

    The merchant (BESOFT_PAYOUT_MSISDN, e.g. +250 798 875 272) receives funds. It must NEVER be debited.
    Called on every MoMo debit request (both subscription and VOD). Raises 400 if the payer is the
    merchant account.
    """
    merchant = _normalize_msisdn(BESOFT_PAYOUT_MSISDN or "")
    if merchant and payer == merchant:
        logger.error("[momo][safety] Refusing to debit merchant account %s — payer must be a customer number, not the collection account.", merchant)
        raise HTTPException(
            400,
            "You entered our collection account. Please enter YOUR own Mobile Money number to pay.",
        )


@api.post("/billing/momo/initiate")
async def momo_initiate(body: MoMoInitiateIn, user = Depends(get_current_user)):
    plan = PLAN_CATALOG.get(body.plan)
    if not plan:
        raise HTTPException(400, "Invalid plan")
    payer = _normalize_msisdn(body.phone)
    if len(payer) < 10:
        raise HTTPException(400, "Invalid payer phone number")
    _guard_payer_not_merchant(payer)

    reference = f"bbfm-{uuid.uuid4().hex[:16]}"
    debit_amount = float(plan["amount"])
    # Merchant charge_percent is 0 on this account (confirmed via /transfer response). Adjust if BeSoft changes it.
    credit_amount = debit_amount

    async def _try_besoft(endpoint: str, payload: dict) -> tuple[int, str, dict]:
        """Attempt a BeSoft call and return (status, raw_text, parsed_data)."""
        async with httpx.AsyncClient(timeout=30.0, verify=BESOFT_VERIFY_SSL) as c:
            r = await c.post(f"{BESOFT_BASE_URL}{endpoint}", headers=_besoft_headers(), json=payload)
        parsed: dict = {}
        try:
            parsed = r.json() or {}
        except Exception:
            parsed = {}
        return r.status_code, r.text or "", parsed

    def _extract_debit(data: dict) -> tuple[str, str | None, str | None]:
        """Return (normalized_status, besoft_tx_id, failure_reason) from a BeSoft response.data payload."""
        d = (data.get("data") or {}) if isinstance(data, dict) else {}
        debit = (d.get("debit") or {}) if isinstance(d, dict) else {}
        besoft_id = debit.get("id") or d.get("id")
        raw_status = (debit.get("status") or d.get("status") or "pending").lower()
        norm = raw_status if raw_status in ("pending", "processing", "success", "failed") else "pending"
        return norm, besoft_id, debit.get("failure_reason") or d.get("failure_reason")

    # ---- /public/payments/transfer — debit-only payload; BeSoft auto-settles net amount to merchant's
    # configured payout_msisdn using charge_percent + disbursement method derived from payment_method.
    # Per BeSoft: mtn_momo_collection → mtn_momo_disbursement automatic settlement.
    payload = {
        "idempotency_key": reference,
        "debit": {
            "amount": debit_amount,
            "currency": plan["currency"],
            "payment_method": "mtn_momo_collection",
            "payer_identifier": payer,
            "description": f"BB FM Kigali — {plan['label']}",
            "country": "RW",
            "metadata": {"userId": user["id"], "plan": body.plan},
        },
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
        status_code, resp_text, resp_data = await _try_besoft("/public/payments/transfer", payload)
    except httpx.RequestError as e:
        await db.payments.update_one({"reference": reference}, {"$set": {"status": "failed", "error": f"network: {e}"}})
        raise HTTPException(502, f"Unable to reach payment provider: {e}")

    debit_norm, besoft_tx_id, failure_reason = _extract_debit(resp_data)
    attempt_note = "transfer"

    # ---- Persist and respond ----
    if status_code >= 300:
        logger.error("BeSoft transfer failed %s %s (attempt=%s)", status_code, resp_text[:200], attempt_note)
        provider_msg = (
            (resp_data.get("message") if isinstance(resp_data, dict) else None)
            or (resp_data.get("data", {}).get("message") if isinstance(resp_data, dict) else None)
            or failure_reason
            or resp_text[:200]
        )
        await db.payments.update_one(
            {"reference": reference},
            {"$set": {"status": "failed", "error": resp_text[:500], "failureReason": provider_msg, "besoftAttempt": attempt_note}},
        )
        return {
            "reference": reference,
            "besoftTxId": None,
            "status": "failed",
            "message": f"MoMo provider rejected the request: {provider_msg[:120]}",
            "failureReason": provider_msg,
            "amount": plan["amount"],
            "currency": plan["currency"],
            "pollUrl": f"{PUBLIC_BASE_URL}/api/billing/momo/{reference}",
        }

    # 2xx from BeSoft — apply normal handling
    data_top = resp_data.get("data") if isinstance(resp_data, dict) else {}
    besoft_status = debit_norm
    failure_reason_final = failure_reason
    normalized_status = besoft_status
    update_fields = {
        "besoftTxId": besoft_tx_id,
        "besoftPayload": data_top,
        "status": normalized_status,
        "besoftAttempt": attempt_note,
    }
    if failure_reason_final:
        update_fields["failureReason"] = failure_reason_final
    await db.payments.update_one({"reference": reference}, {"$set": update_fields})

    # Friendly message
    if normalized_status == "failed":
        friendly = "MoMo declined the payment"
        if failure_reason_final:
            fr_lower = failure_reason_final.lower()
            if "insufficient" in fr_lower:
                friendly = "Insufficient MoMo balance. Please top up and try again."
            elif "invalid" in fr_lower and "number" in fr_lower:
                friendly = "MoMo number is invalid. Please check and try again."
            elif "not registered" in fr_lower or "not found" in fr_lower:
                friendly = "This number is not registered for MTN Mobile Money."
            elif "timeout" in fr_lower or "timed out" in fr_lower:
                friendly = "MoMo request timed out. Please try again."
            elif "http_400" in fr_lower or "provider error" in fr_lower:
                friendly = "MTN MoMo temporarily unavailable. Please try Card payment or try again in a few minutes."
            else:
                friendly = f"MoMo declined: {failure_reason_final[:120]}"
        message = friendly
    else:
        message = "Approve the payment on your phone. We'll notify you when it completes."

    return {
        "reference": reference,
        "besoftTxId": besoft_tx_id,
        "status": normalized_status,
        "message": message,
        "failureReason": failure_reason_final,
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
            "shipping_preference": "NO_SHIPPING",
            "payment_method": {
                "payer_selected": "PAYPAL",
                "payee_preferred": "UNRESTRICTED",
            },
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
            "landing_page": "BILLING",  # show card/guest form first, minimises friction for users without PayPal
            "payment_method": {
                "payer_selected": "PAYPAL",
                "payee_preferred": "UNRESTRICTED",
            },
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
    _guard_payer_not_merchant(payer)
    reference = f"vod-{show_id[:8]}-{uuid.uuid4().hex[:10]}"
    amount = float(VOD_PRICE_RWF)
    # /public/payments/transfer — debit-only payload; BeSoft auto-settles net amount to merchant.
    payload = {
        "idempotency_key": reference,
        "debit": {
            "amount": amount,
            "currency": "RWF",
            "payment_method": "mtn_momo_collection",
            "payer_identifier": payer,
            "description": f"BB FM VOD: {show['title']}",
            "country": "RW",
            "metadata": {"userId": user["id"], "showId": show_id, "kind": "vod_unlock"},
        },
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
            r = await c.post(f"{BESOFT_BASE_URL}/public/payments/transfer", headers=_besoft_headers(), json=payload)
    except httpx.RequestError as e:
        await db.vod_purchases.update_one({"reference": reference}, {"$set": {"status": "failed", "error": str(e)}})
        raise HTTPException(502, f"Unable to reach payment provider: {e}")
    if r.status_code >= 300:
        try:
            err_body = r.json() if r.text else {}
        except Exception:
            err_body = {}
        provider_msg = (
            (err_body.get("message") if isinstance(err_body, dict) else None)
            or (err_body.get("data", {}).get("message") if isinstance(err_body, dict) else None)
            or r.text[:200]
        )
        await db.vod_purchases.update_one({"reference": reference}, {"$set": {
            "status": "failed",
            "error": r.text[:400],
            "failureReason": provider_msg,
            "besoftAttempt": "transfer",
        }})
        return {"reference": reference, "status": "failed", "amount": amount, "currency": "RWF",
                "message": f"MoMo provider rejected the request: {str(provider_msg)[:120]}",
                "failureReason": provider_msg}
    data = r.json().get("data") or {}
    debit = (data.get("debit") or {}) if isinstance(data, dict) else {}
    besoft_tx_id = debit.get("id") or data.get("id")
    besoft_status = (debit.get("status") or data.get("status") or "pending").lower()
    failure_reason = debit.get("failure_reason") or data.get("failure_reason")
    normalized = besoft_status if besoft_status in ("pending", "processing", "success", "failed") else "pending"
    update_fields = {"besoftTxId": besoft_tx_id, "besoftPayload": data, "status": normalized, "besoftAttempt": "transfer"}
    if failure_reason:
        update_fields["failureReason"] = failure_reason
    await db.vod_purchases.update_one({"reference": reference}, {"$set": update_fields})

    message = "Approve the payment on your phone."
    if normalized == "failed":
        fr = (failure_reason or "").lower()
        if "insufficient" in fr:
            message = "Insufficient MoMo balance. Please top up and try again."
        elif "invalid" in fr and "number" in fr:
            message = "MoMo number is invalid. Please check and try again."
        elif "not registered" in fr or "not found" in fr:
            message = "This number is not registered for MTN Mobile Money."
        elif "timeout" in fr or "timed out" in fr:
            message = "MoMo request timed out. Please try again."
        elif failure_reason:
            message = f"MoMo declined: {failure_reason[:120]}"
        else:
            message = "MoMo declined the payment."
    return {"reference": reference, "besoftTxId": besoft_tx_id, "status": normalized, "amount": amount, "currency": "RWF", "message": message, "failureReason": failure_reason}


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


# ---------- Admin YouTube channel sync ----------
class YouTubeSyncIn(BaseModel):
    handle: Optional[str] = None  # override — default is YOUTUBE_HANDLE env


@api.post("/admin/youtube/sync")
async def admin_youtube_sync(body: YouTubeSyncIn | None = None, _ = Depends(require_admin)):
    handle = body.handle if body else None
    result = await _yt_sync_channel(db, handle=handle)
    return result


@api.get("/admin/youtube/status")
async def admin_youtube_status(_ = Depends(require_admin)):
    doc = await db.integration_state.find_one({"key": "youtube_sync"}, {"_id": 0})
    return doc or {"key": "youtube_sync", "lastSyncAt": None}


# ---------- Admin cover image upload (Emergent Object Storage) ----------
@api.post("/admin/uploads/image")
async def admin_upload_image(file: UploadFile = File(...), current = Depends(require_admin)):
    """Upload a cover image for a show / program / news item. Returns { url, storagePath }.

    The returned `url` is a fully-qualified backend URL — save it directly into shows.coverUrl.
    """
    contents = await file.read()
    try:
        result = await run_in_threadpool(
            upload_image_bytes,
            current["id"],
            contents,
            file.filename,
            file.content_type,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("[upload] failed")
        raise HTTPException(502, f"Upload failed: {e}")
    # Persist a record so we can attribute uploads later
    await db.uploads.insert_one({
        "id": str(uuid.uuid4()),
        "userId": current["id"],
        "storagePath": result["storagePath"],
        "contentType": result["contentType"],
        "size": result["size"],
        "filename": file.filename,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    })
    public_url = f"{PUBLIC_BASE_URL}/api/uploads/{result['storagePath']}"
    return {"url": public_url, "storagePath": result["storagePath"], "contentType": result["contentType"]}


@api.get("/uploads/{full_path:path}")
async def read_upload(full_path: str):
    """Public read endpoint. Anyone can view an uploaded cover image (they're not private)."""
    try:
        data, content_type = await run_in_threadpool(read_object, full_path)
    except Exception:
        raise HTTPException(404, "Image not found")
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})


# ---------- Admin Users management ----------
class AdminUserRoleIn(BaseModel):
    role: Literal["user", "admin"]


class AdminInviteIn(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    role: Literal["user", "admin"] = "admin"
    displayName: Optional[str] = None


def _clean_user(u: dict) -> dict:
    """Strip internal fields from a user document for admin API responses."""
    return {
        "id": u.get("id"),
        "phone": u.get("phone"),
        "email": u.get("email"),
        "displayName": u.get("displayName"),
        "picture": u.get("picture"),
        "role": u.get("role", "user"),
        "tier": u.get("tier", "free"),
        "subscriptionExpiresAt": u.get("subscriptionExpiresAt"),
        "createdAt": u.get("createdAt"),
        "provider": u.get("provider"),
    }


@api.get("/admin/users")
async def admin_list_users(_ = Depends(require_admin), q: Optional[str] = None):
    """List all users. Optional ?q= filter searches phone/email/displayName."""
    query: dict = {}
    if q:
        import re as _re
        rx = _re.compile(_re.escape(q), _re.IGNORECASE)
        query = {"$or": [
            {"phone": {"$regex": rx}},
            {"email": {"$regex": rx}},
            {"displayName": {"$regex": rx}},
        ]}
    docs = await db.users.find(query, {"_id": 0}).sort("createdAt", -1).to_list(500)
    return [_clean_user(u) for u in docs]


@api.put("/admin/users/{user_id}/role")
async def admin_set_user_role(user_id: str, body: AdminUserRoleIn, current = Depends(require_admin)):
    """Promote/demote a user. Guard: an admin cannot demote themselves (avoid locking out the last admin)."""
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(404, "User not found")
    if user_id == current["id"] and body.role != "admin":
        raise HTTPException(400, "You cannot demote yourself. Ask another admin to do it.")
    if body.role != "admin" and target.get("role") == "admin":
        # About to demote an admin — make sure at least one other admin remains
        remaining = await db.users.count_documents({"role": "admin", "id": {"$ne": user_id}})
        if remaining == 0:
            raise HTTPException(400, "At least one admin must remain.")
    await db.users.update_one(
        {"id": user_id},
        {"$set": {"role": body.role, "updatedAt": datetime.now(timezone.utc).isoformat()}},
    )
    updated = await db.users.find_one({"id": user_id}, {"_id": 0})
    return _clean_user(updated)


@api.post("/admin/users/invite")
async def admin_invite_user(body: AdminInviteIn, _ = Depends(require_admin)):
    """Create an admin (or user) account by phone or email. If they already exist, updates their role."""
    if not body.phone and not body.email:
        raise HTTPException(400, "Provide phone or email")

    phone = body.phone.strip() if body.phone else None
    email = body.email.strip().lower() if body.email else None

    # Try to find existing user by phone or email
    existing = None
    if phone:
        # Match with or without leading + and prefix
        normalized = phone.lstrip("+")
        existing = await db.users.find_one({
            "$or": [{"phone": phone}, {"phone": normalized}, {"phone": "+" + normalized}],
        })
    if not existing and email:
        existing = await db.users.find_one({"email": email})

    now_iso = datetime.now(timezone.utc).isoformat()
    if existing:
        await db.users.update_one(
            {"id": existing["id"]},
            {"$set": {"role": body.role, "updatedAt": now_iso}},
        )
        u = await db.users.find_one({"id": existing["id"]}, {"_id": 0})
        return {**_clean_user(u), "created": False}

    # Create a brand-new stub user
    new_id = str(uuid.uuid4())
    doc = {
        "id": new_id,
        "phone": phone,
        "email": email,
        "displayName": body.displayName,
        "role": body.role,
        "tier": "free",
        "subscriptionExpiresAt": None,
        "createdAt": now_iso,
        "provider": "admin-invite",
    }
    await db.users.insert_one(doc.copy())
    return {**_clean_user(doc), "created": True}


@api.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, current = Depends(require_admin)):
    if user_id == current["id"]:
        raise HTTPException(400, "You cannot delete yourself.")
    target = await db.users.find_one({"id": user_id})
    if not target:
        raise HTTPException(404, "User not found")
    if target.get("role") == "admin":
        remaining = await db.users.count_documents({"role": "admin", "id": {"$ne": user_id}})
        if remaining == 0:
            raise HTTPException(400, "At least one admin must remain.")
    await db.users.delete_one({"id": user_id})
    return {"ok": True}


# ---------- Admin: Payments History + Revenue Dashboard ----------
@api.get("/admin/payments")
async def admin_payments_list(
    method: Optional[str] = None,
    status: Optional[str] = None,
    days: int = 90,
    limit: int = 100,
    _ = Depends(require_admin),
):
    """List recent payments with optional filters. Joins user phone/email."""
    if limit < 1: limit = 1
    if limit > 500: limit = 500
    if days < 1: days = 1
    if days > 365: days = 365
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q: dict = {"createdAt": {"$gte": cutoff}}
    if method:
        q["method"] = method
    if status:
        q["status"] = status
    docs = await db.payments.find(q, {"_id": 0}).sort("createdAt", -1).limit(limit).to_list(limit)
    # Enrich with user info
    user_ids = {d.get("userId") for d in docs if d.get("userId")}
    users_map: dict = {}
    if user_ids:
        u_docs = await db.users.find({"id": {"$in": list(user_ids)}}, {"_id": 0, "id": 1, "phone": 1, "email": 1, "displayName": 1}).to_list(500)
        users_map = {u["id"]: u for u in u_docs}
    out = []
    for d in docs:
        u = users_map.get(d.get("userId"), {}) if d.get("userId") else {}
        out.append({
            **d,
            "userPhone": u.get("phone"),
            "userEmail": u.get("email"),
            "userName": u.get("displayName"),
        })
    return out


@api.get("/admin/payments/summary")
async def admin_payments_summary(days: int = 30, _ = Depends(require_admin)):
    """Revenue totals + counts, broken down by method/currency/status."""
    if days < 1: days = 1
    if days > 365: days = 365
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # By method + currency + status (only sum successful for revenue)
    pipeline = [
        {"$match": {"createdAt": {"$gte": cutoff}}},
        {"$group": {
            "_id": {"method": "$method", "currency": "$currency", "status": "$status"},
            "count": {"$sum": 1},
            "amount": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, {"$ifNull": ["$amount", 0]}, 0]}},
        }},
    ]
    rows = await db.payments.aggregate(pipeline).to_list(200)

    # Aggregate by method
    by_method: dict = {}
    by_currency: dict = {}
    totals = {"success": 0, "pending": 0, "failed": 0, "count": 0}
    for r in rows:
        k = r["_id"]
        method = k.get("method") or "unknown"
        currency = (k.get("currency") or "").upper()
        status = k.get("status") or "unknown"
        count = r.get("count", 0)
        amount = float(r.get("amount", 0) or 0)
        totals["count"] += count
        if status in totals: totals[status] += count
        m = by_method.setdefault(method, {"count": 0, "byCurrency": {}})
        m["count"] += count
        if status == "success":
            m["byCurrency"].setdefault(currency, 0)
            m["byCurrency"][currency] += amount
            by_currency.setdefault(currency, 0)
            by_currency[currency] += amount

    # By-day series
    by_day_raw = await db.payments.aggregate([
        {"$match": {"createdAt": {"$gte": cutoff}, "status": "success"}},
        {"$group": {
            "_id": {"day": {"$substr": ["$createdAt", 0, 10]}, "currency": "$currency"},
            "amount": {"$sum": {"$ifNull": ["$amount", 0]}},
            "count": {"$sum": 1},
        }},
        {"$sort": {"_id.day": 1}},
    ]).to_list(2000)

    day_map: dict = {}
    for r in by_day_raw:
        day = r["_id"]["day"]
        cur = (r["_id"].get("currency") or "").upper()
        d = day_map.setdefault(day, {"day": day, "count": 0, "byCurrency": {}})
        d["count"] += r.get("count", 0)
        d["byCurrency"][cur] = d["byCurrency"].get(cur, 0) + float(r.get("amount", 0) or 0)
    by_day = sorted(day_map.values(), key=lambda x: x["day"])

    return {
        "windowDays": days,
        "totals": totals,
        "byMethod": [
            {"method": m, "count": v["count"], "revenue": v["byCurrency"]}
            for m, v in sorted(by_method.items(), key=lambda kv: -kv[1]["count"])
        ],
        "totalRevenue": by_currency,   # {"EUR": 42.0, "RWF": 12000, ...}
        "byDay": by_day,
    }


# ---------- Admin SMS providers ----------
@api.get("/admin/sms/providers")
async def admin_sms_providers(_ = Depends(require_admin)):
    """Report which SMS providers are configured. Booleans only — never expose secrets."""
    return {
        "order": SMS_PROVIDER_ORDER,
        "providers": {
            "route_mobile": {
                "configured": bool(SMS_API_URL and SMS_USERNAME and SMS_PASSWORD),
                "senderId": SMS_SENDER_ID if (SMS_API_URL and SMS_USERNAME) else None,
                "notes": "Requires IP whitelisting by Route Mobile.",
            },
            "twilio": {
                "configured": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM),
                "from": TWILIO_FROM or None,
                "notes": "Global. API-key auth, no IP whitelist. Sign up at twilio.com.",
            },
            "africas_talking": {
                "configured": bool(AT_USERNAME and AT_API_KEY),
                "senderId": AT_SENDER_ID or None,
                "notes": "Cheapest for Rwanda MTN/Airtel. API-key auth. Sign up at africastalking.com.",
            },
            "whatsapp": {
                "configured": bool(WHATSAPP_API_URL and WHATSAPP_API_TOKEN),
                "endpoint": WHATSAPP_API_URL or None,
                "notes": "Delivers OTP via WhatsApp instead of SMS.",
            },
        },
    }


class SmsTestIn(BaseModel):
    phone: str
    message: Optional[str] = None


@api.post("/admin/sms/test")
async def admin_sms_test(body: SmsTestIn, _ = Depends(require_admin)):
    """Send a real test SMS through the provider chain (admin only). Useful to confirm which providers work."""
    phone = body.phone.strip()
    if len(phone) < 7:
        raise HTTPException(400, "Invalid phone")
    normalized = phone.lstrip("+")
    text = (body.message or "").strip() or "BB Kigali 89.7 FM: SMS provider test — please ignore."
    sent, resp = await _send_sms(normalized, text)
    provider = None
    if sent and "|" in resp:
        provider = resp.split("|", 1)[0]
    return {"sent": sent, "provider": provider, "attempts": resp}


@api.get("/admin/sms/analytics")
async def admin_sms_analytics(days: int = 7, _ = Depends(require_admin)):
    """Provider analytics: attempts, deliveries, success rate. Filters last N days."""
    if days < 1: days = 1
    if days > 90: days = 90
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    pipeline_per_provider = [
        {"$match": {"createdAt": {"$gte": cutoff_iso}}},
        {"$group": {
            "_id": "$provider",
            "attempts": {"$sum": {"$cond": [{"$ne": ["$skipped", True]}, 1, 0]}},
            "delivered": {"$sum": {"$cond": [{"$eq": ["$success", True]}, 1, 0]}},
            "skipped": {"$sum": {"$cond": [{"$eq": ["$skipped", True]}, 1, 0]}},
        }},
        {"$sort": {"delivered": -1}},
    ]
    per_provider = await db.sms_deliveries.aggregate(pipeline_per_provider).to_list(20)

    providers_out = []
    total_attempts = 0
    total_delivered = 0
    for p in per_provider:
        attempts = p.get("attempts", 0) or 0
        delivered = p.get("delivered", 0) or 0
        skipped = p.get("skipped", 0) or 0
        rate = (delivered / attempts) if attempts else 0.0
        total_attempts += attempts
        total_delivered += delivered
        providers_out.append({
            "provider": p["_id"],
            "attempts": attempts,
            "delivered": delivered,
            "skipped": skipped,
            "successRate": round(rate, 4),
        })

    # Ensure all 4 known providers appear even with zero data
    known = {p["provider"] for p in providers_out}
    for name in _SMS_PROVIDERS.keys():
        if name not in known:
            providers_out.append({"provider": name, "attempts": 0, "delivered": 0, "skipped": 0, "successRate": 0.0})

    pipeline_by_day = [
        {"$match": {"createdAt": {"$gte": cutoff_iso}, "skipped": {"$ne": True}}},
        {"$group": {
            "_id": {"$substr": ["$createdAt", 0, 10]},
            "delivered": {"$sum": {"$cond": [{"$eq": ["$success", True]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$eq": ["$success", False]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    by_day_raw = await db.sms_deliveries.aggregate(pipeline_by_day).to_list(days + 5)
    by_day = [{"day": d["_id"], "delivered": d.get("delivered", 0), "failed": d.get("failed", 0)} for d in by_day_raw]

    return {
        "windowDays": days,
        "totals": {
            "attempts": total_attempts,
            "delivered": total_delivered,
            "successRate": round((total_delivered / total_attempts) if total_attempts else 0.0, 4),
        },
        "providers": providers_out,
        "byDay": by_day,
    }




# ---------- Stripe (LIVE — card payments, Android + Web only, hidden on iOS) ----------
class StripeCheckoutIn(BaseModel):
    purchase_type: Literal["subscription", "vod"]
    plan: Optional[Literal["basic_monthly", "basic_yearly", "premium_monthly", "premium_yearly"]] = None
    show_id: Optional[str] = None


def _stripe_ready() -> None:
    if not stripe or not STRIPE_SECRET_KEY:
        raise HTTPException(500, "Stripe is not configured on the server")


def _stripe_return_url() -> str:
    return f"{PUBLIC_BASE_URL}/api/billing/stripe/return?session_id={{CHECKOUT_SESSION_ID}}"


def _stripe_cancel_url() -> str:
    return f"{PUBLIC_BASE_URL}/api/billing/stripe/cancel"


@api.get("/billing/stripe/config")
async def stripe_config(_ = Depends(get_current_user)):
    """Frontend uses this to know whether to render the Stripe payment option."""
    return {
        "enabled": bool(stripe and STRIPE_SECRET_KEY),
        "publishableKey": STRIPE_PUBLISHABLE_KEY,
        "currency": STRIPE_CURRENCY,
    }


@api.post("/billing/stripe/create-checkout")
async def stripe_create_checkout(body: StripeCheckoutIn, user = Depends(get_current_user)):
    _stripe_ready()
    # Build a fixed server-side line item — client cannot alter price
    email = (user.get("email") or "").strip() or None
    if body.purchase_type == "subscription":
        if not body.plan or body.plan not in STRIPE_EUR_PRICES:
            raise HTTPException(400, "Invalid subscription plan")
        price = STRIPE_EUR_PRICES[body.plan]
        interval = STRIPE_INTERVAL[body.plan]
        label = PLAN_CATALOG[body.plan]["label"]
        line_item = {
            "price_data": {
                "currency": STRIPE_CURRENCY,
                "product_data": {"name": f"BB FM Kigali — {label}"},
                "unit_amount": int(round(float(price) * 100)),  # in cents
                "recurring": {"interval": interval},
            },
            "quantity": 1,
        }
        mode = "subscription"
        metadata = {"user_id": user["id"], "purchase_type": "subscription", "plan": body.plan}
    else:  # vod
        if not body.show_id:
            raise HTTPException(400, "show_id is required for VOD purchase")
        show = await db.shows.find_one({"id": body.show_id}, {"_id": 0, "title": 1})
        if not show:
            raise HTTPException(404, "Show not found")
        line_item = {
            "price_data": {
                "currency": STRIPE_CURRENCY,
                "product_data": {"name": f"BB FM VOD — {show.get('title', 'Unlock')}"},
                "unit_amount": int(round(float(VOD_PRICE_EUR) * 100)),
            },
            "quantity": 1,
        }
        mode = "payment"
        metadata = {"user_id": user["id"], "purchase_type": "vod", "show_id": body.show_id}

    idem_key = f"stripe-{uuid.uuid4().hex}"
    session_params = {
        "mode": mode,
        "line_items": [line_item],
        "metadata": metadata,
        "success_url": _stripe_return_url(),
        "cancel_url": _stripe_cancel_url(),
        "payment_method_types": ["card"],
        # This account has Managed Payments enabled by default which requires a tax code.
        # Disable it per-session so cards work immediately without configuring tax categories.
        "managed_payments": {"enabled": False},
    }
    if email:
        session_params["customer_email"] = email
    if mode == "subscription":
        session_params["subscription_data"] = {"metadata": metadata}
    try:
        session = stripe.checkout.Session.create(**session_params, idempotency_key=idem_key)
    except stripe.error.StripeError as e:  # type: ignore
        logger.error("Stripe create session error: %s", str(e))
        raise HTTPException(502, f"Stripe error: {getattr(e, 'user_message', None) or str(e)[:180]}")

    # Persist a pending payment record
    now_iso = datetime.now(timezone.utc).isoformat()
    payment_doc = {
        "id": session.id,
        "reference": session.id,
        "userId": user["id"],
        "plan": body.plan,
        "showId": body.show_id,
        "purchaseType": body.purchase_type,
        "amount": (line_item["price_data"]["unit_amount"] / 100),
        "currency": STRIPE_CURRENCY.upper(),
        "method": "stripe",
        "status": "pending",
        "stripeSessionId": session.id,
        "createdAt": now_iso,
    }
    await db.payments.insert_one(payment_doc.copy())

    return {
        "sessionId": session.id,
        "checkoutUrl": session.url,
        "publishableKey": STRIPE_PUBLISHABLE_KEY,
    }


async def _stripe_grant_from_session(session_obj) -> None:
    """Fulfil a paid Stripe checkout — grant subscription or VOD unlock. Idempotent."""
    md = getattr(session_obj, "metadata", None) or {}
    user_id = md.get("user_id")
    purchase_type = md.get("purchase_type")
    if not user_id:
        return
    now = datetime.now(timezone.utc)

    if purchase_type == "subscription":
        plan_key = md.get("plan")
        plan = PLAN_CATALOG.get(plan_key)
        if not plan:
            return
        expires_at = now + timedelta(days=plan["days"])
        await db.users.update_one(
            {"id": user_id},
            {"$set": {
                "tier": plan["tier"],
                "subscriptionExpiresAt": expires_at.isoformat(),
                "provider": "stripe",
                "updatedAt": now.isoformat(),
            }},
        )
    elif purchase_type == "vod":
        show_id = md.get("show_id")
        if not show_id:
            return
        # Add to unlockedVods on user
        await db.users.update_one({"id": user_id}, {"$addToSet": {"unlockedVods": show_id}})
        # Also record in vod_purchases for history
        await db.vod_purchases.update_one(
            {"userId": user_id, "showId": show_id, "method": "stripe"},
            {"$setOnInsert": {
                "id": str(uuid.uuid4()),
                "userId": user_id,
                "showId": show_id,
                "method": "stripe",
                "createdAt": now.isoformat(),
            }, "$set": {"status": "success"}},
            upsert=True,
        )

    # Mark payment as success
    await db.payments.update_one(
        {"stripeSessionId": session_obj.id},
        {"$set": {"status": "success", "updatedAt": now.isoformat()}},
    )


@api.get("/billing/stripe/session-status/{session_id}")
async def stripe_session_status(session_id: str, user = Depends(get_current_user)):
    _stripe_ready()
    # Verify this session belongs to this user via our payments collection
    p = await db.payments.find_one({"stripeSessionId": session_id, "userId": user["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Session not found for this user")

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError as e:  # type: ignore
        raise HTTPException(502, f"Stripe error: {str(e)[:200]}")

    payment_status = session.payment_status  # 'paid' | 'unpaid' | 'no_payment_required'
    session_status = session.status  # 'open' | 'complete' | 'expired'
    paid = payment_status == "paid"

    # Grant ONLY on confirmed payment. 'no_payment_required' is ONLY valid if the plan is 0-value
    # (we don't have any), so treat it as unpaid to be safe.
    if paid and p.get("status") != "success":
        try:
            await _stripe_grant_from_session(session)
        except Exception as e:  # pragma: no cover
            logger.error("Stripe direct grant error: %s", str(e))

    # If session is complete but payment_status is unpaid, this is a FAILED payment.
    # Mark our record so we do not silently retry-grant later.
    if session_status == "complete" and not paid:
        await db.payments.update_one(
            {"stripeSessionId": session_id},
            {"$set": {"status": "failed", "failureReason": f"payment_status={payment_status}"}},
        )

    return {
        "sessionId": session.id,
        "status": session_status,
        "paymentStatus": payment_status,
        "paid": paid,
        "purchaseType": (session.metadata or {}).get("purchase_type"),
        "plan": (session.metadata or {}).get("plan"),
        "showId": (session.metadata or {}).get("show_id"),
    }


@api.post("/billing/stripe/webhook")
async def stripe_webhook(request: Request):
    if not stripe:
        raise HTTPException(500, "Stripe not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        except ValueError:
            raise HTTPException(400, "Invalid payload")
        except stripe.error.SignatureVerificationError:  # type: ignore
            raise HTTPException(400, "Invalid signature")
    else:
        # If no webhook secret is configured (e.g. pre-launch), accept unsigned events but
        # log a warning. The user should set STRIPE_WEBHOOK_SECRET before production.
        import json as _json
        try:
            event = _json.loads(payload)
        except Exception:
            raise HTTPException(400, "Invalid payload")
        logger.warning("Stripe webhook received without signing secret configured; recommend setting STRIPE_WEBHOOK_SECRET.")

    event_id = event["id"] if isinstance(event, dict) else event.id
    # Idempotency guard
    if await db.stripe_events.find_one({"eventId": event_id}):
        return {"received": True, "idempotent": True}

    et = event["type"] if isinstance(event, dict) else event.type
    obj = event["data"]["object"] if isinstance(event, dict) else event.data.object

    if et in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        payment_status = obj.get("payment_status") if isinstance(obj, dict) else getattr(obj, "payment_status", None)
        if payment_status == "paid":
            # Convert dict → object-ish for shared helper
            class _Obj:
                pass
            fake = _Obj()
            fake.id = obj.get("id") if isinstance(obj, dict) else obj.id
            fake.metadata = obj.get("metadata") if isinstance(obj, dict) else obj.metadata
            await _stripe_grant_from_session(fake)

    await db.stripe_events.insert_one({
        "eventId": event_id,
        "eventType": et,
        "receivedAt": datetime.now(timezone.utc).isoformat(),
    })
    return {"received": True}


@api.get("/billing/stripe/return", response_class=HTMLResponse)
async def stripe_return(session_id: str):
    return HTMLResponse(
        content=f"""<!doctype html><html><head><meta charset=utf-8>
        <title>Payment received — BB FM Kigali</title>
        <style>body{{background:#0F0F13;color:#fff;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;margin:0;height:100vh;display:flex;align-items:center;justify-content:center;padding:2rem;text-align:center}}
        .box{{max-width:420px}}h1{{color:#FF6B00;letter-spacing:1px;font-size:20px;margin:0 0 8px}}p{{color:rgba(255,255,255,0.7);line-height:1.5;font-size:14px}}
        .id{{font-family:ui-monospace,monospace;font-size:11px;color:rgba(255,255,255,0.4);word-break:break-all;margin-top:1rem}}</style></head>
        <body><div class=box><h1>PAYMENT RECEIVED</h1>
        <p>Thanks for supporting B&amp;B Kigali 89.7 FM. Your subscription or unlock will activate automatically. Returning to the app…</p>
        <div class=id>Ref: {session_id}</div></div></body></html>""",
        status_code=200,
    )


@api.get("/billing/stripe/cancel", response_class=HTMLResponse)
async def stripe_cancel():
    return HTMLResponse(
        content="""<!doctype html><html><head><meta charset=utf-8><title>Payment cancelled</title>
        <style>body{background:#0F0F13;color:#fff;font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:0;height:100vh;display:flex;align-items:center;justify-content:center;text-align:center;padding:2rem}</style></head>
        <body><div><h1 style="color:#FF6B00">Payment cancelled</h1><p style="color:rgba(255,255,255,0.7)">You can retry anytime from the BB FM Kigali app.</p></div></body></html>""",
        status_code=200,
    )


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


@api.get("/health")
async def health():
    """Deployment readiness probe — verifies DB and env are ready."""
    try:
        await db.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "ok": db_ok,
        "service": "bb-fm-kigali",
        "db": "ok" if db_ok else "unreachable",
        "stripe": bool(STRIPE_SECRET_KEY),
        "sms_providers": SMS_PROVIDER_ORDER,
    }


# ---------- Seed data ----------
async def seed():
    # ----- Admin allowlist backfill: promote emails/phones to admin if user exists,
    #        create stub accounts for admin emails so they show up in Admin → Users -----
    if ADMIN_EMAILS:
        # Promote existing users
        promoted = await db.users.update_many(
            {"email": {"$in": list(ADMIN_EMAILS)}, "role": {"$ne": "admin"}},
            {"$set": {"role": "admin", "updatedAt": datetime.now(timezone.utc).isoformat()}},
        )
        if promoted.modified_count:
            logger.info("Promoted %s existing user(s) to admin via ADMIN_EMAILS", promoted.modified_count)
        # Ensure any pre-existing stubs also carry the provider tag for auditability
        await db.users.update_many(
            {"email": {"$in": list(ADMIN_EMAILS)}, "provider": {"$in": [None, ""]}},
            {"$set": {"provider": "admin-allowlist"}},
        )
        # Create stubs for emails that never signed in yet
        for email in ADMIN_EMAILS:
            if not await db.users.find_one({"email": email}):
                await db.users.insert_one({
                    "id": str(uuid.uuid4()),
                    "phone": None,
                    "email": email,
                    "displayName": email.split("@")[0],
                    "picture": None,
                    "tier": "free",
                    "role": "admin",
                    "subscriptionExpiresAt": None,
                    "provider": "admin-allowlist",
                    "createdAt": datetime.now(timezone.utc).isoformat(),
                })
                logger.info("Created admin stub for %s (first Google/Apple sign-in will attach)", email)

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
    # Kick off background YouTube sync (idempotent — no-op if YOUTUBE_API_KEY unset).
    if os.environ.get("YOUTUBE_API_KEY"):
        app.state._yt_task = asyncio.create_task(_yt_periodic_loop(db))
        logger.info("YouTube periodic sync started")


@app.on_event("shutdown")
async def on_shutdown():
    task = getattr(app.state, "_yt_task", None)
    if task:
        task.cancel()
    client.close()


app.include_router(api)


# Root-level /health for the deployment platform's readiness probe.
# (Emergent probes /health without the /api prefix.)
@app.get("/health")
async def app_health():
    try:
        await db.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {"ok": db_ok, "service": "bb-fm-kigali", "db": "ok" if db_ok else "unreachable"}


# ---- Privacy Policy — served straight from the backend so the in-app link always resolves.
LANDING_DIR = Path("/app/landing")


@app.get("/api/privacy", response_class=HTMLResponse)
async def api_privacy_policy():
    """The k8s ingress routes /api/* → this backend on port 8001, so this is the public URL for the app."""
    path = LANDING_DIR / "privacy.html"
    if not path.exists():
        raise HTTPException(404, "Privacy policy not published yet")
    return HTMLResponse(path.read_text(encoding="utf-8"))
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
