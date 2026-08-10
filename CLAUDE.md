# relai-threads-bot

Marketing automation for Relai, a Swiss Bitcoin-only self-custody app.
Owner: Arsen Thagapsov, Marketing Lead. Timezone Europe/Zurich.

Posts to the official company Threads account via GitHub Actions.

**Scope: Threads only.** Sibling repo to `relai-x-bot`, which is X-only by
its own design. Kept separate on purpose: different platform, different
auth model, different failure modes. Do not merge the two.

---

## Working style

- Output first, questions after. Build it, then flag what needs correcting.
- No options menus when there is a clear recommendation. Give the recommendation.
- Bullets over paragraphs. One sentence per point.
- **Never use em dashes.** They make writing read as AI-generated.
- Be direct about uncertainty. "Likely" without a source is not acceptable.
  If a figure comes from a third party rather than the vendor, say so.

---

## Current state

### Live bots

| File | Workflow | Schedule | Content |
|---|---|---|---|
| `post_evergreen.py` | `evergreen.yml` | Mondays | One line from `evergreen.txt`, same pool as the X bot |

Targets 09:00-13:00 Europe/Zurich, hard cutoff 20:00. Same rotation seed and
EPOCH as `relai-x-bot`, so both accounts post the same line on the same
Monday. If the pools ever diverge, give this one its own `SHUFFLE_SEED`.

### Shared module

`threads_api.py`. Stdlib only, no pip install step, matching the reasoning
in the X bot's `x_api.py`. Auth is a bearer-style access token as a query
param, not OAuth 1.0a signing, since that's what the Threads Graph API uses.
Posting is a two-step container/publish flow, not a single call.

---

## Architecture decisions, and why

**Four scheduled slots per posting day, any of which can post.**
Same reasoning as the X bot: GitHub runner acquisition fails often, so one
chance per day was not enough. Deduplicated by reading the account rather
than by keeping state.

**Window guard on the local clock, not the cron.**
Same reasoning as the X bot: GitHub cron is best effort and lands late, not
early. Each run checks the real Europe/Zurich time before posting.

**Cron times sit off the hour**, same UTC times as the X bot's evergreen
workflow, since both target the same local window.

**No auto-refresh for the access token.** Threads access tokens expire
after 60 days, unlike X's OAuth 1.0a tokens which never expire. Automating
the refresh would need a GitHub PAT with repo secret-write access sitting
in Actions, a bigger permission grant than this bot's blast radius
justifies. Renewal is manual: generate a new long-lived token from the
Meta developer dashboard's User Token Generator, re-save it as the
`THREADS_ACCESS_TOKEN` secret. Nothing in the code warns you when it is
close to expiring; put a reminder wherever you track recurring tasks.

**No state files, no database.** Everything derives from the date or from
reading the account, same as the X bot.

---

## Known problems

**Access token expires every 60 days.** See above. If posts start failing
with an auth error, this is the first thing to check.

**Everything under "Known problems" in `relai-x-bot`'s CLAUDE.md about
GitHub scheduled runs being unreliable applies here too**, since this repo
uses the same GitHub Actions scheduling mechanism.

---

## Secrets

Set in repo Settings, never in code. Names only:

- `THREADS_APP_ID`, `THREADS_APP_SECRET` — from the Meta developer app
- `THREADS_ACCESS_TOKEN` — long-lived, expires in 60 days, manual renewal
- `THREADS_USER_ID` — optional, saves one API read per run

Never print, log or commit secret values.

---

## Compliance

Relai AG is VQF-regulated in Switzerland. Relai EU SASU holds MiCA CASP
authorization and is supervised by the AMF in France.

Anything posted from Relai's Threads account is an external, EU-retail-
facing marketing communication under **MiCA Art. 66**, same as the X
account, which requires it to be fair, clear and not misleading.

**Rules for this repo:**

- `evergreen.txt` mirrors the X bot's pool, which went through Compliance
  review for @relai_app specifically. Verbatim reuse on Threads is the
  current assumption; get a one-line confirmation from Compliance that the
  sign-off covers cross-platform reuse before this goes live, not just X.
- Never add, edit or reword content in `evergreen.txt` without being asked.
- Flag regulatory exposure explicitly with the regulator and article. Flag
  it once, state the specific change needed, then move on.
- Anything touching public copy is an advisory draft. Guglielmo in
  Compliance reviews before it goes live.
- The Threads API itself is a new ICT dependency under **DORA** and needs
  a register entry, separate from whatever entry X's API already has.

---

## Testing

The workflow has a `dry_run` input defaulting to true. Always dry run first.

A dry run exits before any API call, so it does **not** test authentication.
Only a live run does that.

The repo may be public, matching the X bot. If so, Actions logs are public.
Do not log anything sensitive.
