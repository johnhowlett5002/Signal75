#!/usr/bin/env python3
"""
Signal 75 — MailerLite Integration
Handles referral email capture, tagging, and welcome sequences
Used by the referral webhook endpoint
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

MAILERLITE_KEY = os.environ.get("MAILERLITE_API_KEY", "")
MAILERLITE_GROUP_ID = os.environ.get("MAILERLITE_GROUP_ID", "")
MAILERLITE_BASE = "https://connect.mailerlite.com/api"

def api_request(method, endpoint, data=None):
    """Make a MailerLite API request."""
    url = f"{MAILERLITE_BASE}{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {MAILERLITE_KEY}"
    }
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise Exception(f"MailerLite API error {e.code}: {error_body}")

def subscribe_referral(email, referrer_id, utm_source="referral"):
    """
    Subscribe a new user who signed up via referral link.
    Tags them with referrer ID so we know who referred them.
    Adds to Signal75 group for welcome sequence.
    
    Args:
        email: new subscriber's email
        referrer_id: the Signal 75 user ID of person who shared the link
        utm_source: tracking source
    
    Returns:
        subscriber data dict
    """
    if not MAILERLITE_KEY:
        raise Exception("MAILERLITE_API_KEY not set")
    if not MAILERLITE_GROUP_ID:
        raise Exception("MAILERLITE_GROUP_ID not set")

    data = {
        "email": email,
        "groups": [MAILERLITE_GROUP_ID],
        "fields": {
            "referred_by": referrer_id,
            "signup_source": utm_source,
            "signup_date": datetime.now(timezone.utc).isoformat()
        },
        "status": "active"
    }

    # Create/update subscriber
    result = api_request("POST", "/subscribers", data)
    subscriber_id = result.get("data", {}).get("id")

    print(f"✅ Subscriber added: {email} (referred by {referrer_id})")
    return result

def subscribe_direct(email, source="direct"):
    """
    Subscribe a user who signed up directly (not via referral).
    Used for the email capture form on the site.
    """
    if not MAILERLITE_KEY:
        raise Exception("MAILERLITE_API_KEY not set")
    if not MAILERLITE_GROUP_ID:
        raise Exception("MAILERLITE_GROUP_ID not set")

    data = {
        "email": email,
        "groups": [MAILERLITE_GROUP_ID],
        "fields": {
            "signup_source": source,
            "signup_date": datetime.now(timezone.utc).isoformat()
        },
        "status": "active"
    }

    result = api_request("POST", "/subscribers", data)
    print(f"✅ Direct subscriber added: {email}")
    return result

def get_subscriber(email):
    """Look up a subscriber by email."""
    import urllib.parse
    encoded = urllib.parse.quote(email)
    try:
        return api_request("GET", f"/subscribers/{encoded}")
    except Exception:
        return None

def test_connection():
    """Test the MailerLite API connection."""
    try:
        result = api_request("GET", "/subscribers?limit=1")
        print("✅ MailerLite connection successful")
        return True
    except Exception as e:
        print(f"❌ MailerLite connection failed: {e}")
        return False

if __name__ == "__main__":
    # Test the connection
    test_connection()
