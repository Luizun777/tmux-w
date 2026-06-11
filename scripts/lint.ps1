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

# Use the venv python directly (no activation needed)
$Python = Join-Path ".venv" "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "ERROR: venv not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Linting code..." -ForegroundColor Cyan
Write-Host ""

$Failed = $false
foreach ($target in @("tmuxw", "tests")) {
    Write-Host "Checking: $target/" -ForegroundColor Yellow
    if ($Fix) {
        & $Python -m ruff check --fix $target
        if ($LASTEXITCODE -ne 0) { $Failed = $true }
        & $Python -m ruff format $target
        if ($LASTEXITCODE -ne 0) { $Failed = $true }
    } else {
        & $Python -m ruff check $target
        if ($LASTEXITCODE -ne 0) { $Failed = $true }
        & $Python -m ruff format --check $target
        if ($LASTEXITCODE -ne 0) { $Failed = $true }
    }
}

Write-Host ""
if (-not $Failed) {
    Write-Host "OK: Linting passed!" -ForegroundColor Green
} elseif ($Fix) {
    Write-Host "WARNING: Fixed some issues. Review and commit." -ForegroundColor Yellow
} else {
    Write-Host "ERROR: Linting issues found. Run with -Fix to auto-fix." -ForegroundColor Red
    exit 1
}
