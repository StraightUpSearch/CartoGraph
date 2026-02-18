"""
Celery task: webhook delivery

Signs the payload with HMAC-SHA256 using the endpoint's stored secret,
then POSTs it to the registered URL with retries.

Delivery headers:
  X-CartoGraph-Event: <event_type>
  X-CartoGraph-Signature-256: sha256=<hex_digest>
  X-CartoGraph-Delivery: <delivery_id>
  Content-Type: application/json
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from app.celery_app import celery_app
from app.config.variables import cg_settings

log = logging.getLogger(__name__)

_DELIVERY_TIMEOUT_S = 10


def _sign_payload(secret: str, raw_body: bytes) -> str:
    """Return sha256=<hex> HMAC signature over the raw JSON bytes."""
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@celery_app.task(
    name="app.webhook_tasks.deliver_webhook",
    bind=True,
    queue="webhook_delivery",
    max_retries=4,
    default_retry_delay=30,
)
def deliver_webhook(
    self: Any,
    webhook_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Deliver a webhook payload to the registered endpoint.

    Args:
        webhook_id: UUID string of the WebhookEndpoint record.
        event_type: Event type string (e.g. 'domain.updated').
        payload: Dict to be serialised and POSTed.

    Returns result summary dict (stored in Celery result backend).
    """
    # Import here to avoid circular import at module load time
    from sqlmodel import Session, select

    from app.core.db import engine
    from app.models import WebhookEndpoint

    delivery_id = str(uuid.uuid4())
    delivered_at = datetime.now(timezone.utc).isoformat()

    with Session(engine) as session:
        endpoint = session.get(WebhookEndpoint, uuid.UUID(webhook_id))
        if not endpoint:
            log.warning("deliver_webhook: endpoint %s not found — skipping", webhook_id)
            return {"status": "skipped", "reason": "endpoint_not_found"}
        if not endpoint.is_active:
            return {"status": "skipped", "reason": "endpoint_inactive"}

        url = endpoint.url
        secret = endpoint.secret
        event_types: list[str] = endpoint.event_types or []

    # Check the endpoint subscribes to this event type
    if event_types and event_type not in event_types:
        return {"status": "skipped", "reason": "event_type_not_subscribed"}

    body = json.dumps(
        {"event": event_type, "delivery_id": delivery_id, "data": payload},
        default=str,
    ).encode()
    signature = _sign_payload(secret, body)

    headers = {
        "Content-Type": "application/json",
        "X-CartoGraph-Event": event_type,
        "X-CartoGraph-Signature-256": signature,
        "X-CartoGraph-Delivery": delivery_id,
        "User-Agent": f"CartoGraph-Webhooks/{cg_settings.SCHEMA_VERSION}",
    }

    try:
        with httpx.Client(timeout=_DELIVERY_TIMEOUT_S) as client:
            response = client.post(url, content=body, headers=headers)
        response.raise_for_status()
        log.info(
            "deliver_webhook: %s → %s HTTP %s",
            event_type, url, response.status_code,
        )
        return {
            "status": "delivered",
            "http_status": response.status_code,
            "delivery_id": delivery_id,
            "delivered_at": delivered_at,
        }
    except httpx.HTTPStatusError as exc:
        log.warning(
            "deliver_webhook: HTTP %s from %s — retrying",
            exc.response.status_code, url,
        )
        raise self.retry(
            exc=exc,
            countdown=30 * (2 ** self.request.retries),
        )
    except httpx.RequestError as exc:
        log.warning("deliver_webhook: request error to %s: %s — retrying", url, exc)
        raise self.retry(
            exc=exc,
            countdown=30 * (2 ** self.request.retries),
        )
