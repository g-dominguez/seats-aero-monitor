# seats-aero-monitor

A Python script that checks the Seats.aero partner API for premium economy award seats on a specific trip and emails an alert when seats match. It runs on a schedule in GitHub Actions.

### How it works
* **Scheduled checks:** GitHub Actions runs `seats_aero_monitor.py` on a cron schedule (`.github/workflows/monitor.yml`). GitHub can delay or skip scheduled runs under load, so checks are less frequent than the cron asks for.
* **Search:** each route in `SEARCH_QUERIES` is searched for one date across several loyalty programs (`SOURCES`). Results come from Seats.aero's cached data, so they can be out of date.
* **Filtering:** each flight is checked on its own for cabin, seat count, points cost and, where set, earliest departure hour. An alert only uses that one flight's values. Flights with an unusable price are skipped and logged.
* **Alerts:** matches are emailed through Gmail SMTP and listed in the GitHub Actions job summary. If there are matches and the email can't be sent, the run fails so the problem is visible.

### Configuration
* **Trip criteria:** set in the "Flight Criteria" section of `seats_aero_monitor.py` (date, cabin, seats, points limit, routes and programs).
* **Secrets:** stored as GitHub repository secrets and passed in as environment variables: `SEATS_AERO_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD` (a Gmail app password) and `NOTIFICATION_EMAIL`.

### Checking it works
* **Send a test email** through the real secrets without searching:
  `gh workflow run monitor.yml -f send_test_email=true`
* **Run the tests** locally (no network or email):
  ```bash
  python3 -m venv .venv && source .venv/bin/activate
  pip install pytest requests
  python -m pytest -v
  ```

### Known limitations
* The same alert is sent on every run while seats stay available.
* Taxes are always shown in USD, even when the program reports another currency.
* API failures are logged but currently look like a run with no matches.

### Tech stack
* **Language:** Python 3
* **Scheduling:** GitHub Actions
* **Data source:** Seats.aero partner API
