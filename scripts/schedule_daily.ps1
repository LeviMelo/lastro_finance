# Registers the daily snapshot job (`fin ingest daily`) in Windows Task Scheduler (PLAN §4.12).
# Runs at 22:30 local time (after B3's BDI SLA of 21:00 and ANBIMA's evening publication) and again at logon,
# so a laptop that was off catches up: windowed sources (B3 BDI: 21 business days, ANBIMA: ~6) are re-planned
# from the calendar on every run, and today-only registries are simply fetched now.
# Usage (owner, once):  powershell -ExecutionPolicy Bypass -File scripts\schedule_daily.ps1
# Remove:               Unregister-ScheduledTask -TaskName "LASTRO fin ingest daily" -Confirm:$false

$repo = Split-Path -Parent $PSScriptRoot
# the project's own environment: no uv or conda needed when the task runs (create it once with `uv sync`)
$fin = Join-Path $repo ".venv\Scripts\fin.exe"
if (-not (Test-Path $fin)) { throw "not found: $fin (run 'uv sync' in $repo first)" }
$log = Join-Path $repo "data\logs\scheduler.log"
$cmd = "/c cd /d `"$repo`" && set PYTHONUTF8=1 && `"$fin`" ingest daily >> `"$log`" 2>&1"

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $cmd -WorkingDirectory $repo
$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At 22:30),
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME)
)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "LASTRO fin ingest daily" -Action $action -Trigger $triggers -Settings $settings `
    -Description "LASTRO: archive ephemeral financial sources daily" -Force | Out-Null
Get-ScheduledTask -TaskName "LASTRO fin ingest daily" | Select-Object TaskName, State
