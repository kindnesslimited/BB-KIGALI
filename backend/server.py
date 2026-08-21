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
    phone: str
    displayName: Optional[str] = None
    tier: Literal["free", "basic", "premium"] = "free"
    subscriptionExpiresAt: Optional[str] = None

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
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user:
        raise HTTPException(401, "User not found")
    # Check subscription expiry
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
        "phone": u["phone"],
        "displayName": u.get("displayName"),
        "tier": u.get("tier", "free"),
        "subscriptionExpiresAt": u.get("subscriptionExpiresAt"),
    }


PLAN_CATALOG = {
    "basic_monthly":   {"tier": "basic",   "amount": 1000,  "currency": "RWF", "period": "monthly", "days": 30,  "label": "Basic Monthly"},
    "basic_yearly":    {"tier": "basic",   "amount": 10000, "currency": "RWF", "period": "yearly",  "days": 365, "label": "Basic Yearly"},
    "premium_monthly": {"tier": "premium", "amount": 3000,  "currency": "RWF", "period": "monthly", "days": 30,  "label": "Premium Monthly"},
    "premium_yearly":  {"tier": "premium", "amount": 30000, "currency": "RWF", "period": "yearly",  "days": 365, "label": "Premium Yearly"},
}


# ---------- Auth ----------
@api.post("/auth/otp/start")
async def otp_start(body: OTPStartIn):
    phone = body.phone.strip()
    if len(phone) < 7:
        raise HTTPException(400, "Invalid phone number")
    await db.otp_challenges.update_one(
        {"phone": phone},
        {"$set": {
            "phone": phone,
            "code": MOCK_OTP_CODE,
            "attempts": 0,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    # MOCK: always return the test code in response for demo
    return {"ok": True, "message": "OTP sent. Use 123456 (demo mode).", "testCode": MOCK_OTP_CODE}


@api.post("/auth/otp/verify", response_model=AuthOut)
async def otp_verify(body: OTPVerifyIn):
    phone = body.phone.strip()
    challenge = await db.otp_challenges.find_one({"phone": phone}, {"_id": 0})
    if not challenge:
        raise HTTPException(401, "No OTP challenge. Request a new code.")
    if body.code.strip() != MOCK_OTP_CODE:
        await db.otp_challenges.update_one({"phone": phone}, {"$inc": {"attempts": 1}})
        raise HTTPException(401, "Invalid code")
    user = await db.users.find_one({"phone": phone}, {"_id": 0})
    if not user:
        user = {
            "id": str(uuid.uuid4()),
            "phone": phone,
            "displayName": None,
            "tier": "free",
            "subscriptionExpiresAt": None,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user.copy())
    await db.otp_challenges.delete_one({"phone": phone})
    return {"accessToken": sign_jwt(user["id"]), "user": user_public(user)}


@api.get("/auth/me", response_model=UserOut)
async def me(user = Depends(get_current_user)):
    return user_public(user)


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
    if show.get("premium") and user.get("tier", "free") == "free":
        return {**show, "locked": True, "videoUrl": None}
    return {**show, "locked": False}


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


# ---------- Root health ----------
@api.get("/")
async def root():
    return {"service": "BB FM Kigali", "ok": True}


# ---------- Seed data ----------
async def seed():
    if not await db.shows.count_documents({}):
        shows = [
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
            {"id": str(uuid.uuid4()), "title": "Exclusive: DJ Karisa Interview", "category": "interview",
             "description": "Behind the scenes with Kigali's top DJ.",
             "thumbnail": "https://images.pexels.com/photos/28435464/pexels-photo-28435464.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "videoUrl": "https://www.youtube.com/embed/9bZkp7q19f0",
             "duration": "28:45", "premium": True,
             "createdAt": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "title": "Rwanda Sound Sessions", "category": "vod",
             "description": "The best of Rwandan music, curated weekly.",
             "thumbnail": "https://images.pexels.com/photos/23384428/pexels-photo-23384428.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "videoUrl": "https://www.youtube.com/embed/kJQP7kiw5Fk",
             "duration": "58:12", "premium": True,
             "createdAt": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "title": "Afternoon Groove Podcast", "category": "podcast",
             "description": "Chill vibes for your afternoon commute.",
             "thumbnail": "https://images.pexels.com/photos/38586686/pexels-photo-38586686.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "videoUrl": "https://www.youtube.com/embed/y6120QOlsfU",
             "duration": "51:00", "premium": False,
             "createdAt": datetime.now(timezone.utc).isoformat()},
            {"id": str(uuid.uuid4()), "title": "Tech Talk Kigali", "category": "interview",
             "description": "Conversations with Rwandan tech leaders.",
             "thumbnail": "https://images.unsplash.com/photo-1485579149621-3123dd979885?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMjV8MHwxfHNlYXJjaHwxfHxsaXZlJTIwcmFkaW8lMjBtaWNyb3Bob25lJTIwZGFya3xlbnwwfHx8fDE3ODczMDcwNjF8MA&ixlib=rb-4.1.0&q=85",
             "videoUrl": "https://www.youtube.com/embed/oHg5SJYRHA0",
             "duration": "35:20", "premium": True,
             "createdAt": datetime.now(timezone.utc).isoformat()},
        ]
        await db.shows.insert_many(shows)

    if not await db.news.count_documents({}):
        now = datetime.now(timezone.utc)
        news = [
            {"id": str(uuid.uuid4()), "title": "BB FM launches new mobile app",
             "excerpt": "Listen live, watch VOD, and subscribe from your phone.",
             "body": "Today, BB FM Kigali proudly launches its brand new mobile app. Listeners across Rwanda can now enjoy live radio, on-demand videos, exclusive podcasts, and subscribe to premium content — all from the palm of their hand.",
             "thumbnail": "https://images.pexels.com/photos/28435464/pexels-photo-28435464.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "publishedAt": now.isoformat()},
            {"id": str(uuid.uuid4()), "title": "Kigali Festival Weekend Lineup Revealed",
             "excerpt": "Three days of live music, art and culture across the city.",
             "body": "The much-anticipated Kigali Festival returns this weekend with a stellar lineup of local and international artists. BB FM will broadcast live from the main stage.",
             "thumbnail": "https://images.pexels.com/photos/26447525/pexels-photo-26447525.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "publishedAt": (now - timedelta(hours=5)).isoformat()},
            {"id": str(uuid.uuid4()), "title": "New Morning Show Host Announced",
             "excerpt": "Meet the fresh voice waking up Kigali every weekday.",
             "body": "We are thrilled to announce our new morning show host — bringing energy, news, and the best music every weekday from 6am to 10am.",
             "thumbnail": "https://images.pexels.com/photos/6883808/pexels-photo-6883808.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
             "publishedAt": (now - timedelta(days=1)).isoformat()},
            {"id": str(uuid.uuid4()), "title": "Rwandan Artists Dominate Regional Charts",
             "excerpt": "A record-breaking year for Rwandan music across East Africa.",
             "body": "For the third quarter in a row, Rwandan artists have dominated the East African charts, cementing Rwanda's position as a rising force in African music.",
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
