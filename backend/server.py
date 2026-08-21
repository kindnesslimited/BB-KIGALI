"""BB FM Kigali - Radio + VOD backend."""
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Literal

import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header
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


# ---------- MTN MoMo dedicated endpoints ----------
# These are the endpoints your real MTN MoMo integration (RequestToPay) will hit.
# Point your MoMo API "callbackHost" / "X-Callback-Url" at PUBLIC_BASE_URL + /api/billing/momo/callback
class MoMoInitiateIn(BaseModel):
    plan: Literal["basic_monthly", "basic_yearly", "premium_monthly", "premium_yearly"]
    phone: str  # payer MSISDN in E.164 e.g. +250788xxxxxx


@api.post("/billing/momo/initiate")
async def momo_initiate(body: MoMoInitiateIn, user = Depends(get_current_user)):
    plan = PLAN_CATALOG.get(body.plan)
    if not plan:
        raise HTTPException(400, "Invalid plan")
    reference = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payment = {
        "id": reference,
        "reference": reference,
        "userId": user["id"],
        "plan": body.plan,
        "planLabel": plan["label"],
        "amount": plan["amount"],
        "currency": plan["currency"],
        "method": "mtn_momo",
        "phone": body.phone,
        "status": "pending",
        "createdAt": now.isoformat(),
    }
    await db.payments.insert_one(payment.copy())
    # In production: call MTN MoMo RequestToPay API here with:
    #   X-Reference-Id: reference
    #   X-Callback-Url: PUBLIC_BASE_URL + /api/billing/momo/callback
    #   body { amount, currency: "RWF", externalId, payer:{partyIdType:"MSISDN", partyId: body.phone}, payerMessage, payeeNote }
    return {
        "reference": reference,
        "status": "pending",
        "message": "Approve the payment on your phone. We'll notify you when it completes.",
        "callbackUrl": f"{PUBLIC_BASE_URL}/api/billing/momo/callback",
        "pollUrl": f"{PUBLIC_BASE_URL}/api/billing/momo/{reference}",
    }


@api.post("/billing/momo/callback")
async def momo_callback(payload: dict):
    """Public webhook that MTN MoMo POSTs when the payer's transaction status changes.
    Whitelist this URL in your MoMo API sandbox/production dashboard as callbackHost."""
    logger.info("MoMo callback received: %s", payload)
    reference = payload.get("referenceId") or payload.get("externalId") or payload.get("reference")
    status_raw = (payload.get("status") or "").upper()
    if not reference:
        return {"ok": False, "error": "missing_reference"}
    payment = await db.payments.find_one({"reference": reference}, {"_id": 0})
    if not payment:
        return {"ok": False, "error": "unknown_reference"}
    final_status = "success" if status_raw in ("SUCCESSFUL", "SUCCESS", "COMPLETED") else \
                   "failed"  if status_raw in ("FAILED", "REJECTED", "CANCELLED", "EXPIRED") else \
                   "pending"
    await db.payments.update_one({"reference": reference}, {"$set": {
        "status": final_status,
        "providerPayload": payload,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }})
    if final_status == "success":
        plan = PLAN_CATALOG.get(payment["plan"])
        if plan:
            expires = datetime.now(timezone.utc) + timedelta(days=plan["days"])
            await db.users.update_one(
                {"id": payment["userId"]},
                {"$set": {"tier": plan["tier"], "subscriptionExpiresAt": expires.isoformat(), "currentPlan": payment["plan"]}},
            )
    return {"ok": True, "status": final_status, "reference": reference}


@api.get("/billing/momo/{reference}")
async def momo_status(reference: str, user = Depends(get_current_user)):
    p = await db.payments.find_one({"reference": reference, "userId": user["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Payment not found")
    return {"reference": reference, "status": p["status"], "amount": p["amount"], "currency": p["currency"]}


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
