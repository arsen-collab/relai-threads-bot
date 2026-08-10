#!/usr/bin/env python3
"""
Minimal Threads API client for the Relai bots.

Standard library only, mirrors the no-dependency approach in the X bot's
x_api.py. Auth is a bearer-style access token passed as a query param,
which is much simpler than X's OAuth 1.0a HMAC signing.

Unlike X's tokens, this one expires (60 days) and must be renewed by hand
in the Meta developer dashboard, then re-saved as the THREADS_ACCESS_TOKEN
GitHub secret. No auto-refresh is built here on purpose: doing that would
need a GitHub PAT with repo secret-write access sitting in Actions, which
is a bigger permission grant than this bot's blast radius justifies.
Put a reminder on your own calendar; there is no code-side warning.
"""

import os
import sys
import time
import json
import urllib.parse
import urllib.request
import urllib.error

API = "https://graph.threads.net/v1.0"

RETRY_ON = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = [5, 20]


def get_credentials():
    keys = ["THREADS_APP_ID", "THREADS_APP_SECRET", "THREADS_ACCESS_TOKEN"]
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        sys.exit(f"ERROR: missing variables: {', '.join(missing)}")
    return {k: os.environ[k] for k in keys}


def _request(method, url, params=None, body=None):
    """One HTTP call with retries on transient failures."""
    query = dict(params or {})
    full_url = url
    if method == "GET" and query:
        full_url += "?" + urllib.parse.urlencode(query)

    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        req_url = full_url
        data = None
        if method == "POST":
            data = urllib.parse.urlencode(query).encode("utf-8")
        req = urllib.request.Request(req_url, data=data, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8")[:300]
            last_error = (exc.code, detail)
            if exc.code in RETRY_ON and attempt < MAX_ATTEMPTS - 1:
                wait = BACKOFF_SECONDS[attempt]
                print(f"  HTTP {exc.code}, retrying in {wait}s "
                      f"(attempt {attempt + 2}/{MAX_ATTEMPTS})")
                time.sleep(wait)
                continue
            return {"_error": exc.code, "_detail": detail}
        except urllib.error.URLError as exc:
            last_error = (0, str(exc))
            if attempt < MAX_ATTEMPTS - 1:
                wait = BACKOFF_SECONDS[attempt]
                print(f"  Network error, retrying in {wait}s "
                      f"(attempt {attempt + 2}/{MAX_ATTEMPTS})")
                time.sleep(wait)
                continue
            return {"_error": 0, "_detail": str(exc)}

    return {"_error": last_error[0], "_detail": last_error[1]}


def get_user_id(creds):
    """Cached via THREADS_USER_ID if set, saves one API read per run."""
    cached = os.environ.get("THREADS_USER_ID")
    if cached:
        return cached
    result = _request(
        "GET", f"{API}/me",
        params={"fields": "id,username", "access_token": creds["THREADS_ACCESS_TOKEN"]},
    )
    if "_error" in result:
        print(f"  Could not resolve user id: {result['_error']} {result['_detail']}")
        return None
    return result.get("id")


def recent_texts(creds, count=10):
    """Most recent posts on the account. Returns None if the check failed,
    which callers must treat differently from an empty list."""
    user_id = get_user_id(creds)
    if not user_id:
        return None
    result = _request(
        "GET", f"{API}/{user_id}/threads",
        params={
            "fields": "text",
            "limit": max(5, min(count, 100)),
            "access_token": creds["THREADS_ACCESS_TOKEN"],
        },
    )
    if "_error" in result:
        print(f"  Could not read recent posts: {result['_error']} {result['_detail']}")
        return None
    return [t.get("text", "") for t in (result.get("data") or [])]


def already_posted(creds, text, count=10):
    """True if this exact text is already on the account.

    Returns False when the check itself fails, so a read outage does not
    silently stop the bot from posting. Worst case is a duplicate attempt.
    """
    texts = recent_texts(creds, count)
    if texts is None:
        print("  Duplicate check unavailable, proceeding.")
        return False
    normalised = text.strip()
    return any(t.strip() == normalised for t in texts)


def post(creds, text):
    """Two-step publish: create a container, then publish it."""
    user_id = get_user_id(creds)
    if not user_id:
        sys.exit("ERROR: could not resolve Threads user id.")

    container = _request(
        "POST", f"{API}/{user_id}/threads",
        params={
            "media_type": "TEXT",
            "text": text,
            "access_token": creds["THREADS_ACCESS_TOKEN"],
        },
    )
    if "_error" in container:
        code, detail = container["_error"], container["_detail"]
        sys.exit(f"ERROR: container creation failed with {code}: {detail}")

    creation_id = container.get("id")
    if not creation_id:
        sys.exit(f"ERROR: no creation_id in container response: {container}")

    published = _request(
        "POST", f"{API}/{user_id}/threads_publish",
        params={
            "creation_id": creation_id,
            "access_token": creds["THREADS_ACCESS_TOKEN"],
        },
    )
    if "_error" in published:
        code, detail = published["_error"], published["_detail"]
        if code == 400 and "duplicate" in detail.lower():
            print("  Already posted (duplicate). Treating as success.")
            return None
        sys.exit(f"ERROR: publish failed with {code}: {detail}")

    return published.get("id")
