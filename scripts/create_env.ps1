<#
.SYNOPSIS
    Create or update the 'barthelona' conda environment and install the hash-locked dependencies.

.DESCRIPTION
    1. Creates the env from environment.yml (python + pip from conda-forge), or updates it if it exists.
    2. Installs every Python package from requirements/<deps>.win.lock with --require-hashes.
    3. Installs the barthelona package itself in editable mode (--no-deps).
    Works in Windows PowerShell 5.1 and PowerShell 7. Does not change any machine-wide setting.

.PARAMETER Deps
    'dev' (default: runtime + test/lint tools) or 'runtime'.

.PARAMETER Recreate
    Remove the environment first and build it from scratch.

.PARAMETER Name
    Environment name. Default: barthelona.

.EXAMPLE
    .\scripts\create_env.ps1
    . .\scripts\activate.ps1

.EXAMPLE
    .\scripts\create_env.ps1 -Recreate
#>
[CmdletBinding()]
param(
    [ValidateSet('dev', 'runtime')]
    [string]$Deps = 'dev',
    [switch]$Recreate,
    [string]$Name = 'barthelona'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $RepoRoot 'environment.yml'
$LockFile = Join-Path $RepoRoot "requirements\$Deps.win.lock"

function Get-CondaExe {
    if ($env:CONDA_EXE -and (Test-Path $env:CONDA_EXE)) { return $env:CONDA_EXE }
    $cmd = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:USERPROFILE 'miniconda3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'anaconda3\Scripts\conda.exe'),
        (Join-Path $env:ProgramData 'miniconda3\Scripts\conda.exe'),
        (Join-Path $env:ProgramData 'anaconda3\Scripts\conda.exe')
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    throw 'conda not found. Install Miniconda or add conda.exe to PATH.'
}

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Exe $($Arguments -join ' ')" }
}

function Get-EnvPrefix {
    param([string]$Conda, [string]$EnvName)
    $json = & $Conda env list --json | Out-String | ConvertFrom-Json
    foreach ($p in $json.envs) {
        if ((Split-Path -Leaf $p) -eq $EnvName -and (Split-Path -Leaf (Split-Path -Parent $p)) -eq 'envs') { return $p }
    }
    return $null
}

$Conda = Get-CondaExe
Write-Host "conda: $Conda"

if (-not (Test-Path $LockFile)) {
    throw "Lock file not found: $LockFile. Generate it with .\scripts\lock.ps1"
}

$Prefix = Get-EnvPrefix -Conda $Conda -EnvName $Name
if ($Prefix -and $Recreate -and $env:CONDA_PREFIX -and ((Resolve-Path $env:CONDA_PREFIX).Path -eq (Resolve-Path $Prefix).Path)) {
    throw "Environment '$Name' is active in this shell. Run 'conda deactivate' (or use a new terminal), then retry -Recreate."
}
if ($Prefix -and $Recreate) {
    Write-Host "Removing environment '$Name' ($Prefix)..."
    Invoke-Native $Conda @('env', 'remove', '--name', $Name, '--yes')
    $Prefix = $null
}

if ($Prefix) {
    Write-Host "Updating environment '$Name' from environment.yml..."
    Invoke-Native $Conda @('env', 'update', '--name', $Name, '--file', $EnvFile, '--prune')
} else {
    Write-Host "Creating environment '$Name' from environment.yml..."
    Invoke-Native $Conda @('env', 'create', '--name', $Name, '--file', $EnvFile)
    $Prefix = Get-EnvPrefix -Conda $Conda -EnvName $Name
    if (-not $Prefix) { throw "Environment '$Name' was not created." }
}

$Python = Join-Path $Prefix 'python.exe'
if (-not (Test-Path $Python)) { throw "Python not found in environment: $Python" }

Push-Location $RepoRoot
try {
    Write-Host "Installing locked dependencies from requirements\$Deps.win.lock..."
    Invoke-Native $Python @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-warn-script-location', '--require-hashes', '--no-deps', '-r', $LockFile)
    # Updates must leave the env exactly as the lock says (e.g. switching -Deps dev -> runtime).
    Write-Host 'Removing packages that are not in the lock...'
    Invoke-Native $Python @((Join-Path $RepoRoot 'scripts\prune_env.py'), $LockFile)
    # --require-hashes cannot be combined with an editable install, so the package goes in a separate step.
    Write-Host 'Installing barthelona (editable, no deps)...'
    Invoke-Native $Python @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-warn-script-location', '--no-deps', '-e', '.')
    Invoke-Native $Python @('-m', 'pip', 'check')
} finally {
    Pop-Location
}

$version = & $Python -c 'import sys; print(sys.version.split()[0])'
Write-Host ''
Write-Host "Environment '$Name' is ready (Python $version, deps: $Deps)." -ForegroundColor Green
Write-Host 'Activate it in this shell with:  . .\scripts\activate.ps1'
