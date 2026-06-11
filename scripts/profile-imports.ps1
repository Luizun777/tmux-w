#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Profile Python import times to identify slow imports

.DESCRIPTION
    Uses Python's importlib to measure time spent importing each module.
    Helps identify bottlenecks in startup time.

.EXAMPLE
    & .\scripts\profile-imports.ps1
#>

$ErrorActionPreference = "Stop"

# Use the venv python directly (no activation needed)
$Python = Join-Path ".venv" "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Host "Profiling Python import times..." -ForegroundColor Cyan
Write-Host ""

$PyCode = @'
import importlib
import timeit

modules_to_test = [
    "ctypes",
    "msvcrt",
    "socket",
    "threading",
    "json",
    "time",
    "subprocess",
    "winpty",
    "pyte",
    "tmuxw.keys",
    "tmuxw.client",
    "tmuxw.server",
    "tmuxw.pane",
    "tmuxw.render",
]

print("Module Import Times (5 iterations, avg ms):\n")
print(f"{'Module':<30} {'Time (ms)':<15} {'Note':<20}")
print("-" * 65)

slow_modules = []

for module in modules_to_test:
    try:
        # Time 5 imports
        times = []
        for _ in range(5):
            start = timeit.default_timer()
            importlib.import_module(module)
            end = timeit.default_timer()
            times.append((end - start) * 1000)

        avg_time = sum(times) / len(times)
        status = ""
        if avg_time > 50:
            status = "SLOW"
            slow_modules.append((module, avg_time))
        elif avg_time > 10:
            status = "MEDIUM"

        print(f"{module:<30} {avg_time:<15.2f} {status:<20}")
    except Exception as e:
        print(f"{module:<30} ERROR: {str(e)[:15]}")

if slow_modules:
    print("\nWARNING: Slow modules (>50ms) - candidates for lazy-loading:")
    for mod, time in sorted(slow_modules, key=lambda x: x[1], reverse=True):
        print(f" {mod}: {time:.2f}ms")
else:
    print("\nOK: No slow imports detected (all < 50ms)")

# Total import time of tmuxw
print("\nTotal tmuxw import time:")
start = timeit.default_timer()
import tmuxw
end = timeit.default_timer()
print(f" tmuxw module: {(end - start) * 1000:.2f}ms")
'@

$PyCode | & $Python -

Write-Host ""
Write-Host "OK: Profile complete" -ForegroundColor Green
