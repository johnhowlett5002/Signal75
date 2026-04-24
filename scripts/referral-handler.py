#!/usr/bin/env python3
"""
Signal 75 — Referral Handler
Called when a user clicks a referral link and submits their email.
This runs as a serverless function (or can be called from the app directly).

Flow:
1. User visits signal75.co.uk?ref=ABC123
2. App stores ref ID in localStorage
3. User enters email to unlock Pick 2
4. App calls this handler with email + ref ID
5. Handler subscribes to MailerLite with referral tag
6. Handler notifies referrer they have a new referral

Since Signal 75 is static HTML, this logic runs client-side in the browser
using the MailerLite API directly from JavaScript.
This script shows the server-side equivalent for reference.
"""

import os
import json
import sys
sys.path.insert(0, os.path.dirname(__file__))
from mailerlite import subscribe_referral, subscribe_direct

def handle_referral(email, referrer_id):
    """
    Process a referral signup.
    Returns dict with success status and unlock level.
    """
    if not email or "@" not in email:
        return {"success": False, "error": "Invalid email"}

    try:
        # Subscribe with referral tag
        result = subscribe_referral(email, referrer_id)
        return {
            "success": True,
            "message": "Thanks! Pick 2 is now unlocked.",
            "subscriber_id": result.get("data", {}).get("id")
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def handle_direct_signup(email):
    """Process a direct email signup (no referral)."""
    if not email or "@" not in email:
        return {"success": False, "error": "Invalid email"}
    try:
        subscribe_direct(email)
        return {"success": True, "message": "You're on the list!"}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    # Test
    print("Referral handler ready")
