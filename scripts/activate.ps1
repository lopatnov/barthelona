<#
.SYNOPSIS
    Activate the 'barthelona' conda environment in the CURRENT PowerShell session (your own terminal).

.DESCRIPTION
    Must be dot-sourced:   . .\scripts\activate.ps1
    - Loads the conda PowerShell hook if 'conda init powershell' was never run.
    - Activates the environment.
    - Sets PYTHONUTF8, WSL_UTF8, BARTHELONA_HOME and default local endpoint variables.
    - Loads KEY=VALUE lines from <repo>\.env (API keys). Values are never printed.
    Coding agents should NOT use this (it would put API keys into the agent's shell): they run tools
    through .\scripts\dev.ps1 instead.
    Works in Windows PowerShell 5.1 and PowerShell 7. Changes nothing outside this session, and does not
    overwrite or leave behind variables in your session (internal names are prefixed with __bart).

.PARAMETER BarthelonaEnvName
    Environment name (alias: -Name). Default: barthelona.
#>
param([Alias('Name')][string]$BarthelonaEnvName = 'barthelona')

if ($MyInvocation.InvocationName -ne '.') {
    Write-Warning 'This script must be dot-sourced to affect your shell:  . .\scripts\activate.ps1'
    return
}

try {
    $__bartRoot = Split-Path -Parent $PSScriptRoot

    # 1. Conda hook (only if 'conda activate' is not already available as a shell function).
    if (-not (Get-Command conda -CommandType Function, Alias -ErrorAction SilentlyContinue)) {
        $__bartConda = $env:CONDA_EXE
        if (-not $__bartConda -or -not (Test-Path $__bartConda)) {
            $__bartApp = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($__bartApp) { $__bartConda = $__bartApp.Source }
        }
        if (-not $__bartConda) {
            foreach ($__bartC in @((Join-Path $env:USERPROFILE 'miniconda3\Scripts\conda.exe'),
                                   (Join-Path $env:USERPROFILE 'anaconda3\Scripts\conda.exe'))) {
                if (Test-Path $__bartC) { $__bartConda = $__bartC; break }
            }
        }
        if (-not $__bartConda) {
            Write-Error 'conda not found. Install Miniconda or add conda.exe to PATH.'
            return
        }
        (& $__bartConda 'shell.powershell' 'hook') | Out-String | Invoke-Expression
    }

    # 2. Activate.
    conda activate $BarthelonaEnvName
    if ($env:CONDA_DEFAULT_ENV -ne $BarthelonaEnvName) {
        Write-Error "Could not activate '$BarthelonaEnvName'. Create it first: .\scripts\create_env.ps1"
        return
    }

    # 3. Session variables.
    $env:PYTHONUTF8 = '1'
    $env:WSL_UTF8 = '1'
    $env:BARTHELONA_HOME = $__bartRoot
    if (-not $env:LMSTUDIO_BASE_URL) { $env:LMSTUDIO_BASE_URL = 'http://127.0.0.1:1234/v1' }
    if (-not $env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL = 'http://127.0.0.1:11434' }
    if (-not $env:QDRANT_URL) { $env:QDRANT_URL = 'http://127.0.0.1:6333' }

    # 4. .env: KEY=VALUE per line; '#' comment lines; optional 'export '; quoted values keep '#';
    #    unquoted values end at ' #' (inline comment). Never echo values.
    $__bartDotenv = Join-Path $__bartRoot '.env'
    $__bartLoaded = @()
    if (Test-Path $__bartDotenv) {
        foreach ($__bartLine in Get-Content -LiteralPath $__bartDotenv -Encoding UTF8) {
            $__bartT = $__bartLine.Trim().TrimStart([char]0xFEFF)
            if (-not $__bartT -or $__bartT.StartsWith('#')) { continue }
            if ($__bartT.StartsWith('export ')) { $__bartT = $__bartT.Substring(7).Trim() }
            $__bartEq = $__bartT.IndexOf('=')
            if ($__bartEq -lt 1) { continue }
            $__bartKey = $__bartT.Substring(0, $__bartEq).Trim()
            $__bartVal = $__bartT.Substring($__bartEq + 1).Trim()
            if ($__bartKey -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') { continue }
            if ($__bartVal.Length -ge 1 -and ($__bartVal[0] -eq '"' -or $__bartVal[0] -eq "'")) {
                $__bartEnd = $__bartVal.IndexOf($__bartVal[0], 1)
                if ($__bartEnd -gt 0) { $__bartVal = $__bartVal.Substring(1, $__bartEnd - 1) }
            } else {
                $__bartHash = $__bartVal.IndexOf(' #')
                if ($__bartHash -ge 0) { $__bartVal = $__bartVal.Substring(0, $__bartHash).TrimEnd() }
            }
            if ($__bartVal -eq '') { continue }
            Set-Item -Path "Env:$__bartKey" -Value $__bartVal
            $__bartLoaded += $__bartKey
        }
    }

    $__bartPy = python -c 'import sys; print(sys.version.split()[0])'
    Write-Host "barthelona env active: Python $__bartPy  (BARTHELONA_HOME=$__bartRoot)" -ForegroundColor Green
    if ($__bartLoaded.Count -gt 0) { Write-Host ('.env loaded: ' + ($__bartLoaded -join ', ')) }
} finally {
    Get-Variable -Name '__bart*' -Scope 0 -ErrorAction SilentlyContinue | Remove-Variable -ErrorAction SilentlyContinue
    Remove-Variable -Name BarthelonaEnvName -ErrorAction SilentlyContinue
}
