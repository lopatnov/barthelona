<#
.SYNOPSIS
    Regenerate the hash-locked requirement files from pyproject.toml.

.DESCRIPTION
    Produces requirements/{runtime,dev}.{win,linux}.lock with uv (Python 3.13).
    Existing pins are kept unless -Upgrade is given (uv treats the old lock as preferences).
    After locking, reinstall with .\scripts\create_env.ps1.

.PARAMETER Upgrade
    Allow every package to move to the newest version permitted by pyproject.toml.

.PARAMETER UpgradePackage
    Upgrade only the named packages, e.g. -UpgradePackage langgraph,streamlit
#>
[CmdletBinding()]
param(
    [switch]$Upgrade,
    [string[]]$UpgradePackage = @()
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot

# Prefer the uv pinned in the barthelona env (dev lock), so locks are produced by the same uv everywhere.
$EnvPython = $null
foreach ($c in @($(if ($env:CONDA_PREFIX -and (Split-Path -Leaf $env:CONDA_PREFIX) -eq 'barthelona') { $env:CONDA_PREFIX }),
                 $env:BARTHELONA_ENV_PREFIX,
                 (Join-Path $env:USERPROFILE 'miniconda3\envs\barthelona'),
                 (Join-Path $env:USERPROFILE 'anaconda3\envs\barthelona'))) {
    if ($c -and (Test-Path (Join-Path $c 'Scripts\uv.exe'))) { $EnvPython = Join-Path $c 'python.exe'; break }
}
if ($EnvPython) {
    $UvCmd = @($EnvPython, '-m', 'uv')
} else {
    $uv = Get-Command uv -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $uv) { throw 'uv not found. Create the env (.\scripts\create_env.ps1; dev deps include uv) or install uv.' }
    $UvCmd = @($uv.Source)
    Write-Warning ("Using uv from PATH (" + ((& $uv.Source --version) -join ' ') + "), not the env's pinned uv; lock output may differ.")
}

$Platforms = [ordered]@{ win = 'x86_64-pc-windows-msvc'; linux = 'x86_64-unknown-linux-gnu' }
$Profiles = [ordered]@{ runtime = @(); dev = @('--extra', 'dev') }

Push-Location $RepoRoot
try {
    foreach ($plat in $Platforms.Keys) {
        foreach ($prof in $Profiles.Keys) {
            $out = "requirements/$prof.$plat.lock"
            $uvArgs = @('pip', 'compile', 'pyproject.toml',
                        '--python-version', '3.13',
                        '--python-platform', $Platforms[$plat],
                        '--generate-hashes',
                        '--custom-compile-command', '.\scripts\lock.ps1',
                        '--quiet',
                        '-o', $out) + $Profiles[$prof]
            if ($Upgrade) { $uvArgs += '--upgrade' }
            foreach ($p in $UpgradePackage) { $uvArgs += @('--upgrade-package', $p) }
            Write-Host "Locking $out"
            $exe = $UvCmd[0]
            $pre = @()
            if ($UvCmd.Count -gt 1) { $pre = $UvCmd[1..($UvCmd.Count - 1)] }
            & $exe @pre @uvArgs
            if ($LASTEXITCODE -ne 0) { throw "uv pip compile failed for $out" }
        }
    }
    # Record which dependency declaration these locks were built from (see scripts/deps_fingerprint.py).
    $py = $null
    if ($env:CONDA_PREFIX -and (Test-Path (Join-Path $env:CONDA_PREFIX 'python.exe'))) { $py = Join-Path $env:CONDA_PREFIX 'python.exe' }
    elseif (Test-Path (Join-Path $env:USERPROFILE 'miniconda3\envs\barthelona\python.exe')) { $py = Join-Path $env:USERPROFILE 'miniconda3\envs\barthelona\python.exe' }
    if ($py) {
        & $py 'scripts/deps_fingerprint.py' '--write'
        if ($LASTEXITCODE -ne 0) { throw 'Writing the dependency fingerprint failed.' }
    } else {
        Write-Warning 'No barthelona python found; requirements/pyproject-deps.sha256 was not updated.'
    }
} finally {
    Pop-Location
}
Write-Host 'Locks updated. Review the diff (git diff requirements/), then run .\scripts\create_env.ps1' -ForegroundColor Green
