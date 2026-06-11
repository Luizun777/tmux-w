#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Lint and format check for tmux-w

.PARAMETER Fix
    Auto-fix formatting issues

.EXAMPLE
    & .\scripts\lint.ps1        # Check code style
    & .\scripts\lint.ps1 -Fix   # Auto-fix issues
#>

param(
    [switch]$Fix = $false
)

$ErrorActionPreference = "Stop"

# Activate venv if not already
$VenvScript = Join-Path ".venv" "Scripts\Activate.ps1"
if (Test-Path $VenvScript) {
    & $VenvScript
}

Write-Host "📋 Linting code..." -ForegroundColor Cyan

# Install ruff if needed
python -m pip install ruff -q 2>/dev/null

Write-Host ""
Write-Host "Checking: tmuxw/" -ForegroundColor Yellow
if ($Fix) {
    ruff check --fix tmuxw 2>&1
    ruff format tmuxw 2>&1
} else {
    ruff check tmuxw 2>&1
    ruff format --check tmuxw 2>&1
}

Write-Host ""
Write-Host "Checking: tests/" -ForegroundColor Yellow
if ($Fix) {
    ruff check --fix tests 2>&1
    ruff format tests 2>&1
} else {
    ruff check tests 2>&1
    ruff format --check tests 2>&1
}

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Linting passed!" -ForegroundColor Green
} else {
    if ($Fix) {
        Write-Host ""
        Write-Host "⚠️  Fixed some issues. Review and commit." -ForegroundColor Yellow
    } else {
        Write-Host ""
        Write-Host "❌ Linting issues found. Run with -Fix to auto-fix." -ForegroundColor Red
        exit 1
    }
}
