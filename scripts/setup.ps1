#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Setup script for tmux-w development environment

.DESCRIPTION
    Creates/updates virtual environment and installs dependencies
    Runs in ~30 seconds (vs 5+ minutes manual setup)
#>

$ErrorActionPreference = "Stop"
$VenvDir = ".venv"
$RequiredPythonVersion = "3.10"

Write-Host "🔧 tmux-w Development Setup" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "1️⃣  Checking Python..." -ForegroundColor Yellow
$PythonCmd = if (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$PythonVersion = & $PythonCmd --version 2>&1
Write-Host "   Found: $PythonVersion"

# Create/update venv
Write-Host "2️⃣  Setting up virtual environment..." -ForegroundColor Yellow
if (Test-Path $VenvDir) {
    Write-Host "   Venv exists, upgrading..."
    & $PythonCmd -m venv --upgrade $VenvDir
} else {
    Write-Host "   Creating new venv..."
    & $PythonCmd -m venv $VenvDir
}

# Activate
$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
Write-Host "3️⃣  Activating venv..." -ForegroundColor Yellow
& $ActivateScript

# Install dependencies
Write-Host "4️⃣  Installing dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip setuptools wheel 2>&1 | Out-Null
python -m pip install -e . 2>&1 | Out-Null

# Install dev deps if pyproject.toml has [project.optional-dependencies]
Write-Host "5️⃣  Installing dev tools..." -ForegroundColor Yellow
python -m pip install pytest ruff --upgrade 2>&1 | Out-Null

Write-Host ""
Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Cyan
Write-Host "   Run tests:  & .\scripts\test.ps1"
Write-Host "   Lint code:  & .\scripts\lint.ps1"
Write-Host "   Dev all:    & .\scripts\dev.ps1"
Write-Host ""
