#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Automated release: bump version, commit, tag, and release

.PARAMETER Version
    Version number (e.g., "0.2.0") or bump type ("major", "minor", "patch")

.EXAMPLE
    & .\scripts\release.ps1 -Version 0.2.0
    & .\scripts\release.ps1 -Version patch     # Auto-increment patch
#>

param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 Release Automation" -ForegroundColor Cyan
Write-Host ""

# Read current version
$PyprojectPath = "pyproject.toml"
$Content = Get-Content $PyprojectPath -Raw
$CurrentMatch = $Content | Select-String 'version = "([^"]+)"'
if (-not $CurrentMatch) {
    Write-Host "❌ Could not find version in pyproject.toml" -ForegroundColor Red
    exit 1
}

$CurrentVersion = $CurrentMatch.Matches[0].Groups[1].Value
Write-Host "Current version: $CurrentVersion" -ForegroundColor Yellow

# Determine new version
if (-not $Version) {
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Yellow
    Write-Host "  1. major  (e.g., 0.1.0 → 1.0.0)"
    Write-Host "  2. minor  (e.g., 0.1.0 → 0.2.0)"
    Write-Host "  3. patch  (e.g., 0.1.0 → 0.1.1)"
    Write-Host "  4. custom (enter version manually)"
    Write-Host ""
    $Choice = Read-Host "Enter choice (1-4)"

    $Parts = $CurrentVersion.Split(".")
    [int]$Major = $Parts[0]
    [int]$Minor = $Parts[1]
    [int]$Patch = $Parts[2]

    switch ($Choice) {
        "1" { $Major++; $Minor = 0; $Patch = 0 }
        "2" { $Minor++; $Patch = 0 }
        "3" { $Patch++ }
        "4" { $Version = Read-Host "Enter new version (e.g., 0.2.0)"; break }
        default { Write-Host "Invalid choice"; exit 1 }
    }

    if (-not $Version) {
        $Version = "$Major.$Minor.$Patch"
    }
} elseif ($Version -match "^(major|minor|patch)$") {
    # Parse semantic version bump
    $Parts = $CurrentVersion.Split(".")
    [int]$Major = $Parts[0]
    [int]$Minor = $Parts[1]
    [int]$Patch = $Parts[2]

    switch ($Version) {
        "major" { $Major++; $Minor = 0; $Patch = 0 }
        "minor" { $Minor++; $Patch = 0 }
        "patch" { $Patch++ }
    }
    $Version = "$Major.$Minor.$Patch"
}

Write-Host ""
Write-Host "New version: $Version" -ForegroundColor Green
Write-Host ""

$Confirm = Read-Host "Continue with release? (y/n)"
if ($Confirm -ne "y") {
    Write-Host "Cancelled" -ForegroundColor Yellow
    exit 0
}

# Update version in pyproject.toml
Write-Host ""
Write-Host "📝 Updating version in pyproject.toml..." -ForegroundColor Cyan
$NewContent = $Content -replace 'version = "[^"]+"', "version = `"$Version`""
Set-Content $PyprojectPath $NewContent -Encoding UTF8

# Stage and commit
Write-Host "📦 Creating git commit..." -ForegroundColor Cyan
git add pyproject.toml
git commit -m "Bump version to $Version" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Git commit failed" -ForegroundColor Red
    exit 1
}

# Create annotated tag
Write-Host "🏷️  Creating git tag..." -ForegroundColor Cyan
$TagMsg = "Release $Version"
git tag -a "v$Version" -m $TagMsg 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Git tag failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ Release prepared!" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Review changes:  git log --oneline -5"
Write-Host "  2. Push to GitHub:  git push origin main && git push origin v$Version"
Write-Host "  3. Workflow runs automatically:"
Write-Host "     - Tests all platforms"
Write-Host "     - Builds wheel + sdist"
Write-Host "     - Creates GitHub Release"
Write-Host ""
Write-Host "📖 See: .github/workflows/release.yml" -ForegroundColor Gray
