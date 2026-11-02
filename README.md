# seats-aero-monitor

An automated flight availability tracker built in Python that queries the Seats.aero API to monitor award seat inventory across SkyTeam and Oneworld programs.

### Architecture & Overview
* **Automated Polling:** Executes on a scheduled cron via GitHub Actions to poll availability across target international routes, cabin classes, and specific date windows.
* **Payload Filtering:** Ingests raw JSON responses, filters by point/tax thresholds and minimum seat availability, and logs state changes to eliminate manual search overhead.
* **Secure Configuration:** Leverages repository secrets for API authentication and environment-variable-driven route definitions.

### Tech Stack
* **Language:** Python 3
* **CI/CD & Orchestration:** GitHub Actions
* **Target Services:** Seats.aero REST API