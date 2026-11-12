"""Lambda handler that starts the monitor workflow on GitHub.

EventBridge Scheduler calls this every 20 minutes. It asks GitHub to run
.github/workflows/monitor.yml on main, the same as pressing "Run workflow"
in the Actions tab. The GitHub token is read from SSM Parameter Store and is
never logged or returned.
"""

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger()
logger.setLevel(logging.INFO)

GITHUB_API = "https://api.github.com"
GITHUB_API_VERSION = "2026-03-10"

_token = None


def get_token() -> str:
    """Read the GitHub token from Parameter Store, once per Lambda container."""
    global _token
    if _token is None:
        import boto3  # included in the Lambda Python runtime; not needed for tests

        ssm = boto3.client("ssm")
        response = ssm.get_parameter(
            Name=os.environ["TOKEN_PARAMETER"], WithDecryption=True
        )
        _token = response["Parameter"]["Value"]
    return _token


def handler(event, context):
    repo = os.environ["GITHUB_REPO"]
    workflow = os.environ["WORKFLOW_FILE"]
    ref = os.environ["GIT_REF"]

    request = urllib.request.Request(
        f"{GITHUB_API}/repos/{repo}/actions/workflows/{workflow}/dispatches",
        data=json.dumps({"ref": ref}).encode(),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {get_token()}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as e:
        # GitHub's error message explains bad tokens, missing permissions, etc.
        detail = e.read()[:500].decode(errors="replace")
        raise RuntimeError(f"GitHub returned {e.code}: {detail}") from None

    run_id = None
    if body:
        run_id = json.loads(body).get("workflow_run_id")
    logger.info("Started %s on %s (status %s, run %s)", workflow, ref, status, run_id)
    return {"status": status, "workflow_run_id": run_id}
