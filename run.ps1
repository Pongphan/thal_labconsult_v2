[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 8501,
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    throw 'Project Python is missing. Run .\scripts\setup.ps1 first.'
}

Push-Location -LiteralPath $projectRoot
try {
    & $pythonExe -X utf8 scripts/check_environment.py
    if ($LASTEXITCODE -ne 0) {
        throw 'Environment check failed. See docs/LOCAL_SETUP.md for repair instructions.'
    }
    if (-not $Check) {
        Write-Host "Open http://127.0.0.1:$Port ; press Ctrl+C to stop."
        # Explicit flags preserve local-only behavior even with global/env overrides.
        & $pythonExe -X utf8 -m streamlit run app.py `
            --server.address=127.0.0.1 --server.port=$Port `
            --browser.serverAddress=127.0.0.1 --browser.gatherUsageStats=false
        if ($LASTEXITCODE -ne 0) { throw 'Streamlit exited with an error.' }
    }
}
finally {
    Pop-Location
}
