from __future__ import annotations

import os
import requests
from typing import Dict, Any


def can_send_sms() -> bool:
    return bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("TWILIO_AUTH_TOKEN") and os.getenv("TWILIO_FROM_NUMBER"))


def can_send_email() -> bool:
    # You can swap to Mailgun/SMTP later.
    return bool(os.getenv("SENDGRID_API_KEY") and os.getenv("SENDGRID_FROM_EMAIL"))


def send_sms_twilio(to_number: str, body: str) -> Dict[str, Any]:
    """
    Sends SMS via Twilio. Requires:
      TWILIO_ACCOUNT_SID
      TWILIO_AUTH_TOKEN
      TWILIO_FROM_NUMBER
    """
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_num = os.getenv("TWILIO_FROM_NUMBER", "")

    if not (sid and token and from_num):
        raise RuntimeError("Twilio env vars missing (TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM_NUMBER)")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = {"From": from_num, "To": to_number, "Body": body}

    r = requests.post(url, data=data, auth=(sid, token), timeout=20)
    if r.status_code >= 400:
        raise RuntimeError(f"Twilio error {r.status_code}: {r.text[:300]}")
    j = r.json()
    return {"provider": "twilio", "sid": j.get("sid"), "status": j.get("status")}


def send_email_sendgrid(to_email: str, subject: str, body: str) -> Dict[str, Any]:
    """
    Sends Email via SendGrid v3 API. Requires:
      SENDGRID_API_KEY
      SENDGRID_FROM_EMAIL
    """
    api_key = os.getenv("SENDGRID_API_KEY", "")
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "")
    if not (api_key and from_email):
        raise RuntimeError("SendGrid env vars missing (SENDGRID_API_KEY/SENDGRID_FROM_EMAIL)")

    url = "https://api.sendgrid.com/v3/mail/send"
    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/plain", "value": body}],
    }

    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=20,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"SendGrid error {r.status_code}: {r.text[:300]}")
    return {"provider": "sendgrid", "status": "queued_or_sent"}
