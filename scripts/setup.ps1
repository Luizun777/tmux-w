#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Setup script for tmux-w development environment

.DESCRIPTION
    Creates/updates virtual environment and installs dependencies
    Runs in ~30 seconds (vs 5+ minutes manual setup)

    NOTE: ASCII-only on purpose. Emoji bytes break Windows PowerShell 5.1
    parsing when the file is read without a UTF-8 BOM.
#>

$ErrorActionPreference = "Stop"
$VenvDir = ".venv"

Write-Host "[tmux-w] Development Setup" -ForegroundColor Cyan
Write-Host ""

# Check Python: pywinpty 2.0.13 only loads on Python 3.10-3.12.
Write-Host "[1/5] Checking Python (3.10-3.12 required)..." -ForegroundColor Yellow
$PythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in @("3.12", "3.11", "3.10")) {
        & py "-$v" --version 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $PythonCmd = @("py", "-$v")
            break
        }
    }
}
if ($null -eq $PythonCmd) {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
        if ($ver -in @("3.10", "3.11", "3.12")) {
            $PythonCmd = @("python")
        }
    }
}
if ($null -eq $PythonCmd) {
    Write-Host "ERROR: No Python 3.10-3.12 found. pywinpty does not work on 3.13+." -ForegroundColor Red
    Write-Host "Install Python 3.12: winget install Python.Python.3.12" -ForegroundColor Red
    exit 1
}
$PythonVersion = & $PythonCmd[0] $PythonCmd[1..$PythonCmd.Length] --version 2>&1
Write-Host "   Found: $PythonVersion (via $($PythonCmd -join ' '))"

# Create/recreate venv. If the existing venv runs an incompatible Python,
# wipe it: venv --upgrade cannot change the interpreter version.
Write-Host "[2/5] Setting up virtual environment..." -ForegroundColor Yellow
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (Test-Path $VenvPython) {
    $venvVer = & $VenvPython -c "import sys; print('%d.%d' % sys.version_info[:2])"
    if ($venvVer -in @("3.10", "3.11", "3.12")) {
        Write-Host "   Venv exists (Python $venvVer), keeping it"
    } else {
        Write-Host "   Venv has incompatible Python $venvVer, recreating..."
        Remove-Item -Recurse -Force $VenvDir
    }
}
if (-not (Test-Path $VenvPython)) {
    Write-Host "   Creating new venv..."
    & $PythonCmd[0] $PythonCmd[1..$PythonCmd.Length] -m venv $VenvDir
}

# Install dependencies (call venv python directly; no activation needed)
Write-Host "[3/5] Upgrading pip..." -ForegroundColor Yellow
& $VenvPython -m pip install --upgrade pip setuptools wheel --quiet

Write-Host "[4/5] Installing tmuxw + dev tools..." -ForegroundColor Yellow
& $VenvPython -m pip install -e ".[dev]" --quiet

# Smoke test: the import that breaks when the Python version is wrong
Write-Host "[5/5] Verifying pywinpty loads..." -ForegroundColor Yellow
& $VenvPython -c "import winpty, tmuxw; print('   OK: pywinpty + tmuxw import correctly')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pywinpty failed to load. See output above." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "   Run tests:  & .\scripts\test.ps1"
Write-Host "   Lint code:  & .\scripts\lint.ps1"
Write-Host "   Dev all:    & .\scripts\dev.ps1"
Write-Host "   Use it:     .\tmuxw.cmd new -s trabajo"
Write-Host ""
