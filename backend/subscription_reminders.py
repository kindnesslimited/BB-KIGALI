"""Subscription expiry reminder scheduler.

Sends a friendly SMS/WhatsApp reminder to users whose subscription is about to expire.
Runs once every 12 hours. Deduplicates via db.subscription_reminders so we never
send the same reminder twice.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

REMINDER_DAYS_BEFORE = [3, 1]  # remind 3 days out and 1 day out
CHECK_INTERVAL_SECONDS = 12 * 3600


async def _send_one(send_fn, db, user: dict, days_left: int) -> None:
    phone = (user.get("phone") or "").strip()
    if not phone:
        return
    reminder_key = f"{user['id']}:{days_left}:{user.get('subscriptionExpiresAt')}"
    already = await db.subscription_reminders.find_one({"key": reminder_key})
    if already:
        return

    days_word = "1 day" if days_left == 1 else f"{days_left} days"
    exp = user.get("subscriptionExpiresAt", "").split("T")[0]
    tier = (user.get("tier") or "").capitalize()
    # Renew-Now deep link. bbfmkigali:// is the app scheme; the /renew route pre-selects the current
    # plan in the checkout screen. Also a web fallback so SMS on non-installers still opens the browser.
    from os import environ
    plan_key = user.get("currentPlan") or "basic_monthly"
    app_scheme = environ.get("APP_LINK_SCHEME", "bbfmkigali").strip()
    web_base = environ.get("PUBLIC_APP_URL", "https://radio-vod-platform.emergent.host").strip().rstrip("/")
    renew_link = f"{web_base}/renew?plan={plan_key}"
    msg = (
        f"BB FM Kigali: Your {tier or 'BB FM'} subscription expires in {days_word} "
        f"(on {exp}). Tap to renew: {renew_link}"
    )

    try:
        ok, resp = await send_fn(phone, msg)
    except Exception as e:
        ok, resp = False, f"error: {e}"

    await db.subscription_reminders.insert_one({
        "id": str(uuid.uuid4()),
        "key": reminder_key,
        "userId": user["id"],
        "phone": phone,
        "daysBefore": days_left,
        "subscriptionExpiresAt": user.get("subscriptionExpiresAt"),
        "sent": ok,
        "response": (resp or "")[:400],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    })
    logger.info("[subs-reminder] user=%s days=%s ok=%s", user["id"], days_left, ok)


async def run_reminder_pass(db, send_fn) -> dict:
    """One reminder pass. Returns { checked, sent, failed }."""
    stats = {"checked": 0, "sent": 0, "failed": 0}
    now = datetime.now(timezone.utc)
    for days in REMINDER_DAYS_BEFORE:
        target_start = (now + timedelta(days=days - 0.5)).isoformat()
        target_end = (now + timedelta(days=days + 0.5)).isoformat()
        cursor = db.users.find(
            {
                "subscriptionExpiresAt": {"$gte": target_start, "$lte": target_end},
                "phone": {"$nin": [None, ""]},
            },
            {"_id": 0},
        )
        async for user in cursor:
            stats["checked"] += 1
            try:
                await _send_one(send_fn, db, user, days)
                stats["sent"] += 1
            except Exception:
                stats["failed"] += 1
                logger.exception("[subs-reminder] send failed")
    logger.info("[subs-reminder] pass complete %s", stats)
    return stats


async def reminder_loop(db, send_fn):
    """Background task. Sleeps 60s on boot, then runs every CHECK_INTERVAL_SECONDS."""
    await asyncio.sleep(60)
    while True:
        try:
            await run_reminder_pass(db, send_fn)
        except Exception:
            logger.exception("[subs-reminder] loop crashed (will retry)")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
