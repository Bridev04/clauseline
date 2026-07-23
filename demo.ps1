# Clauseline — one-command offline demo launcher (Windows / PowerShell).
#
#   .\demo.ps1
#
# Starts the zero-dependency demo backend (no Docker, no API keys) and the
# Next.js dashboard. Ctrl+C stops both. First run installs frontend deps.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host ""
Write-Host "  Clauseline demo — offline, no keys, no Docker" -ForegroundColor Cyan
Write-Host "  ---------------------------------------------" -ForegroundColor Cyan

# 1. Backend: zero-dependency stdlib server on :8000
Write-Host "  [1/3] Starting demo backend on http://localhost:8000 ..." -ForegroundColor Yellow
$backend = Start-Process -FilePath "python" `
    -ArgumentList "demo_server.py" `
    -WorkingDirectory "$root\backend" -PassThru

# 2. Frontend deps (first run only)
if (-not (Test-Path "$root\frontend\node_modules")) {
    Write-Host "  [2/3] Installing frontend dependencies (first run only, ~1-2 min)..." -ForegroundColor Yellow
    Push-Location "$root\frontend"
    npm install
    Pop-Location
} else {
    Write-Host "  [2/3] Frontend dependencies already installed." -ForegroundColor Yellow
}

# 3. Frontend dev server (foreground)
Write-Host "  [3/3] Starting dashboard on http://localhost:3000 ..." -ForegroundColor Yellow
Write-Host ""
Write-Host "  ==> Open http://localhost:3000/evals when it says 'Ready'." -ForegroundColor Green
Write-Host "      Ctrl+C here stops the demo." -ForegroundColor Green
Write-Host ""

try {
    Push-Location "$root\frontend"
    npm run dev
} finally {
    Pop-Location
    if ($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host ""
    Write-Host "  Demo stopped." -ForegroundColor Cyan
}
