# install-executor.ps1 — set up the SNEAK executor on this Windows laptop.
#
#   cd $HOME\Downloads\morning-brief
#   powershell -ExecutionPolicy Bypass -File tools\install-executor.ps1
#
# What it does:
#   1. creates .venv in the repo and installs requirements-executor.txt
#   2. registers the "SNEAK executor" task: weekdays at 08:30 (this computer's
#      clock), wakes the computer, starts late if it was off, one copy at a time
#   3. sets "never sleep while plugged in" (skip with -KeepSleepSettings)
# Then run:  .venv\Scripts\python -m sneak.executor setup
param(
  [string]$At = "08:30",
  [switch]$KeepSleepSettings
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "Python is not installed. Install Python 3.12 from python.org (tick 'Add python.exe to PATH'), then run this again."
}
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements-executor.txt
Write-Host "Python environment ready in $Repo\.venv"

$Py = Join-Path $Repo ".venv\Scripts\pythonw.exe"   # pythonw: no console window; logs go to ~\.sneak\logs
$Action   = New-ScheduledTaskAction -Execute $Py -Argument "-m sneak.executor run" -WorkingDirectory $Repo
$Trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $At
$Settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries `
              -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
              -ExecutionTimeLimit (New-TimeSpan -Hours 9) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "SNEAK executor" -Action $Action -Trigger $Trigger -Settings $Settings `
  -Description "Trades the SNEAK orders published at ~09:01 CT. See AUTOMATION.md." -Force | Out-Null
Write-Host "Scheduled task 'SNEAK executor' registered: weekdays at $At (this computer's time zone)."

if (-not $KeepSleepSettings) {
  powercfg /change standby-timeout-ac 0
  Write-Host "Sleep on AC power: never. Keep the laptop plugged in on trading days."
}
Write-Host ""
Write-Host "Next:  .venv\Scripts\python -m sneak.executor setup"
Write-Host "Then:  .venv\Scripts\python -m sneak.executor check"
