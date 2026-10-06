param(
    [Parameter(Mandatory=$false)]
    [string]$ProjectPath = "$env:USERPROFILE\Documents\DevourLincolnshireNewsDesk"
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectPath
$Python = Join-Path $ProjectPath ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "NewsDesk Python was not found: $Python" }
if (-not (Test-Path (Join-Path $ProjectPath "jobs_web_server.py"))) {
    throw "Jobs Desk is not installed in $ProjectPath"
}

$TokenFile = Join-Path $ProjectPath "data\jobs_local_test_token.txt"
if (Test-Path $TokenFile) {
    $JobsToken = (Get-Content -LiteralPath $TokenFile -Raw).Trim()
}
else {
    $Generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $TokenBytes = New-Object byte[] 48
        $Generator.GetBytes($TokenBytes)
    } finally {
        $Generator.Dispose()
    }
    $JobsToken = [Convert]::ToBase64String($TokenBytes)
}
$env:JOBS_ADMIN_TOKEN = $JobsToken
$env:JOBS_HOST = "127.0.0.1"
$env:PORT = "8080"
$env:JOBS_PUBLIC_BASE_URL = "http://127.0.0.1:8080"

New-Item -ItemType Directory -Path (Split-Path -Parent $TokenFile) -Force | Out-Null
Set-Content -LiteralPath $TokenFile -Value $JobsToken -Encoding UTF8

Write-Host ""
Write-Host "LOCAL JOBS DESK SERVICE" -ForegroundColor Green
Write-Host "Form: http://127.0.0.1:8080/jobs/advertise/devour_jobs_lincolnshire"
Write-Host "Jobs Desk API URL: http://127.0.0.1:8080"
Write-Host "Editorial token saved to: $TokenFile" -ForegroundColor Yellow
Write-Host "Leave this window open while testing. Press Ctrl+C to stop."
Write-Host ""

& $Python (Join-Path $ProjectPath "jobs_web_server.py")
