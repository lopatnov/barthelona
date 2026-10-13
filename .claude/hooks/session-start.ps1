# SessionStart hook: prints a short environment status that is added to Claude's context.
# Read-only and fast: never boots the WSL VM, never starts services, never prints secrets.
# Compatible with Windows PowerShell 5.1.
$ErrorActionPreference = 'SilentlyContinue'
$root = $env:CLAUDE_PROJECT_DIR
if (-not $root) { $root = (Get-Location).Path }
$lines = @('barthelona dev environment status:')

# conda env
$envDir = Join-Path $env:USERPROFILE 'miniconda3\envs\barthelona'
if (Test-Path (Join-Path $envDir 'python.exe')) {
    $lines += "- conda env 'barthelona': present. Agent tool shells start WITHOUT it: run tools as .\scripts\dev.ps1 <cmd> (PowerShell) or scripts/dev.sh <cmd> (bash). Never dot-source activate.ps1 in an agent shell (it loads API keys)."
} else {
    $lines += "- conda env 'barthelona': MISSING. Create with: .\scripts\create_env.ps1"
}

# lock freshness (dependency fingerprint, see scripts/deps_fingerprint.py)
$envPy = Join-Path $envDir 'python.exe'
$fpScript = Join-Path $root 'scripts\deps_fingerprint.py'
if ((Test-Path $envPy) -and (Test-Path $fpScript)) {
    $null = & $envPy $fpScript --check 2>$null
    if ($LASTEXITCODE -ne 0) { $lines += '- requirements locks are STALE: pyproject.toml dependencies changed; run .\scripts\lock.ps1 then .\scripts\create_env.ps1.' }
}

# git
Push-Location $root
$changes = @(git status --porcelain 2>$null).Count
$branch = git rev-parse --abbrev-ref HEAD 2>$null
Pop-Location
$lines += "- git: branch $branch, $changes changed/untracked path(s)."

# Last devlog entry: newest docs/devlog/YYYY-Qn.md, first '## ' heading and its '- Next:' line.
$devDir = Join-Path $root 'docs\devlog'
$dev = Get-ChildItem -LiteralPath $devDir -Filter '*.md' -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1
if ($dev) {
    $head = $null; $next = '(none recorded)'
    foreach ($l in (Get-Content -LiteralPath $dev.FullName -Encoding UTF8 -TotalCount 60)) {
        if ($head -and $l -match '^## ') { break }
        if (-not $head -and $l -match '^## (.+)$') { $head = $Matches[1]; continue }
        if ($head -and $l -match '^- Next:\s*(.+)$') { $next = $Matches[1]; break }
    }
    if ($head) {
        $s = "- Last session ($($dev.Name)): $head. Next: $next"
        if ($s.Length -gt 300) { $s = $s.Substring(0, 297) + '...' }
        $lines += $s
    }
}

# WSL (does not boot the VM)
$env:WSL_UTF8 = '1'
$running = (wsl.exe -l --running -q 2>$null | Out-String)
if ($running -match 'Ubuntu') { $lines += '- WSL Ubuntu: running.' }
else { $lines += '- WSL Ubuntu: stopped (Qdrant :6333 and the Qdrant MCP :8000 are unreachable until it starts; this is expected).' }

# LM Studio
try {
    $r = Invoke-RestMethod -Uri 'http://127.0.0.1:1234/api/v1/models' -TimeoutSec 2
    $loaded = @()
    foreach ($m in $r.models) { if ($m.loaded_instances -and @($m.loaded_instances).Count -gt 0) { $loaded += $m.key } }
    if ($loaded.Count -gt 0) { $lines += ('- LM Studio: up; loaded: ' + ($loaded -join ', ')) }
    else { $lines += '- LM Studio: up; no model loaded.' }
} catch {
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:1234/v1/models' -TimeoutSec 2
        $lines += '- LM Studio: up.'
    } catch { $lines += '- LM Studio: not reachable on :1234.' }
}

$lines += '- Reminder: reply in English; the design is docs/architecture.md; check docs/roadmap.md for what exists.'
[Console]::Out.Write(($lines -join "`n"))
exit 0
