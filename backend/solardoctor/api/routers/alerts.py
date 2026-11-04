"""alerts router — test delivery of inspection fault alerts."""
from __future__ import annotations

from fastapi import APIRouter

from solardoctor.api.schemas.responses import AlertTestOut
from solardoctor.core import alerts

router = APIRouter(tags=["alerts"])


@router.post("/alerts/test", response_model=AlertTestOut)
def send_test_alert():
    """Send a test alert through every configured channel.

    Always 200: an unconfigured channel reports status "not_configured" and a
    delivery failure reports "failed", so the console can show both inline.
    Sync `def` so the blocking HTTP/SMTP calls run in the thread pool.
    """
    return alerts.send_test_alert()
