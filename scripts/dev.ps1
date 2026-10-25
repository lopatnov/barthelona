<#
.SYNOPSIS
    Run one command with the barthelona conda env on PATH, without activating it. .env is loaded only with
    the opt-in -LoadEnv switch (D-057).

.DESCRIPTION
    Agent tool shells (Claude Code, Codex) start fresh for every call, so an activated env does not carry
    over. This wrapper prepends the env's directories to PATH for this one command, sets PYTHONUTF8 and
    WSL_UTF8, runs the command, restores PATH and returns its exit code. API keys from .env are NOT loaded
    unless the first argument is -LoadEnv: then each KEY=VALUE line of the repository's .env that is not
    already set in the process is placed in the environment of this one command and removed afterwards.
    The values are never printed, logged or returned; the agent still never reads the file itself.
    Works in Windows PowerShell 5.1 and PowerShell 7. Env lookup: active barthelona env, then
    $env:BARTHELONA_ENV_PREFIX, then the usual miniconda/anaconda locations, then `conda env list --json`.

.EXAMPLE
    .\scripts\dev.ps1 ruff check .
    .\scripts\dev.ps1 python -m pytest -q
    .\scripts\dev.ps1 python scripts/sync_agent_configs.py --check
    .\scripts\dev.ps1 -LoadEnv python -m barthelona zetaris status
#>
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$__argv = @($args)
$__loadEnv = $false
if ($__argv.Count -gt 0 -and $__argv[0] -eq '-LoadEnv') {
    $__loadEnv = $true
    if ($__argv.Count -gt 1) { $__argv = @($__argv[1..($__argv.Count - 1)]) } else { $__argv = @() }
}
if ($__argv.Count -eq 0) {
    Write-Output 'usage: .\scripts\dev.ps1 [-LoadEnv] <command> [args...]   e.g. .\scripts\dev.ps1 ruff check .'
    exit 2
}

$__bartPrefix = $null
if ($env:CONDA_PREFIX -and (Split-Path -Leaf $env:CONDA_PREFIX) -eq 'barthelona') { $__bartPrefix = $env:CONDA_PREFIX }
if (-not $__bartPrefix -and $env:BARTHELONA_ENV_PREFIX) { $__bartPrefix = $env:BARTHELONA_ENV_PREFIX }
if (-not $__bartPrefix) {
    foreach ($__c in @((Join-Path $env:USERPROFILE 'miniconda3\envs\barthelona'),
            (Join-Path $env:USERPROFILE 'anaconda3\envs\barthelona'),
            (Join-Path $env:ProgramData 'miniconda3\envs\barthelona'))) {
        if (Test-Path (Join-Path $__c 'python.exe')) { $__bartPrefix = $__c; break }
    }
}
if (-not $__bartPrefix) {
    $__conda = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($__conda) {
        try {
            $__json = & $__conda.Source env list --json | Out-String | ConvertFrom-Json
            $__bartPrefix = @($__json.envs | Where-Object { (Split-Path -Leaf $_) -eq 'barthelona' })[0]
        }
        catch {
            # Fall through to the "env not found" message below, but say why the lookup failed.
            [Console]::Error.WriteLine("conda env list failed: $($_.Exception.Message)")
        }
    }
}
if (-not $__bartPrefix -or -not (Test-Path (Join-Path $__bartPrefix 'python.exe'))) {
    [Console]::Error.WriteLine('barthelona env not found. Create it with .\scripts\create_env.ps1')
    exit 3
}

$__envFile = Join-Path (Split-Path -Parent $PSScriptRoot) '.env'
if ($__loadEnv -and -not (Test-Path -LiteralPath $__envFile)) {
    [Console]::Error.WriteLine('-LoadEnv: no .env file in the repository root')
    exit 4
}

$__oldPath = $env:PATH
$__oldUtf8 = $env:PYTHONUTF8
$__oldWsl = $env:WSL_UTF8
$__oldPyPath = $env:PYTHONPATH
$__repoSrc = Join-Path (Split-Path -Parent $PSScriptRoot) 'src'
$__code = 1
$__loaded = @()
try {
    if ($__loadEnv) {
        # Values stay in variables of this script; nothing below prints them.
        foreach ($__line in [System.IO.File]::ReadAllLines($__envFile)) {
            if ($__line -notmatch '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }
            $__name = $Matches[1]
            $__value = $Matches[2].Trim()
            if ($__value.Length -ge 2 -and (($__value.StartsWith('"') -and $__value.EndsWith('"')) -or ($__value.StartsWith("'") -and $__value.EndsWith("'")))) {
                $__value = $__value.Substring(1, $__value.Length - 2)
            }
            if ($__value -and $null -eq [Environment]::GetEnvironmentVariable($__name)) {
                [Environment]::SetEnvironmentVariable($__name, $__value, 'Process')
                $__loaded += $__name
            }
        }
    }
    $env:PATH = (@($__bartPrefix, (Join-Path $__bartPrefix 'Scripts'), (Join-Path $__bartPrefix 'Library\bin')) -join ';') + ';' + $__oldPath
    $env:PYTHONUTF8 = '1'
    $env:WSL_UTF8 = '1'
    # The env holds one editable install that points at one checkout (#268); this checkout's src wins instead.
    if ($__oldPyPath) { $env:PYTHONPATH = $__repoSrc + ';' + $__oldPyPath } else { $env:PYTHONPATH = $__repoSrc }
    $__exe = $__argv[0]
    $__rest = @()
    if ($__argv.Count -gt 1) { $__rest = $__argv[1..($__argv.Count - 1)] }
    & $__exe @__rest
    $__code = $LASTEXITCODE
    if ($null -eq $__code) { if ($?) { $__code = 0 } else { $__code = 1 } }
}
finally {
    foreach ($__name in $__loaded) { Remove-Item -LiteralPath ('Env:' + $__name) -ErrorAction SilentlyContinue }
    $env:PATH = $__oldPath
    $env:PYTHONUTF8 = $__oldUtf8
    $env:WSL_UTF8 = $__oldWsl
    $env:PYTHONPATH = $__oldPyPath
}
exit $__code
