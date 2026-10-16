[CmdletBinding()]
param([string]$Python, [switch]$Dev)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $projectRoot '.venv'
$pythonExe = Join-Path $venvPath 'Scripts\python.exe'
$localPython = Join-Path $projectRoot '.tools\python\cpython-3.12.15-windows-x86_64-none\python.exe'
$localUv = Join-Path $projectRoot '.tools\uv\uv.exe'
$lockName = if ($Dev) { 'requirements-dev-lock-win-py312.txt' } else { 'requirements-lock-win-py312.txt' }
$lockFile = Join-Path $projectRoot $lockName
$checkArgs = @('--locked')
if ($Dev) { $checkArgs += '--development' }

Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath $venvPath)) {
        if ($Python) {
            & $Python -m venv $venvPath
        }
        elseif (Test-Path -LiteralPath $localPython -PathType Leaf) {
            & $localPython -m venv $venvPath
        }
        else {
            & py -3.12 -m venv $venvPath
        }
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Supply a CPython 3.12 executable with -Python.' }
    }

    $runtimeWorks = $false
    if (Test-Path -LiteralPath $pythonExe -PathType Leaf) {
        & $pythonExe -c "import sys; print(sys.executable)"
        $runtimeWorks = $LASTEXITCODE -eq 0
    }
    if (-not $runtimeWorks) {
        # Relocated uv venvs contain launchers with an absolute Python path.
        # Recreate their launchers only, preserving the installed packages.
        if ((Test-Path -LiteralPath $localUv -PathType Leaf) -and (Test-Path -LiteralPath $localPython -PathType Leaf)) {
            & $localUv venv $venvPath --allow-existing --python $localPython `
                --offline --no-python-downloads --no-project --no-config --no-cache
            if ($LASTEXITCODE -ne 0) { throw 'Could not repair relocated environment.' }
        }
        else {
            throw 'Existing .venv is not usable with this lockfile. Preserve it, then create a fresh CPython 3.12 environment as described in docs/LOCAL_SETUP.md.'
        }
    }
    & $pythonExe -c "import sys; assert sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32, 'Use 64-bit CPython 3.12 for this lockfile'"
    if ($LASTEXITCODE -ne 0) { throw 'The current environment uses a different Python version. It was preserved; see docs/LOCAL_SETUP.md.' }

    # Already exact and usable: no installer or network is needed.
    & $pythonExe -X utf8 scripts/check_environment.py @checkArgs --dependencies-only
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path -LiteralPath $localUv -PathType Leaf) {
            & $localUv pip install --python $pythonExe --require-hashes --only-binary=:all: -r $lockFile --no-config --no-cache
        }
        else {
            & $pythonExe -m ensurepip --upgrade
            if ($LASTEXITCODE -ne 0) { throw 'Could not initialize pip.' }
            & $pythonExe -m pip install --require-hashes --only-binary=:all: -r $lockFile
        }
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; check network access and the configured package index.' }
    }
    & $pythonExe -X utf8 scripts/check_environment.py @checkArgs
    if ($LASTEXITCODE -ne 0) { throw 'Environment or application checks failed. Read the FAIL messages above.' }
    Write-Host 'Ready. Run .\run.ps1 to start ThalLink on this computer.'
}
finally {
    Pop-Location
}
