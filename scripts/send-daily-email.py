#!/usr/bin/env python3
"""
send-daily-email.py — Signal 75
Generates and sends daily picks email via Brevo.
Run after 10am picks generation.
"""
import json, subprocess, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

PICKS_JSON   = '/Users/johnhowlett/Signal75/picks.json'
PERF_JSON    = '/Users/johnhowlett/Signal75/performance.json'
BREVO_URL    = 'https://api.brevo.com/v3/smtp/email'
LIST_ID      = 2
SENDER_EMAIL = 'hello@signal75.co.uk'
SENDER_NAME  = 'Signal 75'
SITE_URL     = 'https://signal75.co.uk'

def get_brevo_key():
    result = subprocess.run(
        ['security', 'find-generic-password', '-a', 'signal75', '-s', 'brevo-api-key', '-w'],
        capture_output=True, text=True
    )
    return result.stdout.strip()

def load_json(path):
    with open(path) as f:
        return json.load(f)

def format_date_display(date_str):
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.strftime('%A %d %B %Y')
    except:
        return date_str

def format_time_uk(t):
    return t if t else '--:--'

def badge_label(badge):
    if 'Banker' in str(badge): return '🔥 Banker'
    if 'Strong' in str(badge): return '💪 Strong'
    if 'Each' in str(badge) or 'EW' in str(badge): return '🎯 Each Way'
    return '⚡ Signal'

def build_email_html(picks_data, perf_data):
    date_str = picks_data.get('date', '')
    date_display = format_date_display(date_str)
    mode = picks_data.get('mode', 'noBetDay')

    flat = picks_data.get('flat', [])
    jumps = picks_data.get('jumps', [])
    all_races = flat + jumps

    horses = []
    for race in all_races:
        for h in race.get('horses', []):
            horses.append({
                'name': h.get('name', ''),
                'course': race.get('course', ''),
                'time': race.get('time', ''),
                'odds': h.get('odds', 0),
                'badge': h.get('badge', 'Strong'),
                'score': h.get('signal_score', 0),
                'why': h.get('reason', ''),
                'jockey': h.get('jockey', ''),
                'form': h.get('formStr', ''),
            })

    # Performance summary
    bet_days = perf_data.get('completeDays', 0)
    profit = perf_data.get('totalProfit', 0)
    roi = perf_data.get('roi', 0)
    wins = perf_data.get('wins', 0)
    profit_str = f"+£{profit:.2f}" if profit >= 0 else f"-£{abs(profit):.2f}"
    profit_color = "#4CAF50" if profit >= 0 else "#F44336"

    # Build horse cards
    pick1_html = ''
    locked_html = ''

    if mode == 'noBetDay' or not horses:
        pick1_html = f'''
        <div style="background:#1a1a2e;border:1px solid rgba(240,192,64,0.2);border-radius:10px;padding:20px;text-align:center;margin-bottom:16px">
            <div style="font-size:48px;margin-bottom:12px">🔍</div>
            <div style="font-family:'Courier New',monospace;font-size:11px;color:#C8C8E0;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px">No Bet Day</div>
            <div style="color:#FFFFFF;font-size:15px;margin-bottom:8px">No horses cleared the Signal 75 threshold today</div>
            <div style="font-family:'Courier New',monospace;font-size:10px;color:#888;margin-bottom:8px">The model only picks when the data says so.</div>
            <div style="font-family:'Courier New',monospace;font-size:10px;color:#C8C8E0;line-height:1.6">Tomorrow Signal 75 will scan all UK races again.<br>When 3 horses clear the threshold — you'll be first to know.</div>
        </div>'''
    else:
        # Pick 1 — always free
        h = horses[0]
        try:
            odds_display = f"{float(h['odds']):.1f}"
        except:
            odds_display = str(h['odds'])

        pick1_html = f'''
        <div style="background:#1a1a2e;border:1px solid rgba(240,192,64,0.4);border-radius:10px;padding:16px;margin-bottom:12px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
                <div style="font-family:'Courier New',monospace;font-size:9px;color:#F0C040;letter-spacing:0.15em;text-transform:uppercase">Leg 1 — Free Pick</div>
                <div style="font-family:'Courier New',monospace;font-size:9px;color:#C8C8E0;background:rgba(255,255,255,0.05);padding:3px 8px;border-radius:4px">{badge_label(h["badge"])}</div>
            </div>
            <div style="font-size:20px;font-weight:700;color:#FFFFFF;letter-spacing:1px;margin-bottom:6px">{h["name"]}</div>
            <div style="font-family:'Courier New',monospace;font-size:11px;color:#C8C8E0;margin-bottom:8px">{h["course"]} · {format_time_uk(h["time"])} · {odds_display} BSP</div>
            <div style="font-size:12px;color:#E0E0F0;line-height:1.5;padding:10px;background:rgba(255,255,255,0.04);border-radius:6px;border-left:2px solid rgba(240,192,64,0.4)">{h["why"] or "Selected by Signal 75 data engine."}</div>
            <div style="margin-top:8px;font-family:'Courier New',monospace;font-size:10px;color:#888">Form: {h["form"] or "—"} · Jockey: {h["jockey"] or "—"}</div>
        </div>'''

        # Locked picks 2 & 3
        locked_html = f'''
        <div style="margin-bottom:8px;position:relative">
            <div style="background:#1a1a2e;border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:16px;filter:blur(3px);opacity:0.4">
                <div style="font-family:'Courier New',monospace;font-size:9px;color:#F0C040;text-transform:uppercase;margin-bottom:8px">Leg 2 — Locked</div>
                <div style="font-size:18px;font-weight:700;color:#FFFFFF">▓▓▓▓▓▓▓▓▓▓</div>
                <div style="font-family:'Courier New',monospace;font-size:11px;color:#C8C8E0;margin-top:6px">▓▓▓▓▓▓ · ▓▓:▓▓ · ▓.▓</div>
            </div>
            <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;width:100%">
                <div style="font-size:20px">🔒</div>
            </div>
        </div>
        <div style="margin-bottom:16px;position:relative">
            <div style="background:#1a1a2e;border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:16px;filter:blur(3px);opacity:0.4">
                <div style="font-family:'Courier New',monospace;font-size:9px;color:#F0C040;text-transform:uppercase;margin-bottom:8px">Leg 3 — Locked</div>
                <div style="font-size:18px;font-weight:700;color:#FFFFFF">▓▓▓▓▓▓▓▓▓▓</div>
                <div style="font-family:'Courier New',monospace;font-size:11px;color:#C8C8E0;margin-top:6px">▓▓▓▓▓▓ · ▓▓:▓▓ · ▓.▓</div>
            </div>
            <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;width:100%">
                <div style="font-size:20px">🔒</div>
            </div>
        </div>'''

    # Performance row
    perf_html = ''
    if bet_days > 0:
        perf_html = f'''
        <div style="background:#0d0d1a;border:1px solid rgba(255,255,255,0.08);border-radius:8px;padding:12px;margin-bottom:16px;display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center">
            <div>
                <div style="font-size:18px;font-weight:700;color:{profit_color}">{profit_str}</div>
                <div style="font-family:'Courier New',monospace;font-size:8px;color:#888;text-transform:uppercase;margin-top:2px">Profit</div>
            </div>
            <div>
                <div style="font-size:18px;font-weight:700;color:#FFFFFF">{bet_days}</div>
                <div style="font-family:'Courier New',monospace;font-size:8px;color:#888;text-transform:uppercase;margin-top:2px">Bet Days</div>
            </div>
            <div>
                <div style="font-size:18px;font-weight:700;color:#F0C040">{roi:+.0f}%</div>
                <div style="font-family:'Courier New',monospace;font-size:8px;color:#888;text-transform:uppercase;margin-top:2px">ROI</div>
            </div>
        </div>'''

    html = f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0a0a0f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:420px;margin:0 auto;padding:16px">

    <!-- Header -->
    <div style="text-align:center;padding:20px 0 16px">
        <div style="font-size:28px;font-weight:900;letter-spacing:3px;color:#FFFFFF">SIGNAL 75</div>
        <div style="font-family:'Courier New',monospace;font-size:9px;color:#F0C040;letter-spacing:0.2em;text-transform:uppercase;margin-top:4px">AI Horse Racing Intelligence</div>
        <div style="font-family:'Courier New',monospace;font-size:9px;color:#888;margin-top:6px">{date_display}</div>
    </div>

    <!-- Performance strip -->
    {perf_html}

    <!-- Today's picks header -->
    <div style="font-family:'Courier New',monospace;font-size:9px;color:#C8C8E0;letter-spacing:0.15em;text-transform:uppercase;margin-bottom:10px">
        {"📊 Today's Patent Selections" if mode != "noBetDay" else "📊 Today's Signal"}
    </div>

    <!-- Pick 1 -->
    {pick1_html}

    <!-- Locked picks -->
    {locked_html}

    <!-- CTA -->
    <div style="text-align:center;margin-bottom:20px">
        <a href="{SITE_URL}" style="display:inline-block;background:linear-gradient(135deg,#F0C040,#d4a820);color:#000000;font-weight:700;font-size:14px;padding:14px 32px;border-radius:8px;text-decoration:none;letter-spacing:0.5px">
            {"🔍 View Today's Radar" if mode == "noBetDay" else "🐴 See All 3 Picks Free"}
        </a>
        <div style="font-family:'Courier New',monospace;font-size:9px;color:#888;margin-top:8px">{"Radar horses scored highly but didn't qualify today" if mode == "noBetDay" else "Share with a friend to unlock all 3 — no payment needed"}</div>
    </div>

    <!-- Footer -->
    <div style="border-top:1px solid rgba(255,255,255,0.08);padding-top:14px;text-align:center">
        <div style="font-family:'Courier New',monospace;font-size:9px;color:#888;line-height:1.8">
            Signal 75 · signal75.co.uk<br>
            Every result published — including losses<br>
            <a href="{{{{ unsubscribe }}}}" style="color:#888">Unsubscribe</a>
        </div>
    </div>

</div>
</body>
</html>'''

    return html

def send_email(html, subject, brevo_key):
    """Send email to all subscribers via Brevo."""
    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": "batch"}],
        "subject": subject,
        "htmlContent": html,
        "listIds": [LIST_ID],
        "params": {}
    }

    # Use Brevo campaign send to list
    campaign_payload = {
        "name": f"Signal 75 Daily — {datetime.now().strftime('%Y-%m-%d')}",
        "subject": subject,
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "htmlContent": html,
        "recipients": {"listIds": [LIST_ID]},
        "scheduledAt": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    }

    data = json.dumps(campaign_payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api.brevo.com/v3/emailCampaigns',
        data=data,
        headers={
            'api-key': brevo_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        },
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read())
            print(f"Campaign created: ID {result.get('id')}")
            return result.get('id')
    except urllib.error.HTTPError as e:
        print(f"Error: {e.code} — {e.read().decode()}")
        return None

def main():
    import sys
    test_mode = '--test' in sys.argv

    picks = load_json(PICKS_JSON)
    perf = load_json(PERF_JSON)

    date_str = picks.get('date', datetime.now().strftime('%Y-%m-%d'))
    mode = picks.get('mode', 'noBetDay')

    if mode == 'noBetDay':
        subject = f"🔍 Signal 75 — No Bet Day · {date_str}"
    else:
        subject = f"🏇 Signal 75 — Today's Picks · {date_str}"

    html = build_email_html(picks, perf)

    if test_mode:
        # Save HTML to file for preview
        out = f'/Users/johnhowlett/Desktop/Signal75-Engine/email_preview.html'
        with open(out, 'w') as f:
            f.write(html)
        print(f"Preview saved to {out}")
        print(f"Subject: {subject}")
        print("Open email_preview.html in browser to check layout")
        return

    # Get Brevo key
    brevo_key = get_brevo_key()
    if not brevo_key:
        print("No Brevo API key found in keychain")
        print("Store with: security add-generic-password -a signal75 -s brevo-api-key -w YOUR_KEY")
        return

    campaign_id = send_email(html, subject, brevo_key)
    if campaign_id:
        print(f"Email campaign created and scheduled")

if __name__ == '__main__':
    main()
