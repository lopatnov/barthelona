<#
.SYNOPSIS
    Read-only health check of the barthelona development environment.

.DESCRIPTION
    Reports [ OK ] / [WARN] / [MISS] lines for: conda env and key imports, lock freshness, WSL and its
    tools, docker containers/images, LM Studio, Ollama, Qdrant, cloud API keys (names only, never values),
    .wslconfig and the Claude Code CLI version. Changes nothing; does not boot the WSL VM unless -StartWsl.
    Works in Windows PowerShell 5.1 and PowerShell 7.

.PARAMETER StartWsl
    Start the WSL VM if it is stopped, so WSL tools, docker and Qdrant can be checked.

.EXAMPLE
    .\scripts\doctor.ps1
    .\scripts\doctor.ps1 -StartWsl
#>
[CmdletBinding()]
param([switch]$StartWsl)

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Distro = 'Ubuntu'
$script:Warnings = 0

function Report([string]$level, [string]$what, [string]$detail) {
    $tag = @{ ok = '[ OK ]'; warn = '[WARN]'; miss = '[MISS]'; info = '[INFO]' }[$level]
    if ($level -eq 'warn' -or $level -eq 'miss') { $script:Warnings++ }
    Write-Output ('{0} {1,-22} {2}' -f $tag, $what, $detail)
}

function Test-Http([string]$url) {
    try { return Invoke-RestMethod -Uri $url -TimeoutSec 3 } catch { return $null }
}

# --- Python environment ---------------------------------------------------------------------------
# Same lookup order as scripts/dev.ps1: active env, BARTHELONA_ENV_PREFIX, usual locations, conda env list.
$envPrefix = $null
if ($env:CONDA_PREFIX -and (Split-Path -Leaf $env:CONDA_PREFIX) -eq 'barthelona') { $envPrefix = $env:CONDA_PREFIX }
if (-not $envPrefix -and $env:BARTHELONA_ENV_PREFIX) { $envPrefix = $env:BARTHELONA_ENV_PREFIX }
if (-not $envPrefix) {
    foreach ($c in @((Join-Path $env:USERPROFILE 'miniconda3\envs\barthelona'), (Join-Path $env:USERPROFILE 'anaconda3\envs\barthelona'), (Join-Path $env:ProgramData 'miniconda3\envs\barthelona'))) {
        if (Test-Path (Join-Path $c 'python.exe')) { $envPrefix = $c; break }
    }
}
if (-not $envPrefix) {
    $condaCmd = Get-Command conda.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($condaCmd) {
        try { $envPrefix = @((& $condaCmd.Source env list --json | Out-String | ConvertFrom-Json).envs | Where-Object { (Split-Path -Leaf $_) -eq 'barthelona' })[0] } catch { }
    }
}
$envPy = $null
if ($envPrefix) { $envPy = Join-Path $envPrefix 'python.exe' }
if ($envPy -and (Test-Path $envPy)) {
    $ver = & $envPy -c 'import sys; print(sys.version.split()[0])' 2>$null
    # No embedded double quotes: Windows PowerShell 5.1 mangles them when calling native programs.
    $imp = & $envPy -c 'import langgraph, streamlit, anthropic, openai, google.genai, unicorn, capstone, barthelona' 2>&1
    if ($LASTEXITCODE -eq 0) { Report ok 'conda env' "barthelona at $envPrefix, Python $ver, key imports ok" }
    else { Report warn 'conda env' ('imports failed: ' + ((@($imp) | Select-Object -Last 1) -join '') + '  -> .\scripts\create_env.ps1') }
    Report info 'agent shells' 'tool calls start without the env: run tools via .\scripts\dev.ps1 <cmd> (or scripts/dev.sh)'
} else {
    Report miss 'conda env' 'barthelona not found -> .\scripts\create_env.ps1'
}

$lock = Join-Path $RepoRoot 'requirements\dev.win.lock'
if (-not (Test-Path $lock)) {
    Report miss 'locks' 'requirements\dev.win.lock missing -> .\scripts\lock.ps1'
} elseif ($envPy -and (Test-Path $envPy)) {
    $null = & $envPy (Join-Path $RepoRoot 'scripts\deps_fingerprint.py') --check 2>$null
    if ($LASTEXITCODE -eq 0) { Report ok 'locks' 'match the dependencies in pyproject.toml' }
    else { Report warn 'locks' 'dependencies in pyproject.toml changed since the last lock -> .\scripts\lock.ps1' }
} else {
    Report info 'locks' 'present (fingerprint not checked: no barthelona python)'
}

# --- Cloud keys (names only) ----------------------------------------------------------------------
$keys = @('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY', 'DEEPSEEK_API_KEY')
$present = @($keys | Where-Object { [Environment]::GetEnvironmentVariable($_) })
$absent = @($keys | Where-Object { -not [Environment]::GetEnvironmentVariable($_) })
if ($present.Count -gt 0) { Report ok 'cloud keys' ('set: ' + ($present -join ', ')) }
if ($absent.Count -gt 0) {
    $hint = 'not set: ' + ($absent -join ', ')
    if (Test-Path (Join-Path $RepoRoot '.env')) { $hint += ' (a .env exists; activate to load it)' } else { $hint += ' (copy .env.example to .env)' }
    Report info 'cloud keys' $hint
}
if ($env:GOOGLE_API_KEY -and $env:GEMINI_API_KEY) { Report warn 'gemini key' 'GOOGLE_API_KEY and GEMINI_API_KEY both set; the SDK prefers GOOGLE_API_KEY' }
foreach ($v in @('LMSTUDIO_BASE_URL', 'OLLAMA_BASE_URL', 'QDRANT_URL')) {
    $val = [Environment]::GetEnvironmentVariable($v)
    if ($val -and $val -match 'localhost') { Report warn $v 'uses localhost; use 127.0.0.1 (localhost resolves to ::1 first and IPv4-only servers hang)' }
}

# --- Local model servers --------------------------------------------------------------------------
$lms = Test-Http 'http://127.0.0.1:1234/api/v1/models'
if ($lms) {
    $loaded = @($lms.models | Where-Object { $_.loaded_instances -and @($_.loaded_instances).Count -gt 0 } | ForEach-Object { $_.key })
    if ($loaded.Count -gt 0) { Report ok 'LM Studio' ('up; loaded: ' + ($loaded -join ', ')) }
    else { Report warn 'LM Studio' 'up, but no model loaded' }
} elseif (Test-Http 'http://127.0.0.1:1234/v1/models') {
    Report ok 'LM Studio' 'up (native /api/v1 not available)'
} else {
    Report warn 'LM Studio' 'not reachable on 127.0.0.1:1234 (start the server: lms server start)'
}
$oll = Test-Http 'http://127.0.0.1:11434/api/version'
if ($oll) { Report ok 'Ollama' "up, version $($oll.version)" } else { Report info 'Ollama' 'not running (optional)' }

# --- WSL ------------------------------------------------------------------------------------------
$env:WSL_UTF8 = '1'
$running = (wsl.exe -l --running -q 2>$null | Out-String)
if ($running -notmatch $Distro -and $StartWsl) {
    wsl.exe -d $Distro -e true 2>$null | Out-Null
    $running = (wsl.exe -l --running -q 2>$null | Out-String)
}
if ($running -match $Distro) {
    Report ok 'WSL' "$Distro running"
    # No embedded double quotes (Windows PowerShell 5.1 strips them for native programs).
    $tools = @(wsl.exe -d $Distro -e bash -lc 'for t in nasm yasm fasm as ld gcc make gdb docker qemu-x86_64; do if command -v $t >/dev/null 2>&1; then echo $t+; else echo $t-; fi; done' 2>$null)
    $probe = @($tools | Where-Object { $_ -match '^[\w.-]+[+-]$' })
    if ($LASTEXITCODE -ne 0 -or $probe.Count -eq 0) {
        Report warn 'WSL tools' 'probe failed'
    } else {
        $missing = @($probe | Where-Object { $_.EndsWith('-') } | ForEach-Object { $_.TrimEnd('-') })
        if ($missing.Count -eq 0) { Report ok 'WSL tools' 'all present' }
        else { Report info 'WSL tools' ('missing (optional for manual checks): ' + ($missing -join ', ')) }
    }
    $ps = wsl.exe -d $Distro -e bash -lc 'docker ps --format {{.Names}} 2>/dev/null' 2>$null
    if ($LASTEXITCODE -eq 0) {
        Report ok 'docker' ('running containers: ' + ((@($ps) | Where-Object { $_ }) -join ', '))
        $imgs = wsl.exe -d $Distro -e bash -lc 'docker images --format {{.Repository}}:{{.Tag}} 2>/dev/null' 2>$null
        foreach ($need in @('barthelona/toolchain', 'barthelona/runner')) {
            if (@($imgs) -match [regex]::Escape($need)) { Report ok 'image' $need } else { Report info 'image' "$need not built yet (Phase 0)" }
        }
    } else {
        Report warn 'docker' 'docker not responding inside WSL'
    }
    $q = Test-Http 'http://127.0.0.1:6343/'
    if ($q) { Report ok 'Qdrant' "barthelona-qdrant up, version $($q.version)" } else { Report info 'Qdrant' 'barthelona-qdrant not reachable on 127.0.0.1:6343 (needed from Phase 3; runbook section 3)' }
} else {
    Report info 'WSL' "$Distro stopped (run with -StartWsl to check tools, docker and Qdrant)"
}

$wslconfig = Join-Path $env:USERPROFILE '.wslconfig'
if (Test-Path $wslconfig) {
    $mem = (Select-String -Path $wslconfig -Pattern '^\s*memory\s*=\s*(\S+)' | Select-Object -First 1)
    if ($mem) { Report ok '.wslconfig' "memory=$($mem.Matches[0].Groups[1].Value)" } else { Report warn '.wslconfig' 'no memory cap (recommended: memory=8GB, see docs/runbook.md)' }
} else {
    Report warn '.wslconfig' 'missing; WSL may take ~15 GB RAM (recommended: memory=8GB, see docs/runbook.md)'
}

# --- Claude Code ------------------------------------------------------------------------------------
$cc = (claude --version 2>$null | Select-Object -First 1)
if ($cc) { Report info 'Claude Code CLI' "$cc (run 'claude update' for the latest)" }

Write-Output ''
if ($script:Warnings -eq 0) { Write-Output 'doctor: no problems found.' } else { Write-Output "doctor: $($script:Warnings) item(s) need attention." }
exit 0
