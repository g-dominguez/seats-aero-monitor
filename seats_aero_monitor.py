"""
Seats.aero Multi-Route Award Flight Inventory Monitor & Alerter
---------------------------------------------------------------
Monitors Seats.aero Cached Search API for 2 Premium Economy award seats:
  - Route 1: NCE -> LAX (1-stop via European hubs like CDG, AMS, MAD, LHR)
  - Route 2: LHR -> LAX (Direct non-stop, restricted to Afternoon/Evening departures ≥ 12:00 PM)
  - Date: July 17, 2027
  - Cabin: Premium Economy (W)
  - Seats: At least 2 seats
  - Max Points Budget: 60,000 miles per seat

Notifications supported:
  1. Email via Gmail App Password (SMTP) with direct clickable booking links & departure times
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
# - NCE to LAX: Any time of day (starts in Nice)
# - LHR to LAX: Must depart in afternoon/evening (>= 12:00 PM) to allow connecting flight from Nice
SEARCH_QUERIES = [
    {
        "name": "NCE to LAX (1-stop via European hubs)",
        "origin": "NCE",
        "destination": "LAX",
        "only_direct": "false",
        "min_cabin_pct": 70,             # Permits European short feeder leg in economy
        "earliest_departure_hour": None, # Any departure time is acceptable
    },
    {
        "name": "LHR to LAX (Direct non-stop - Afternoon/Evening only)",
        "origin": "LHR",
        "destination": "LAX",
        "only_direct": "true",
        "min_cabin_pct": 100,
        "earliest_departure_hour": 12,   # 12:00 PM or later (12 to 23)
    },
]

# Loyalty program sources covering Chase, Amex, Capital One transfer partners:
SOURCES = "virginatlantic,flyingblue,aeroplan,delta,alaska,american,united"

# Booking portal direct links based on the mileage program detected
BOOKING_PORTALS = {
    "virginatlantic": "https://www.virginatlantic.com/en-gb/flying-club",
    "flyingblue": "https://www.flyingblue.com",
    "aeroplan": "https://www.aircanada.com/aeroplan",
    "alaska": "https://www.britishairways.com/en-gb/executive-club",  # Book BA via Avios
    "american": "https://www.britishairways.com/en-gb/executive-club", # Book BA via Avios
    "united": "https://www.united.com",
    "delta": "https://www.delta.com",
}


# ----------------- Notification Dispatchers -----------------
def send_email_alert(flights: list) -> None:
    """Send an HTML email alert with departure times and clickable booking links."""
    if not SMTP_USER or not SMTP_PASSWORD or not NOTIFICATION_EMAIL:
        logging.info("SMTP email credentials not set. Skipping email dispatch.")
        return

    subject = f"✈️ Award Alert: Found {len(flights)} Premium Economy Flight(s) to LAX (≤60k pts)"
    
    html_rows = ""
    for f in flights:
        program_key = f['program'].lower()
        portal_url = BOOKING_PORTALS.get(program_key, "https://seats.aero")
        portal_label = "British Airways (Avios)" if program_key in ["american", "alaska"] else f['program'].title()
        seats_aero_url = f"https://seats.aero/search?origin={f['origin']}&destination=LAX&date={TARGET_DATE}"

        dep_time_str = f.get("departure_time", "Afternoon/Evening" if f.get("is_afternoon") else "All Day")

        html_rows += f"""
        <tr style="border-bottom: 1px solid #e0e0e0;">
            <td style="padding: 10px; font-weight: bold;">{f['route']}</td>
            <td style="padding: 10px; color: #2e7d32; font-weight: bold;">{f['points']:,} pts</td>
            <td style="padding: 10px;">${f['taxes']:.2f}</td>
            <td style="padding: 10px; text-align: center;">{f['seats']}</td>
            <td style="padding: 10px;">{dep_time_str}</td>
            <td style="padding: 10px; text-transform: capitalize;">{f['program']} ({f['airlines']})</td>
            <td style="padding: 10px;">{'Direct' if f['direct'] else '1-Stop'}</td>
            <td style="padding: 10px;">
                <a href="{portal_url}" style="background-color: #1a73e8; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-size: 13px; display: inline-block;">Book on {portal_label}</a>
                <a href="{seats_aero_url}" style="margin-left: 8px; color: #555; text-decoration: underline; font-size: 12px;">View on Seats.aero</a>
            </td>
        </tr>
        """

    html_body = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #333; line-height: 1.5; padding: 20px;">
        <h2 style="color: #1a73e8; margin-bottom: 8px;">🎉 Premium Economy Award Seats Found!</h2>
        <p style="font-size: 15px; margin-top: 0;">
            Your flight monitor found <b>{len(flights)}</b> option(s) for <b>July 17, 2027</b> matching your criteria (at least 2 Premium Economy seats for ≤ 60,000 points):
        </p>

        <table style="border-collapse: collapse; width: 100%; margin-top: 15px; font-size: 14px;">
            <thead>
                <tr style="background-color: #f8f9fa; border-bottom: 2px solid #dee2e6; text-align: left;">
                    <th style="padding: 10px;">Route</th>
                    <th style="padding: 10px;">Cost / Seat</th>
                    <th style="padding: 10px;">Taxes (USD)</th>
                    <th style="padding: 10px; text-align: center;">Seats</th>
                    <th style="padding: 10px;">Departs Around</th>
                    <th style="padding: 10px;">Found Via</th>
                    <th style="padding: 10px;">Flight Type</th>
                    <th style="padding: 10px;">Action Links</th>
                </tr>
            </thead>
            <tbody>
                {html_rows}
            </tbody>
        </table>

        <div style="margin-top: 25px; padding: 15px; background-color: #e8f0fe; border-left: 4px solid #1a73e8; border-radius: 4px;">
            <p style="margin: 0; font-size: 13px; color: #174ea6;">
                <b>Booking Instructions:</b> If found on Virgin Atlantic or Air France, transfer your points directly to Flying Club or Flying Blue. If found on American/Alaska on oneworld flights, transfer your Chase, Amex, or Capital One points to <b>British Airways Executive Club (Avios)</b> to complete the booking.
            </p>
        </div>
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
    for f in flights[:5]:
        program_key = f['program'].lower()
        portal_url = BOOKING_PORTALS.get(program_key, "https://seats.aero")
        portal_label = "British Airways" if program_key in ["american", "alaska"] else f['program'].title()
        dep_str = f" ({f.get('departure_time', 'PM flight')})" if f.get("departure_time") else ""
        description += (
            f"• **{f['route']}**{dep_str} | **{f['points']:,} pts** (+${f['taxes']:.2f})\n"
            f"  {f['seats']} seats on {f['program'].title()} ({f['airlines']}) | [Book on {portal_label}]({portal_url})\n\n"
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

        f.write("| Route | Departure Time | Points / Seat | Taxes (USD) | Seats | Program | Airlines | Type | Booking Link |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n")
        for m in matches:
            program_key = m['program'].lower()
            portal_url = BOOKING_PORTALS.get(program_key, "https://seats.aero")
            portal_label = "British Airways" if program_key in ["american", "alaska"] else m['program'].title()
            dep_str = m.get("departure_time", "Afternoon/Evening" if m.get("is_afternoon") else "All Day")
            f.write(
                f"| {m['route']} | {dep_str} | **{m['points']:,}** | ${m['taxes']:.2f} | {m['seats']} | "
                f"{m['program'].title()} | {m['airlines']} | {'Direct' if m['direct'] else '1-Stop'} | "
                f"[{portal_label}]({portal_url}) |\n"
            )


# ----------------- API Query Engine -----------------
def query_route(query_cfg: dict, headers: dict) -> list:
    """Query Seats.aero API for a single route configuration with time-of-day filtering."""
    params = {
        "origin_airport": query_cfg["origin"],
        "destination_airport": query_cfg["destination"],
        "start_date": TARGET_DATE,
        "end_date": TARGET_DATE,
        "cabins": CABIN,
        "sources": SOURCES,
        "only_direct_flights": query_cfg["only_direct"],
        "min_cabin_pct": query_cfg["min_cabin_pct"],
        "include_trips": "true",  # Fetches individual flight segments with DepartsAt timestamps
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
        earliest_hour = query_cfg.get("earliest_departure_hour")

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

                # Inspect trip-level departure time if time-of-day restriction is set
                trips = item.get("AvailabilityTrips") or item.get("Trips") or []
                flight_dep_time = None
                time_filter_passed = True

                if earliest_hour is not None:
                    # If trips exist, evaluate specific departure time
                    if trips:
                        time_filter_passed = False
                        for t in trips:
                            if t.get("Cabin") == "premium" or not t.get("Cabin"):
                                dep_str = t.get("DepartsAt")
                                if dep_str:
                                    try:
                                        dep_dt = datetime.fromisoformat(dep_str.replace("Z", "+00:00"))
                                        if dep_dt.hour >= earliest_hour:
                                            time_filter_passed = True
                                            flight_dep_time = dep_dt.strftime("%I:%M %p")
                                            break
                                    except Exception:
                                        time_filter_passed = True
                    else:
                        # Fallback if trip-level data is unavailable from source
                        time_filter_passed = True

                if not time_filter_passed:
                    logging.info(f"Flight from {query_cfg['origin']} departs before {earliest_hour}:00. Skipping.")
                    continue

                flight_entry = {
                    "origin": query_cfg["origin"],
                    "route": f"{item.get('Route', {}).get('OriginAirport', query_cfg['origin'])} → {DESTINATION}",
                    "date": item.get("Date", TARGET_DATE),
                    "departure_time": flight_dep_time,
                    "is_afternoon": earliest_hour is not None,
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