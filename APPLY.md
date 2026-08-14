# Getting this into the repo

The cloud sandbox this was built in can't push to GitHub (its git proxy only
allows repos attached to the session), so here are two ways to land it. The
bundle is the safe one — it carries the deletions and file moves that a zip
extraction would leave behind.

## Option A — git bundle (recommended)

```bash
cd /path/to/morning-brief
git pull /path/to/sneak.bundle main
git push
```

That fast-forwards main by one commit containing everything.

## Option B — zip

```bash
cd /path/to/morning-brief
unzip -o sneak-bundle.zip
# the zip cannot delete, so clear out the old system explicitly:
git rm -r --cached scripts simulator reports docs/reports main.py apply_renovation.py strategies 2>/dev/null
rm -rf scripts simulator reports docs/reports main.py apply_renovation.py strategies
git add -A && git commit -m "Pivot morning-brief to SNEAK opening-range scanner" && git push
```

## Then, on GitHub

1. **Settings → Pages → Source** = *GitHub Actions*
2. **Settings → Secrets and variables → Actions** — confirm `CLAUDE_API_KEY`
   still exists (the news triage reuses the old brief's secret). Without it the
   scanner still runs and falls back to keyword-based news flags.
3. **Actions** tab enabled.

## Smoke test without waiting for the morning

**Actions → SNEAK → Run workflow → stage: `prep`**, then `stalk`, then `strike`.

Outside market hours the scanner reports zero candidates — that is the correct
answer, and it proves the plumbing. The first real run happens automatically on
the next trading day.

## Rotate the token

The PAT pasted into the chat should be revoked — it has broad account access and
is now sitting in a transcript. Nothing in this repo needs it: GitHub Actions
authenticates with its own built-in `GITHUB_TOKEN`.
