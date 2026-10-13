# PreToolUse hook for Edit / Write / NotebookEdit. Blocks writes to protected paths.
# Exit 2 = block, stderr is shown to Claude as the reason. Compatible with Windows PowerShell 5.1.
$ErrorActionPreference = 'Stop'
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    $payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
} catch {
    exit 0
}

$ti = $payload.tool_input
$path = $null
if ($ti) {
    if ($ti.file_path) { $path = [string]$ti.file_path }
    elseif ($ti.notebook_path) { $path = [string]$ti.notebook_path }
}
if (-not $path) { exit 0 }

$root = $env:CLAUDE_PROJECT_DIR
if (-not $root) { $root = $payload.cwd }
if (-not $root) { exit 0 }

function ConvertTo-Norm([string]$p) {
    $p = $p -replace '\\', '/'
    if ($p -match '^/([a-zA-Z])/(.*)$') { $p = "$($Matches[1]):/$($Matches[2])" }   # /c/x -> c:/x (Git Bash form)
    return $p.ToLowerInvariant().TrimEnd('/')
}

$full = $path
if ($full -match '^/([a-zA-Z])/(.*)$') { $full = "$($Matches[1]):/$($Matches[2])" }
if (-not [System.IO.Path]::IsPathRooted($full)) { $full = Join-Path $root $full }
try { $full = [System.IO.Path]::GetFullPath($full) } catch { }   # resolves '..' segments
$nPath = ConvertTo-Norm $full
$nRoot = ConvertTo-Norm $root
if (-not $nPath.StartsWith($nRoot + '/')) { exit 0 }   # outside the repo: not this hook's business
$rel = $nPath.Substring($nRoot.Length + 1)
# Claude Code worktrees live under .claude/worktrees/<name>/: protect the same paths inside them.
$rel = $rel -replace '^\.claude/worktrees/[^/]+/', ''

function Block([string]$why) {
    [Console]::Error.WriteLine("Blocked by .claude/hooks/guard-paths.ps1: $why ($rel)")
    exit 2
}

if ($rel -eq '.env' -or ($rel -match '(^|/)\.env(\.[^/]+)?$' -and $rel -notmatch '\.env\.example$')) { Block 'Secrets files are edited by the owner only.' }
if ($rel -match '^asm_doc/') { Block 'asm_doc/ is a read-only reference cache.' }
if ($rel -match '^\.agents/skills/' -or $rel -match '^\.codex/agents/') { Block 'Generated Codex mirror. Edit .claude/skills or .claude/agents; scripts/sync_agent_configs.py regenerates it.' }
if ($rel -match '^docs/archive/') { Block 'docs/archive/ is historical and read-only.' }
if ($rel -match '^var/') { Block 'var/ is runtime data written by the product.' }
if ($rel -match '^workspaces/') { Block 'workspaces/ holds generated projects; change them through the product, not by hand.' }
if ($rel -match '^requirements/.*\.(lock|sha256)$') { Block 'Lock files and the dependency fingerprint are generated. Edit pyproject.toml and run scripts/lock.ps1.' }
if ($rel -match '^policies/(v\d+)/') {
    $manifest = Join-Path $root ("policies/{0}/MANIFEST.json" -f $Matches[1])
    if (Test-Path -LiteralPath $manifest) {
        try {
            $m = Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
            if ($m.released -eq $true) { Block 'Released policy versions are immutable; create the next version instead.' }
        } catch { }
    }
}
exit 0
