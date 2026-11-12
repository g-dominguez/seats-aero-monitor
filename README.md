# seats-aero-monitor

A Python script that checks the Seats.aero partner API for premium economy award seats on a specific trip and emails an alert when seats match. It runs in GitHub Actions, started every 20 minutes by a small scheduler on AWS.

### How it works
* **Scheduled checks:** the workflow `.github/workflows/monitor.yml` runs `seats_aero_monitor.py`. Two things start it:
  * **AWS scheduler (main):** EventBridge Scheduler calls a Lambda function every 20 minutes, which asks GitHub to run the workflow on `main` (see [AWS scheduler](#aws-scheduler)).
  * **GitHub cron (backup):** the workflow's own cron asks for every 20 minutes, but GitHub delays scheduled runs under load and in practice they arrive about every 7 hours. It's kept in case the AWS scheduler stops.
* **Search:** each route in `SEARCH_QUERIES` is searched for one date across several loyalty programs (`SOURCES`). Results come from Seats.aero's cached data, so they can be out of date.
* **Filtering:** each flight is checked on its own for cabin, seat count, points cost and, where set, earliest departure hour. An alert only uses that one flight's values. Flights with an unusable price are skipped and logged.
* **Alerts:** matches are emailed through Gmail SMTP and listed in the GitHub Actions job summary. If there are matches and the email can't be sent, the run fails so the problem is visible.

### Configuration
* **Trip criteria:** set in the "Flight Criteria" section of `seats_aero_monitor.py` (date, cabin, seats, points limit, routes and programs).
* **Secrets:** stored as GitHub repository secrets and passed in as environment variables: `SEATS_AERO_API_KEY`, `SMTP_USER`, `SMTP_PASSWORD` (a Gmail app password) and `NOTIFICATION_EMAIL`.

### AWS scheduler
The `scheduler/` folder holds the AWS part, deployed with the AWS SAM CLI to `us-west-2`.

* **What's in it** (`scheduler/template.yaml`):
  * an EventBridge Scheduler schedule that runs every 20 minutes
  * a Python Lambda function, `scheduler/src/dispatch.py`, that calls GitHub's workflow dispatch API. It doesn't retry, because the next run is 20 minutes away.
  * logs kept for 30 days
  * a CloudWatch alarm that emails you through SNS if 2 or more runs in an hour fail
* **GitHub token:** a fine-grained personal access token limited to this repo, with Actions read and write access. It's stored as the SecureString parameter `/seats-aero-monitor/github-token` in SSM Parameter Store, not in the stack or the repo. When it expires, create a new one and store it the same way (with `--overwrite`). The Lambda picks it up within a few hours, or straight away after a redeploy.
* **Deploy or update:**
  ```bash
  aws login
  # Store the token once (input is hidden):
  read -s "GH_TOKEN?Paste GitHub token: " && echo && aws ssm put-parameter --name /seats-aero-monitor/github-token --type SecureString --value "$GH_TOKEN" && unset GH_TOKEN
  cd scheduler && sam deploy --guided   # later deploys: sam deploy
  ```
  The guided deploy asks for `AlertEmail` and saves your answers to `scheduler/samconfig.toml`. That file is gitignored because it contains your email.
* **Remove:** run `sam delete` in `scheduler/`. The token parameter isn't part of the stack, so delete it separately.
* **Cost:** effectively free at this volume.

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
* **Scheduling:** AWS EventBridge Scheduler and Lambda (SAM), with GitHub Actions as a backup
* **Runs on:** GitHub Actions
* **Data source:** Seats.aero partner API
