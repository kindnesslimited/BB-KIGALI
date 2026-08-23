"""Admin activity audit log — records who did what and when."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def record(
    db,
    *,
    actor_id: str,
    actor_name: Optional[str] = None,
    actor_email: Optional[str] = None,
    actor_phone: Optional[str] = None,
    action: str,             # e.g. "user.create", "show.delete", "news.update"
    target_type: str,        # e.g. "user", "show", "news", "category", "payment"
    target_id: Optional[str] = None,
    summary: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Insert one audit log entry. Never raises — audit failures must not block business logic."""
    try:
        await db.audit_log.insert_one({
            "id": str(uuid.uuid4()),
            "actorId": actor_id,
            "actorName": actor_name,
            "actorEmail": actor_email,
            "actorPhone": actor_phone,
            "action": action,
            "targetType": target_type,
            "targetId": target_id,
            "summary": summary,
            "metadata": metadata or {},
            "createdAt": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        logger.exception("[audit] failed to record %s on %s", action, target_type)


def actor_from_user(user: dict) -> dict:
    return {
        "actor_id": user["id"],
        "actor_name": user.get("displayName") or user.get("email") or user.get("phone"),
        "actor_email": user.get("email"),
        "actor_phone": user.get("phone"),
    }
