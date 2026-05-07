param([string]$LogPath = "logs/20260505.log")

$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'

# wait until current monthly run finishes (success or aborted)
$deadline = (Get-Date).AddMinutes(180)
while ((Get-Date) -lt $deadline) {
    if (Test-Path $LogPath) {
        $tail = Get-Content $LogPath -Tail 5 -Encoding utf8 -ErrorAction SilentlyContinue
        if ($tail -match 'Monthly run done|Monthly run aborted|Failure report written') { break }
    }
    Start-Sleep -Seconds 30
}

Write-Output "[$(Get-Date)] monthly run finished, retrying failed fleet codes..."
python -m backend.retry_failed *> "logs/retry_run.out"
Write-Output "[$(Get-Date)] retry done"
