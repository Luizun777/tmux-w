#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Master development script for tmux-w

.PARAMETER Mode
    "full" (default): setup + lint + test
    "quick": test only
    "setup": setup only
    "test": test only
    "lint": lint only

.EXAMPLE
    & .\scripts\dev.ps1                # Full mode
    & .\scripts\dev.ps1 -Mode quick    # Test only
    & .\scripts\dev.ps1 -Mode setup    # Setup only
#>

param(
    [ValidateSet("full", "quick", "setup", "test", "lint")]
    [string]$Mode = "full"
)

$ErrorActionPreference = "Stop"
$StartTime = Get-Date

function Show-Section {
    param([string]$Title, [string]$Icon = "->")
    Write-Host ""
    Write-Host "$Icon $Title" -ForegroundColor Cyan
    Write-Host ""
}

function Show-Result {
    param([string]$Status, [string]$Color = "Green")
    Write-Host ""
    Write-Host $Status -ForegroundColor $Color
}

# Activate venv
$VenvScript = Join-Path ".venv" "Scripts\Activate.ps1"
if (Test-Path $VenvScript) {
    & $VenvScript
}

Write-Host " tmux-w Development" -ForegroundColor Cyan
Write-Host "Mode: $Mode" -ForegroundColor Gray

switch ($Mode) {
    "full" {
        # Full: Setup + Lint + Test
        Show-Section "[1]  SETUP" "[1] "
        & .\scripts\setup.ps1
        if ($LASTEXITCODE -ne 0) { exit 1 }

        Show-Section "[2]  LINT" "[2] "
        & .\scripts\lint.ps1
        if ($LASTEXITCODE -ne 0) { exit 1 }

        Show-Section "[3]  TEST" "[3] "
        & .\scripts\test.ps1
        if ($LASTEXITCODE -ne 0) { exit 1 }

        $Duration = ((Get-Date) - $StartTime).TotalSeconds
        Show-Result "OK: All checks passed! ($([int]$Duration)s)" "Green"
    }

    "quick" {
        Show-Section "QUICK TEST (no setup/lint)" ""
        & .\scripts\test.ps1
        if ($LASTEXITCODE -ne 0) { exit 1 }

        $Duration = ((Get-Date) - $StartTime).TotalSeconds
        Show-Result "OK: Tests passed! ($([int]$Duration)s)" "Green"
    }

    "setup" {
        Show-Section "SETUP" ""
        & .\scripts\setup.ps1
        if ($LASTEXITCODE -ne 0) { exit 1 }

        Show-Result "OK: Setup complete!" "Green"
    }

    "test" {
        Show-Section "TEST" ""
        & .\scripts\test.ps1
        if ($LASTEXITCODE -ne 0) { exit 1 }

        $Duration = ((Get-Date) - $StartTime).TotalSeconds
        Show-Result "OK: Tests passed! ($([int]$Duration)s)" "Green"
    }

    "lint" {
        Show-Section "LINT" ""
        & .\scripts\lint.ps1
        if ($LASTEXITCODE -ne 0) { exit 1 }

        Show-Result "OK: Linting passed!" "Green"
    }
}

Write-Host ""
Write-Host "Tips:" -ForegroundColor Yellow
Write-Host " & .\scripts\test.ps1 -Pattern 'keys'    # Filter tests"
Write-Host " & .\scripts\test.ps1 -Coverage          # Show coverage"
Write-Host " & .\scripts\lint.ps1 -Fix               # Auto-fix style"
Write-Host ""
