# PostToolUse hook for Edit / Write.
# - *.py: runs `ruff format` on the file (whitespace/layout only) and reports `ruff check` findings as
#   context. It does NOT auto-fix lint, so half-finished multi-step edits are never rewritten.
# - LF-only files (shell, assembly, Makefile, Dockerfile): converts CRLF to LF, because WSL tools break on CR.
# Never blocks. Compatible with Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    $payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
} catch {
    exit 0
}
$path = $null
if ($payload.tool_input -and $payload.tool_input.file_path) { $path = [string]$payload.tool_input.file_path }
if (-not $path) { exit 0 }
if ($path -match '^/([a-zA-Z])/(.*)$') { $path = "$($Matches[1]):/$($Matches[2])" }
if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { exit 0 }
# Only touch files inside this repo (never reformat files elsewhere on the machine).
$projRoot = $env:CLAUDE_PROJECT_DIR
if ($projRoot) {
    $pNorm = ([System.IO.Path]::GetFullPath($path) -replace '\\', '/').ToLowerInvariant()
    $rNorm = ($projRoot -replace '\\', '/').ToLowerInvariant().TrimEnd('/')
    if (-not $pNorm.StartsWith($rNorm + '/')) { exit 0 }
    $relPath = $pNorm.Substring($rNorm.Length + 1) -replace '^\.claude/worktrees/[^/]+/', ''
    # Third-party, reference and runtime data are never reformatted.
    if ($relPath -match '^(\.reference|asm_doc|workspaces|var|\.agents|\.codex)/') { exit 0 }
}

$notes = @()
$name = [System.IO.Path]::GetFileName($path)
$ext = [System.IO.Path]::GetExtension($path).ToLowerInvariant()

$lfExts = @('.sh', '.bash', '.asm', '.inc', '.s', '.nasm', '.fasm', '.mk', '.ld')
if ($lfExts -contains $ext -or $name -like 'Makefile*' -or $name -like 'Dockerfile*' -or $path -cmatch '\.S$') {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    $text = [System.Text.Encoding]::UTF8.GetString($bytes)
    if ($text.Contains("`r`n")) {
        $fixed = $text.Replace("`r`n", "`n")
        $enc = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($path, $fixed, $enc)
        $notes += "post-edit: converted CRLF to LF in $name (WSL tools require LF)."
    }
}

if ($ext -eq '.py') {
    $ruff = $null
    $candidates = @()
    if ($env:CONDA_PREFIX) { $candidates += (Join-Path $env:CONDA_PREFIX 'Scripts\ruff.exe') }
    $candidates += (Join-Path $env:USERPROFILE 'miniconda3\envs\barthelona\Scripts\ruff.exe')
    foreach ($c in $candidates) { if (Test-Path -LiteralPath $c) { $ruff = $c; break } }
    if (-not $ruff) {
        $cmd = Get-Command ruff.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { $ruff = $cmd.Source }
    }
    if ($ruff) {
        & $ruff format --quiet --force-exclude -- $path 2>$null | Out-Null
        $out = & $ruff check --output-format concise --no-fix --force-exclude -- $path 2>$null
        if ($LASTEXITCODE -ne 0 -and $out) {
            $lines = @($out | Where-Object { $_ -and $_ -notmatch '^Found \d+ error' } | Select-Object -First 15)
            if ($lines.Count -gt 0) { $notes += ("ruff check findings in ${name}:`n" + ($lines -join "`n")) }
        }
    }
}

# Edits to Claude skills/agents: regenerate the Codex mirror (.agents/skills, .codex/agents).
$root = $env:CLAUDE_PROJECT_DIR
if ($root) {
    $relNorm = ($path -replace '\\', '/').ToLowerInvariant()
    $rootNorm = ($root -replace '\\', '/').ToLowerInvariant().TrimEnd('/')
    if ($relNorm.StartsWith($rootNorm + '/.claude/skills/') -or $relNorm.StartsWith($rootNorm + '/.claude/agents/')) {
        $py = Join-Path $env:USERPROFILE 'miniconda3\envs\barthelona\python.exe'
        if ($env:CONDA_PREFIX -and (Test-Path (Join-Path $env:CONDA_PREFIX 'python.exe'))) { $py = Join-Path $env:CONDA_PREFIX 'python.exe' }
        $sync = Join-Path $root 'scripts\sync_agent_configs.py'
        if ((Test-Path $py) -and (Test-Path $sync)) {
            $ErrorActionPreference = 'Continue'   # PS 5.1 turns native stderr into terminating errors under 'Stop'
            $msg = (& $py $sync 2>&1 | Out-String).Trim()
            $syncCode = $LASTEXITCODE
            $ErrorActionPreference = 'Stop'
            if ($syncCode -eq 0) { $notes += ('post-edit: ' + $msg) }
            else { $notes += ('post-edit: Codex mirror sync FAILED (exit ' + $syncCode + '): ' + $msg) }
        } else {
            $notes += 'post-edit: Codex mirror NOT synced (no barthelona python); run python scripts/sync_agent_configs.py'
        }
    }
}

if ($notes.Count -gt 0) {
    $obj = @{ hookSpecificOutput = @{ hookEventName = 'PostToolUse'; additionalContext = ($notes -join "`n") } }
    [Console]::Out.Write(($obj | ConvertTo-Json -Compress -Depth 4))
}
exit 0
