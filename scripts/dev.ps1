<#
.SYNOPSIS
    Run one command with the barthelona conda env on PATH, without activating it and without loading .env.

.DESCRIPTION
    Agent tool shells (Claude Code, Codex) start fresh for every call, so an activated env does not carry
    over. This wrapper prepends the env's directories to PATH for this one command, sets PYTHONUTF8 and
    WSL_UTF8, runs the command, restores PATH and returns its exit code. API keys from .env are NOT loaded
    (use activate.ps1 in your own terminal when you need them).
    Works in Windows PowerShell 5.1 and PowerShell 7. Env lookup: active barthelona env, then
    $env:BARTHELONA_ENV_PREFIX, then the usual miniconda/anaconda locations, then `conda env list --json`.

.EXAMPLE
    .\scripts\dev.ps1 ruff check .
    .\scripts\dev.ps1 python -m pytest -q
    .\scripts\dev.ps1 python scripts/sync_agent_configs.py --check
#>
if ($args.Count -eq 0) {
    Write-Output 'usage: .\scripts\dev.ps1 <command> [args...]   e.g. .\scripts\dev.ps1 ruff check .'
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
        } catch {
            # Fall through to the "env not found" message below, but say why the lookup failed.
            [Console]::Error.WriteLine("conda env list failed: $($_.Exception.Message)")
        }
    }
}
if (-not $__bartPrefix -or -not (Test-Path (Join-Path $__bartPrefix 'python.exe'))) {
    [Console]::Error.WriteLine('barthelona env not found. Create it with .\scripts\create_env.ps1')
    exit 3
}

$__oldPath = $env:PATH
$__oldUtf8 = $env:PYTHONUTF8
$__oldWsl = $env:WSL_UTF8
$__code = 1
try {
    $env:PATH = (@($__bartPrefix, (Join-Path $__bartPrefix 'Scripts'), (Join-Path $__bartPrefix 'Library\bin')) -join ';') + ';' + $__oldPath
    $env:PYTHONUTF8 = '1'
    $env:WSL_UTF8 = '1'
    $__exe = $args[0]
    $__rest = @()
    if ($args.Count -gt 1) { $__rest = $args[1..($args.Count - 1)] }
    & $__exe @__rest
    $__code = $LASTEXITCODE
    if ($null -eq $__code) { if ($?) { $__code = 0 } else { $__code = 1 } }
} finally {
    $env:PATH = $__oldPath
    $env:PYTHONUTF8 = $__oldUtf8
    $env:WSL_UTF8 = $__oldWsl
}
exit $__code
