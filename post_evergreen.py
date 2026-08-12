#!/usr/bin/env python3
"""
Relai Threads bot - evergreen posts.

Posts one line from evergreen.txt every INTERVAL_DAYS days, targeting
09:00-13:00 Europe/Zurich. Mirrors the X evergreen bot
(relai-x-bot/post_evergreen.py) line for line; only the API client and
character limit differ.

Pool source:
  evergreen.txt here is a manually-maintained copy of relai-x-bot's pool,
  not a live fetch. This repo is meant to work standalone, including once
  relai-x-bot goes private, so it does not reach across repos at runtime or
  build time. The tradeoff is real: this file drifted once already (a
  43-line snapshot went stale while relai-x-bot's pool grew to 232 lines)
  and can drift again the same way. There is no automated guard against
  that here on purpose. When relai-x-bot/evergreen.txt changes, copy the
  whole file here too, in the same order, or the rotations fall out of
  step with each other. relai-x-bot/CLAUDE.md's evergreen.txt rules say to
  update this copy as well; keep that note in sync if this policy changes.

Reliability design:
  Four runs fire on each posting day. Any of them can post. Before posting,
  a run checks the account's recent posts for this cycle's exact line and
  exits if it is already there. So a run that fails to get a GitHub runner
  costs nothing, because the next slot picks it up.

  This content is not time sensitive, so a late post beats a missed one.
  Anything up to 20:00 local goes out. Only past 20:00 is the day skipped,
  to avoid posting overnight.

Rotation:
  Same INTERVAL_DAYS, EPOCH and SHUFFLE_SEED as the X bot on purpose, so
  both accounts post the same line on the same day, as long as evergreen.txt
  here matches relai-x-bot's copy exactly. Keep these in step with
  relai-x-bot/post_evergreen.py by hand; there is no shared code between the
  repos for this part, only shared conventions. If the two pools or cadences
  ever diverge on purpose, give this one its own SHUFFLE_SEED.
"""

import os
import sys
import random
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import threads_api

TZ = ZoneInfo("Europe/Zurich")
POOL_FILE = "evergreen.txt"

WINDOW_START_HOUR = 9
WINDOW_TARGET_END_HOUR = 13
HARD_CUTOFF_HOUR = 20

# Post every INTERVAL_DAYS days, counted from EPOCH. Must match
# relai-x-bot/post_evergreen.py so both accounts post the same line on the
# same day. Do not change casually, it shifts every future posting day and
# re-times the whole rotation.
INTERVAL_DAYS = 2

# Fixed reference point. Do not change once live, it anchors the rotation.
EPOCH = date(2026, 1, 1)

MAX_CHARS = 500
MIN_POOL_SIZE = 4

# Cron times must match .github/workflows/evergreen.yml.
# Deliberately off the hour: the top of the hour is GitHub's busiest moment.
SLOT_UTC_TIMES = {1: (8, 7), 2: (8, 53), 3: (9, 37), 4: (10, 23)}

SHUFFLE_SEED = "relai-evergreen-v1"


def load_pool(path=POOL_FILE):
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} not found.")

    lines = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            # "# " or a bare "#" is a comment. "#word" is a hashtag.
            if not line or line == "#" or line.startswith("# "):
                continue
            lines.append(line.replace("\\n", "\n"))

    if not lines:
        sys.exit(f"ERROR: {path} contains no tweets.")

    seen = set()
    dupes = [t for t in lines if t in seen or seen.add(t)]
    if dupes:
        sys.exit(f"ERROR: duplicate line in {path}: {dupes[0][:60]}...")

    long_ones = [t for t in lines if len(t) > MAX_CHARS]
    if long_ones:
        sys.exit(f"ERROR: line over {MAX_CHARS} chars: {long_ones[0][:60]}...")

    if len(lines) < MIN_POOL_SIZE:
        sys.exit(f"ERROR: pool has {len(lines)} lines, need at least {MIN_POOL_SIZE}.")

    return lines


def is_posting_day(day):
    return (day - EPOCH).days % INTERVAL_DAYS == 0


def post_index(today):
    """How many posting days have elapsed since EPOCH, excluding today."""
    if today < EPOCH:
        sys.exit("ERROR: current date is before EPOCH.")
    count = 0
    cursor = EPOCH
    while cursor < today:
        if is_posting_day(cursor):
            count += 1
        cursor = date.fromordinal(cursor.toordinal() + 1)
    return count


def pick_tweet(pool, today):
    order = list(pool)
    random.Random(SHUFFLE_SEED).shuffle(order)
    return order[post_index(today) % len(order)]


def in_window(today, slot):
    if slot == 0:
        return True
    h, m = SLOT_UTC_TIMES.get(slot, (0, 0))
    utc = datetime(today.year, today.month, today.day, h, m, tzinfo=timezone.utc)
    return WINDOW_START_HOUR <= utc.astimezone(TZ).hour < WINDOW_TARGET_END_HOUR


def main():
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    slot = int(os.environ.get("SLOT", "0"))

    now = datetime.now(TZ)
    today = now.date()

    print(f"Now: {now:%Y-%m-%d %H:%M %Z} ({now:%A}) | slot {slot}")

    if not is_posting_day(today) and slot != 0:
        print("Not a posting day. Exiting.")
        return

    if not in_window(today, slot):
        print("This slot falls outside the window today. Exiting.")
        return

    if not dry_run:
        if now.hour >= HARD_CUTOFF_HOUR:
            print(f"It is {now:%H:%M}, past the {HARD_CUTOFF_HOUR}:00 cutoff. Skipping.")
            return
        if now.hour >= WINDOW_TARGET_END_HOUR:
            print(f"Note: {now:%H:%M} is past target window. Posting anyway.")

    pool = load_pool()
    tweet = pick_tweet(pool, today)

    print(f"Pool: {len(pool)} lines | index {post_index(today) % len(pool)}")
    print(f"Repeat gap: {len(pool) * INTERVAL_DAYS} days")
    print("---")
    print(tweet)
    print("---")

    if dry_run:
        print("DRY_RUN enabled. Nothing posted.")
        return

    creds = threads_api.get_credentials()

    if threads_api.already_posted(creds, tweet):
        print("This cycle's post is already on the account. Nothing to do.")
        return

    post_id = threads_api.post(creds, tweet)
    if post_id:
        print(f"Posted: https://www.threads.net/@relai.app/post/{post_id}")


if __name__ == "__main__":
    main()
