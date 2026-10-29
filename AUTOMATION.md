# SNEAK automation — setup and runbook

The scan starts itself, the laptop trades the published list, and Healthchecks.io
tells your phone when any piece goes quiet. The plan behind it is in the
"SNEAK automation plan" doc.

```
cron-job.org 08:45 CT ──▶ GitHub Actions scan ──▶ docs/orders.json (~09:01 CT)
laptop 08:50 CT (backup start)  ─┘                        │
                                                          ▼
                    laptop executor ── buy-stops, exits ──▶ Alpaca paper
                          │  heartbeats                        ▲
                          ▼                                    │
                    Healthchecks.io ──▶ your phone    cron-job.org 14:55 CT ── cloud flatten backup
```

## One-time setup

### 1. Healthchecks.io: four checks

Create four checks. For each one, set **Schedule → Cron**, with time zone **America/Chicago**. The
check's **name must be exactly** what is shown, because the pings address checks by name (slug).

| Name | Cron expression | Grace time | Who pings it |
| --- | --- | --- | --- |
| `sneak-scan` | `45 8 * * 1-5` | 30 minutes | the GitHub workflow, at its start and its end |
| `sneak-orders` | `0 9 * * 1-5` | 20 minutes | the executor, once orders are placed (~09:01 CT) |
| `sneak-laptop` | `*/10 9-14 * * 1-5` | 10 minutes | the executor, every minute from 08:30 to 15:01 CT |
| `sneak-day` | `0 15 * * 1-5` | 30 minutes | the executor, after the close and the journal |

Then open **Project Settings → Ping key → Create**, and copy the key. Under
**Integrations**, add your email address or a phone app.

### 2. GitHub repository secrets

Go to the repo → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret | Value |
| --- | --- |
| `HC_PING_KEY` | the Healthchecks ping key |
| `ALPACA_KEY_ID` | Alpaca **paper** API key ID (used only by the 14:55 flatten backup) |
| `ALPACA_SECRET_KEY` | Alpaca **paper** secret key |

### 3. cron-job.org: the second job

Clone the 08:45 job and change three things:

- **Title:** `SNEAK flatten backup`
- **Schedule:** 14:55, Monday–Friday
- **Request body:** `{"ref":"main","inputs":{"stage":"flatten"}}`

### 4. The laptop

1. Install Python 3.12 from python.org, and tick **Add python.exe to PATH**.
2. In PowerShell:
   ```
   cd $HOME\Downloads\morning-brief
   git pull
   powershell -ExecutionPolicy Bypass -File tools\install-executor.ps1
   .venv\Scripts\python -m sneak.executor setup
   .venv\Scripts\python -m sneak.executor check
   ```
   `setup` asks for these, and stores the keys in Windows Credential Manager, never in the repo:
   - **mode:** start with **dry**
   - **cash** and **base risk %:** the same numbers you type into the dashboard's sizer
   - **max entries**
   - the **Healthchecks ping key**
   - the **Alpaca paper keys**
   - the **GitHub token**
3. `check` should print `All good.`, and `sneak-laptop` should turn green on Healthchecks.
4. `.venv\Scripts\python -m sneak.executor selftest` replays seven scripted trading days
   against a fake broker. It should print `selftest PASSED`.

Keep the laptop **plugged in, signed in (locked is fine) and online** on trading days. The
installer sets "never sleep on AC power". The task wakes the computer at 08:30 if it's asleep.

## Going from dry to paper

In **dry** mode, the executor does everything except place orders. It logs what it would have
placed, and writes it to `~\.sneak\journal.csv`. After 5 trading days where every dry line
matches the dashboard (symbols, shares, prices), run `setup` again and choose **paper**.

## What runs when (CT, weekdays)

| Time | What happens |
| --- | --- |
| 08:30 | Task Scheduler starts the executor. It checks the account is flat, the keys work, the clock is right, and the kill switch is off |
| 08:45 | cron-job.org starts the scan; `sneak-scan` gets its start ping |
| 08:50 | The executor starts the scan itself if no run began in the last 15 minutes |
| ~09:01 | The scan publishes `docs/orders.json`. The executor places the buy-stops and pings `sneak-orders` |
| 09:00–09:15 | An entry is cancelled if price trades at or below its stop first. All unfilled entries are cancelled at 09:15 |
| on fill | Two exits per trade: the larger half at Target 1, the rest at Target 2, both with the red-candle stop |
| Target 1 fills | The Target 2 exit is re-placed with its stop at the entry price |
| 14:50 | The executor cancels everything and sells what's left at market (10 minutes before the close, also on half days) |
| 14:55 | The cloud backup closes anything still open from today's SNEAK orders, and alerts if it had to |
| 15:01 | The journal is written and `sneak-day` gets the day's summary |

## When an alert comes

| Alert | Meaning | Do this |
| --- | --- | --- |
| `sneak-scan` down | No scan run started, or it failed | Actions → SNEAK → Run workflow → `all` before 09:14 CT. Check cron-job.org's history and the token's expiry date |
| `sneak-orders` down or fail | The laptop placed nothing, or the preflight refused | Read the message. Enter the dashboard's orders by hand if needed |
| `sneak-laptop` down | The laptop is asleep, offline or crashed | The exits already sit at Alpaca, so open trades are protected. Wake the laptop: the task restarts and adopts its own orders |
| `sneak-day` fail ("cloud flatten closed …") | The laptop didn't flatten | Nothing is open now. Check the laptop log before tomorrow |
| `sneak-day` down | The executor didn't finish the day | Check Alpaca for open positions or orders, and close them by hand before 15:00 |

Logs: `~\.sneak\logs\YYYY-MM-DD.log`. Journal: `~\.sneak\journal.csv`.

## Stopping it

- **Kill switch:** set `"kill": true` in `control/kill.json`. The GitHub web editor works from a phone.
  This stops new entries; exits already working keep running, and the 14:50 flatten still happens.
  Alternatively, create an empty file `~\.sneak\KILL` on the laptop.
- **Pause the scan:** disable the cron-job.org jobs.
- **Remove the executor:** in PowerShell, run `Unregister-ScheduledTask -TaskName "SNEAK executor"`.

## Limits built in

- Paper only. `live` mode is refused until a Schwab adapter exists.
- At most `max_entries` orders a day, in rank order.
- Total position never exceeds `cash`, the same rule as the dashboard's sizer.
- After `max_daily_loss_r` (default 3R) of realised loss, everything is cancelled and closed.
- Every order has the ID `sneak-YYYY-MM-DD-SYMBOL-leg`. A restart adopts its own orders instead
  of placing them twice. The cloud flatten touches only symbols with those IDs.
- The executor won't trade if the account holds positions it didn't open today, or if the list
  is from another day or was published after the window.
