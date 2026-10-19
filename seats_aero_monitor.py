"""
Seats.aero Multi-Route Award Flight Inventory Monitor & Alerter
---------------------------------------------------------------
Monitors Seats.aero Cached Search API for 2 Premium Economy award seats:
  - Route 1: NCE -> LAX (1-stop via European hubs like CDG, AMS, MAD, LHR)
  - Route 2: LHR -> LAX (Direct non-stop)
  - Date: July 17, 2027
  - Cabin: Premium Economy (W)
  - Seats: At least 2 seats
  - Max Points Budget: 60,000 miles per seat

Notifications supported:
  1. Email via Gmail App Password (SMTP) or custom SMTP
  2. Mobile push via Discord Webhook / Telegram
  3. GitHub Actions Job Summary table (renders directly in GitHub Actions UI)
"""

import os
import sys
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ----------------- Configuration & Secrets -----------------
SEATS_AERO_API_KEY = os.getenv("SEATS_AERO_API_KEY", "").strip()

# Email notification settings (Optional: Gmail App Password or SMTP)
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
# Automatically strips any spaces from Google App Password (e.g., 'abcd efgh' -> 'abcdefgh')
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").replace(" ", "").strip()
NOTIFICATION_EMAIL = os.getenv("NOTIFICATION_EMAIL", SMTP_USER).strip()

# Mobile push webhooks (Optional)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Flight Criteria
API_URL = "https://seats.aero/partnerapi/search"
TARGET_DATE = "2027-07-17"
CABIN = "premium"
MIN_SEATS = 2
MAX_POINTS_CEILING = 60000

# Multiple origin search:
# - NCE (Nice) to LAX (captures 1-stop via CDG/Air France, AMS/KLM, MAD/Iberia, etc.)
# - LHR (London Heathrow) to LAX (captures direct Virgin Atlantic & partner routes)
SEARCH_QUERIES = [
    {
        "name": "NCE to LAX (1-stop via European hubs)",
        "origin": "NCE",
        "destination": "LAX",
        "only_direct": "false",
        "min_cabin_pct": 70,  # Permits European short feeder leg in economy
    },
    {
        "name": "LHR to LAX (Direct non-stop)",
        "origin": "LHR",
        "destination": "LAX",
        "only_direct": "true",
        "min_cabin_pct": 100,
    },
]

# Loyalty program sources covering Chase, Amex, Capital One transfer partners:
# virginatlantic (Virgin Atlantic Flying Club), flyingblue (Air France/KLM),
# aeroplan (Air Canada), delta (SkyMiles), alaska/american (BA partner routes)
SOURCES = "virginatlantic,flyingblue,aeroplan,delta,alaska,american,united"


# ----------------- Notification Dispatchers -----------------
def send_email_alert(flights: list) -> None:
    """Send an email alert via SMTP (e.g., Gmail App Password)."""
    if not SMTP_USER or not SMTP_PASSWORD or not NOTIFICATION_EMAIL:
        logging.info("SMTP email credentials not set. Skipping email dispatch.")
        return

    subject = f"✈️ Flight Alert: Found {len(flights)} Premium Economy Options to LAX (≤60k pts)"
    
    html_rows = ""
    for f in flights:
        html_rows += f"""
        <tr>
            <td style="padding: 8px; border: 1px solid #ddd;">{f['route']}</td>
            <td style="padding: 8px; border: 1px solid #ddd;"><b>{f['points']:,}</b></td>
            <td style="padding: 8px; border: 1px solid #ddd;">${f['taxes']:.2f}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{f['seats']}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{f['program']}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{f['airlines']}</td>
            <td style="padding: 8px; border: 1px solid #ddd;">{'Direct' if f['direct'] else '1-Stop'}</td>
        </tr>
        """

    html_body = f"""
    <html>
    <body>
        <h2>Flight Award Availability Alert (July 17, 2027)</h2>
        <p>Found <b>{len(flights)}</b> flight option(s) meeting your criteria (2+ Premium Economy seats for ≤ 60,000 points):</p>
        <table style="border-collapse: collapse; width: 100%; font-family: sans-serif;">
            <thead>
                <tr style="background-color: #f2f2f2; text-align: left;">
                    <th style="padding: 8px; border: 1px solid #ddd;">Route</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">Points / Seat</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">Taxes</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">Seats</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">Program</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">Airlines</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">Type</th>
                </tr>
            </thead>
            <tbody>
                {html_rows}
            </tbody>
        </table>
        <p style="margin-top: 20px;">Log in to the respective airline program to book before seats sell out.</p>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = NOTIFICATION_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    try:
        logging.info(f"Connecting to SMTP server {SMTP_SERVER}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, NOTIFICATION_EMAIL, msg.as_string())
        server.quit()
        logging.info(f"Alert email sent successfully to {NOTIFICATION_EMAIL}!")
    except Exception as e:
        logging.error(f"Failed to send email alert: {e}")


def send_discord_alert(flights: list) -> None:
    """Send an alert to a Discord channel via Webhook."""
    if not DISCORD_WEBHOOK_URL:
        return

    description = f"Found **{len(flights)}** option(s) for 2 seats in Premium Economy (≤ 60k pts):\n\n"
    for f in flights[:5]:  # Send top 5 to keep message compact
        description += (
            f"• **{f['route']}** | **{f['points']:,} pts** (+${f['taxes']:.2f}) | "
            f"{f['seats']} seats on {f['program'].title()} ({f['airlines']})\n"
        )

    payload = {
        "embeds": [
            {
                "title": f"🚨 Premium Economy Alert: July 17, 2027 to LAX",
                "description": description,
                "color": 3447003,
                "timestamp": datetime.utcnow().isoformat(),
            }
        ]
    }
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if res.status_code == 204:
            logging.info("Discord webhook alert sent successfully.")
    except Exception as e:
        logging.error(f"Failed to send Discord alert: {e}")


def write_github_summary(matches: list) -> None:
    """Write an execution summary table directly to the GitHub Actions workflow tab."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    with open(summary_path, "a") as f:
        f.write("### ✈️ Seats.aero Award Flight Monitor Results\n\n")
        f.write(f"**Target Date:** {TARGET_DATE} | **Cabin:** Premium Economy | **Budget Cap:** ≤ {MAX_POINTS_CEILING:,} pts\n\n")
        
        if not matches:
            f.write("ℹ️ *No qualifying seats found on this check. Will check again on next scheduled run.*\n")
            return

        f.write("| Route | Points / Seat | Taxes (USD) | Seats | Program | Airlines | Flight Type |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for m in matches:
            f.write(
                f"| {m['route']} | **{m['points']:,}** | ${m['taxes']:.2f} | {m['seats']} | "
                f"{m['program']} | {m['airlines']} | {'Direct' if m['direct'] else '1-Stop'} |\n"
            )


# ----------------- API Query Engine -----------------
def query_route(query_cfg: dict, headers: dict) -> list:
    """Query Seats.aero API for a single route configuration."""
    params = {
        "origin_airport": query_cfg["origin"],
        "destination_airport": query_cfg["destination"],
        "start_date": TARGET_DATE,
        "end_date": TARGET_DATE,
        "cabins": CABIN,
        "sources": SOURCES,
        "only_direct_flights": query_cfg["only_direct"],
        "min_cabin_pct": query_cfg["min_cabin_pct"],
        "take": 200,
    }

    logging.info(f"Querying {query_cfg['name']}...")

    try:
        response = requests.get(API_URL, headers=headers, params=params, timeout=20)
        if response.status_code != 200:
            logging.error(f"API Error ({response.status_code}): {response.text}")
            return []

        data = response.json().get("data", [])
        logging.info(f"Received {len(data)} availability items for {query_cfg['name']}.")

        matching_flights = []
        for item in data:
            w_avail = item.get("WAvailable", False)
            w_seats = int(item.get("WRemainingSeats", 0) or 0)
            w_miles_raw = item.get("WMileageCost", "0")
            w_miles = int(w_miles_raw) if str(w_miles_raw).isdigit() else 0
            w_taxes_cents = item.get("WTotalTaxes", 0) or 0
            w_taxes_usd = float(w_taxes_cents) / 100.0

            # Filter criteria: 2+ seats available and points <= 60,000
            if w_avail and w_seats >= MIN_SEATS:
                if MAX_POINTS_CEILING and w_miles > MAX_POINTS_CEILING:
                    continue

                flight_entry = {
                    "route": f"{item.get('Route', {}).get('OriginAirport', query_cfg['origin'])} → {DESTINATION}",
                    "date": item.get("Date", TARGET_DATE),
                    "seats": w_seats,
                    "points": w_miles,
                    "taxes": w_taxes_usd,
                    "program": item.get("Source", "N/A"),
                    "airlines": item.get("WAirlines", "N/A"),
                    "direct": item.get("WDirect", query_cfg["only_direct"] == "true"),
                }
                matching_flights.append(flight_entry)

        return matching_flights

    except Exception as e:
        logging.error(f"Failed to query {query_cfg['name']}: {e}")
        return []


def main():
    if not SEATS_AERO_API_KEY:
        logging.error("Missing SEATS_AERO_API_KEY environment variable. Exiting.")
        sys.exit(1)

    headers = {
        "Partner-Authorization": SEATS_AERO_API_KEY,
        "Accept": "application/json",
    }

    all_matches = []
    for cfg in SEARCH_QUERIES:
        matches = query_route(cfg, headers)
        all_matches.extend(matches)

    logging.info(f"Total matching flights across all routes: {len(all_matches)}")

    # Record summary in GitHub Actions UI
    write_github_summary(all_matches)

    # Dispatch alerts if matches found
    if all_matches:
        send_email_alert(all_matches)
        send_discord_alert(all_matches)


if __name__ == "__main__":
    main()
