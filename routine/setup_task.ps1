# Registers the daily routine in Windows Task Scheduler (18:45 IST, Mon-Fri).
# Run once from an elevated PowerShell:
#   powershell -ExecutionPolicy Bypass -File routine\setup_task.ps1

$repo   = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { Write-Error "venv python not found at $python"; exit 1 }

$action  = New-ScheduledTaskAction -Execute $python -Argument "-m routine.run_daily" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 18:45
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName "MomentumDailyRoutine" `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "EOD momentum screen + digest email (routine/run_daily.py)" -Force

Write-Host "Registered 'MomentumDailyRoutine' for 18:45 Mon-Fri."
Write-Host "Test it now with:  Start-ScheduledTask -TaskName MomentumDailyRoutine"
