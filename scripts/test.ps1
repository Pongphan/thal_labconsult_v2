[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location -LiteralPath $projectRoot
try {
    & $pythonExe -X utf8 scripts/check_environment.py --locked --development
    if ($LASTEXITCODE -ne 0) { throw 'Runtime/test-tool check failed. Run .\scripts\setup.ps1 -Dev.' }
    & $pythonExe -X utf8 -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Correctness lint failed.' }
    & $pythonExe -X utf8 scripts/generate_rule_inventory.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Review inventory is stale; regenerate and review the changes.' }
    # A fresh owned directory avoids reusing pytest caches created by another
    # Windows/sandbox identity. Never delete or change ACLs on shared temp paths.
    $testRunRoot = Join-Path ([IO.Path]::GetTempPath()) ('thallink-test-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $testRunRoot | Out-Null
    $pytestTemp = Join-Path $testRunRoot 'fixtures'
    $pytestCache = 'cache_dir=' + (Join-Path $testRunRoot 'cache')
    & $pythonExe -X utf8 -m pytest --junitxml=artifacts/junit.xml --cov `
        --cov-report=term-missing --cov-report=xml:artifacts/coverage.xml `
        --cov-report=html:artifacts/htmlcov --cov-report=json:artifacts/coverage.json `
        --basetemp $pytestTemp -o $pytestCache
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    & $pythonExe -X utf8 scripts/package_source.py --check
    if ($LASTEXITCODE -ne 0) { throw 'Source package verification failed.' }
}
finally {
    Pop-Location
}
