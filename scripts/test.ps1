#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run tests for tmux-w

.PARAMETER Pattern
    Filter tests by pattern (pytest -k syntax)

.PARAMETER Coverage
    Include coverage report

.EXAMPLE
    & .\scripts\test.ps1              # Run all tests
    & .\scripts\test.ps1 -Pattern "keys" # Run tests matching "keys"
    & .\scripts\test.ps1 -Coverage    # With coverage report
#>

param(
    [string]$Pattern = "",
    [switch]$Coverage = $false
)

$ErrorActionPreference = "Stop"

# Activate venv if not already
$VenvScript = Join-Path ".venv" "Scripts\Activate.ps1"
if (Test-Path $VenvScript) {
    & $VenvScript
}

Write-Host "Running tests..." -ForegroundColor Cyan

$Args = @("tests/")
if ($Pattern) {
    $Args += "-k", $Pattern
}
if ($Coverage) {
    Write-Host " (with coverage)" -ForegroundColor Gray
    python -m pip install pytest-cov -q 2>/dev/null
    $Args += "--cov=tmuxw", "--cov-report=term-missing"
}

python -m pytest @Args -v --tb=short

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "OK: All tests passed!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "ERROR: Tests failed" -ForegroundColor Red
    exit 1
}
