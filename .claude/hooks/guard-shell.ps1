# PreToolUse hook for Bash and PowerShell tool calls (defense in depth; permission rules match text only).
# Analyzes the command per segment (split on ; && || | newlines, respecting quotes), by the actual command
# word, recursing into bash -c / wsl -e / pwsh -Command / $(...). Quoted search patterns, commit messages,
# heredoc and here-string bodies are therefore not mistaken for commands. Absolute paths into the repo are
# normalized to '.' first. Exit 2 = block (stderr is shown to Claude). Windows PowerShell 5.1 compatible.
$ErrorActionPreference = 'Stop'
try {
    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    $payload = [Console]::In.ReadToEnd() | ConvertFrom-Json
} catch {
    exit 0   # unreadable input: do not block
}
$cmd = ''
if ($payload.tool_input -and $payload.tool_input.command) { $cmd = [string]$payload.tool_input.command }
if (-not $cmd) { exit 0 }
$root = $env:CLAUDE_PROJECT_DIR
if (-not $root -and $payload.cwd) { $root = [string]$payload.cwd }

function Block([string]$why) {
    [Console]::Error.WriteLine("Blocked by .claude/hooks/guard-shell.ps1: $why")
    exit 2
}

function Unquote([string]$t) {
    if ($t.Length -ge 2 -and (($t[0] -eq '"' -and $t[-1] -eq '"') -or ($t[0] -eq "'" -and $t[-1] -eq "'"))) {
        return $t.Substring(1, $t.Length - 2)
    }
    return $t
}

function Get-Tokens([string]$s) {
    $list = New-Object System.Collections.Generic.List[string]
    foreach ($m in [regex]::Matches($s, '"(?:[^"\\]|\\.)*"|''[^'']*''|\S+')) { $list.Add($m.Value) }
    return , $list
}

function Split-Segments([string]$s) {
    $segs = New-Object System.Collections.Generic.List[string]
    $sb = New-Object System.Text.StringBuilder
    $q = [char]0
    for ($i = 0; $i -lt $s.Length; $i++) {
        $ch = $s[$i]
        if ($q -ne [char]0) {
            if ($ch -eq $q) { $q = [char]0 }
            [void]$sb.Append($ch)
            continue
        }
        if ($ch -eq '"' -or $ch -eq "'") { $q = $ch; [void]$sb.Append($ch); continue }
        if ($ch -eq ';' -or $ch -eq '|' -or $ch -eq '&' -or $ch -eq "`n" -or $ch -eq "`r") {
            $segs.Add($sb.ToString()); [void]$sb.Clear(); continue
        }
        [void]$sb.Append($ch)
    }
    $segs.Add($sb.ToString())
    return , $segs
}

$envFile = '^\.env(\.(?!example$)[\w.-]+)?$'
$protectedDirs = @('.', '*', '~', '/', '.git', '.claude', '.agents', '.codex', 'asm_doc', '.reference', 'docs',
                   'src', 'policies', 'knowledge', 'config', 'scripts', 'tests', 'requirements', '$home', '~/')

function Test-EnvToken([string]$tok) {
    $v = (Unquote $tok) -replace '\\', '/'
    $leaf = ($v -split '/')[-1]
    return ($leaf -match $envFile)
}

function Test-Git($rest) {
    $j = 0
    while ($j -lt $rest.Count) {
        $o = $rest[$j]
        if ($o -ceq '-C' -or $o -ceq '-c') { $j += 2; continue }
        if ($o -like '-*') { $j++; continue }
        break
    }
    if ($j -ge $rest.Count) { return }
    $sub = (Unquote $rest[$j]).ToLowerInvariant()
    $argv = @()
    if ($j + 1 -lt $rest.Count) { $argv = @($rest[($j + 1)..($rest.Count - 1)] | ForEach-Object { Unquote $_ }) }
    if ($sub -in @('diff', 'log', 'show', 'format-patch') -and @($argv | Where-Object { $_ -match '^(--output|-o$)' }).Count -gt 0) {
        Block "git $sub --output writes files; redirect output in a separate, visible step instead."
    }
    switch ($sub) {
        'push' {
            if (@($argv | Where-Object { $_ -match '^(--force|--force-with-lease|--force-if-includes|--mirror|--delete|--prune)(=.*)?$' -or $_ -cmatch '^-[a-zA-Z]*[fd][a-zA-Z]*$' -or $_ -match '^\+' -or $_ -match '^:' }).Count -gt 0) {
                Block 'Force-push, --mirror and deleting remote branches are never allowed from an agent.'
            }
            $script:AskReason = 'git push publishes commits to the remote. Confirm the branch and remote before approving (AGENTS.md: push only when the owner asks).'
        }
        'reset' { if ($argv -contains '--hard') { Block 'git reset --hard discards work. Ask the owner first.' } }
        'clean' { if (@($argv | Where-Object { $_ -cmatch '^-[a-zA-Z]*f' -or $_ -eq '--force' }).Count -gt 0) { Block 'git clean -f deletes untracked files (e.g. .reference/, var/). Ask the owner first.' } }
        'checkout' { if ($argv -contains '.') { Block 'Discarding all working-tree changes is not allowed. Restore specific files instead.' } }
        'restore' { if ($argv -contains '.') { Block 'Discarding all working-tree changes is not allowed. Restore specific files instead.' } }
    }
}

function Test-Remove([string]$name, $rest) {
    $recursive = $false
    foreach ($t in $rest) {
        $u = Unquote $t
        if ($u -match '^--recursive$' -or $u -match '^-rec' -or ($u -cmatch '^-[a-zA-Z]{1,3}$' -and $u -cmatch '[rR]') -or $u -match '^/s$') { $recursive = $true }
    }
    if (-not $recursive) { return }
    foreach ($t in $rest) {
        $u = Unquote $t
        if ($u -match '^-' -or $u -match '^/[sq]$') { continue }
        $v = ($u -replace '\\', '/').ToLowerInvariant()
        if ($v -match '^[a-z]:/?$' -or $v -eq '/c' -or $v -eq '/mnt/c') { Block 'Recursive delete of a drive root is not allowed.' }
        if ($v -eq '..' -or $v.StartsWith('../')) { Block "Recursive delete outside the repo ('$u') is not allowed." }
        $abs = $v
        if ($abs -match '^/mnt/([a-z])/(.*)$') { $abs = "$($Matches[1]):/$($Matches[2])" }
        elseif ($abs -match '^/([a-z])/(.*)$') { $abs = "$($Matches[1]):/$($Matches[2])" }
        if ($root -and $abs -match '^[a-z]:/') {
            $rootN = ($root -replace '\\', '/').ToLowerInvariant().TrimEnd('/')
            if ($rootN.StartsWith($abs.TrimEnd('/') + '/')) { Block "Recursive delete of an ancestor of the repo ('$u') is not allowed." }
        }
        while ($v.EndsWith('/*') -or ($v.Length -gt 1 -and $v.EndsWith('/'))) { $v = $v.Substring(0, $v.Length - $(if ($v.EndsWith('/*')) { 2 } else { 1 })) }
        while ($v.StartsWith('./') -and $v.Length -gt 2) { $v = $v.Substring(2) }
        if ($v -eq './') { $v = '.' }
        if ($protectedDirs -contains $v) { Block "Recursive delete of a protected path ('$u') is not allowed." }
    }
}

function Test-Pip($argv) {
    if ($argv.Count -eq 0) { return }
    $sub = (Unquote $argv[0]).ToLowerInvariant()
    if ($sub -ne 'install') { return }
    $a = @($argv | Select-Object -Skip 1 | ForEach-Object { Unquote $_ })
    if (@($a | Where-Object { $_ -match '\.reference' }).Count -gt 0) { Block 'Installing from .reference/ is not allowed: it is untrusted study material.' }
    $editable = $false
    for ($k = 0; $k -lt $a.Count - 1; $k++) { if ($a[$k] -eq '-e' -and $a[$k + 1] -eq '.') { $editable = $true } }
    $positional = @($a | Where-Object { $_ -notmatch '^-' })
    if ($editable -and ($a -contains '--no-deps') -and $positional.Count -eq 1) { return }
    $lock = $false
    for ($k = 0; $k -lt $a.Count - 1; $k++) { if ($a[$k] -eq '-r' -and $a[$k + 1] -match '^(\.[\\/])?requirements[\\/][\w.-]+\.lock$') { $lock = $true } }
    if ($lock -and ($a -contains '--require-hashes')) { return }
    Block 'Ad-hoc pip install is not allowed. Edit pyproject.toml, run scripts/lock.ps1, then scripts/create_env.ps1.'
}

function Test-Docker($rest) {
    $j = 0
    while ($j -lt $rest.Count -and $rest[$j] -like '-*') { if ($rest[$j] -in @('--context', '-H', '--host', '--log-level', '--config')) { $j += 2 } else { $j++ } }
    if ($j -ge $rest.Count) { return }
    $sub = (Unquote $rest[$j]).ToLowerInvariant()
    $sub2 = ''
    if ($j + 1 -lt $rest.Count) { $sub2 = (Unquote $rest[$j + 1]).ToLowerInvariant() }
    $joined = ' ' + ((@($rest) | ForEach-Object { Unquote $_ }) -join ' ').ToLowerInvariant() + ' '
    if ($joined -match 'docker\.sock') { Block 'Mounting the docker socket is forbidden (sandbox policy, D-010).' }
    if ($sub -in @('system', 'volume', 'image', 'container', 'builder', 'network') -and $sub2 -eq 'prune') { Block 'docker prune can delete the owner''s other containers and volumes (Qdrant, databases).' }
    if ($sub -eq 'volume' -and $sub2 -in @('rm', 'remove')) { Block 'Removing docker volumes can destroy the owner''s data.' }
    if ($sub -eq 'compose' -and $joined -match ' down ' -and $joined -match ' (-v|--volumes)[ =]') { Block 'docker compose down -v deletes volumes.' }
    $rmLike = ($sub -in @('rm', 'stop', 'kill', 'rename')) -or ($sub -eq 'container' -and $sub2 -in @('rm', 'stop', 'kill', 'rename'))
    if ($rmLike -and ($joined -match 'qdrant|mongo|mssql|pressmark|minikube|mcp-server' -or $joined -match '\$\(docker|`docker')) { Block 'Those containers belong to the owner''s other projects.' }
}

function Test-Segment([string]$seg, [int]$depth) {
    $t = Get-Tokens $seg
    $i = 0
    while ($i -lt $t.Count) {
        $w = (Unquote $t[$i]).ToLowerInvariant().TrimStart('(', '{')
        if ($w -eq '' -or $w -in @('&', '.', 'sudo', 'env', 'command', 'exec', 'time', 'nohup', 'builtin', 'call', '{', '(')) { $i++; continue }
        if ($w -match '^[a-z_][a-z0-9_]*=') { $i++; continue }
        break
    }
    if ($i -ge $t.Count) { return }
    $raw = (Unquote $t[$i]).TrimStart('(', '{')
    $name = ([System.IO.Path]::GetFileName(($raw -replace '/', '\'))).ToLowerInvariant() -replace '\.(exe|cmd|bat)$', ''
    $rest = New-Object System.Collections.Generic.List[string]
    for ($k = $i + 1; $k -lt $t.Count; $k++) { $rest.Add($t[$k]) }
    $restU = @($rest | ForEach-Object { Unquote $_ })

    # Sourcing or executing .env, or activating the env (loads API keys into the agent shell).
    if ($name -match $envFile) { Block 'Sourcing or executing .env is not allowed: it holds the owner''s API keys.' }
    if ($name -match '^activate\.(ps1|sh)$') { Block 'Agents must not activate the env (activate.* loads API keys). Run tools via scripts/dev.ps1 or scripts/dev.sh.' }

    switch -Regex ($name) {
        '^source$' {
            foreach ($tok in $rest) {
                if (Test-EnvToken $tok) { Block 'Sourcing .env is not allowed: it holds the owner''s API keys.' }
                if ((Unquote $tok) -match 'activate\.(ps1|sh)$') { Block 'Agents must not activate the env (activate.* loads API keys). Run tools via scripts/dev.ps1 or scripts/dev.sh.' }
            }
            return
        }
        '^wsl$' {
            if ($restU -contains '--unregister') { Block 'Unregistering a WSL distro destroys it.' }
            $idx = -1
            for ($k = 0; $k -lt $restU.Count; $k++) { if ($restU[$k] -in @('-e', '--exec', '--')) { $idx = $k; break } }
            if ($idx -lt 0) {
                $k = 0
                while ($k -lt $restU.Count -and $restU[$k] -like '-*') { if ($restU[$k] -in @('-d', '--distribution', '-u', '--user', '--cd', '--shell-type')) { $k += 2 } else { $k++ } }
                $idx = $k - 1
            }
            if ($idx + 1 -lt $rest.Count) { Test-Command (($rest | Select-Object -Skip ($idx + 1)) -join ' ') ($depth + 1) }
            return
        }
        '^(bash|sh|zsh|dash)$' {
            for ($k = 0; $k -lt $restU.Count; $k++) {
                if ($restU[$k] -cmatch '^-[a-z]*c$' -and $k + 1 -lt $restU.Count) { Test-Command $restU[$k + 1] ($depth + 1); return }
            }
            if (@($restU | Where-Object { $_ -match '\.reference' }).Count -gt 0) { Block 'Executing code from .reference/ is not allowed: it is untrusted study material.' }
            return
        }
        '^(pwsh|powershell)$' {
            for ($k = 0; $k -lt $restU.Count; $k++) {
                if ($restU[$k] -match '^-(c|command)$' -and $k + 1 -lt $restU.Count) { Test-Command (($restU | Select-Object -Skip ($k + 1)) -join ' ') ($depth + 1); return }
                if ($restU[$k] -match '^-(f|file)$' -and $k + 1 -lt $restU.Count -and $restU[$k + 1] -match '\.reference') { Block 'Executing code from .reference/ is not allowed.' }
            }
            return
        }
        '^cmd$' {
            for ($k = 0; $k -lt $restU.Count; $k++) { if ($restU[$k] -match '^/[ck]$') { Test-Command (($restU | Select-Object -Skip ($k + 1)) -join ' ') ($depth + 1); return } }
            return
        }
        '^dev\.(ps1|sh)$' {
            # scripts/dev.ps1 / dev.sh run the rest as a command: analyze it.
            Test-Command ($rest -join ' ') ($depth + 1); return
        }
        '^git$' { Test-Git $rest; return }
        '^(rm|del|erase|rmdir|rd|remove-item|ri)$' { Test-Remove $name $rest; return }
        '^conda$' {
            $sub = @($restU | Where-Object { $_ -notlike '-*' })[0]
            if ($sub -in @('install', 'update', 'upgrade')) { Block 'Packages are not installed with conda. Edit pyproject.toml, run scripts/lock.ps1, then scripts/create_env.ps1.' }
            if ($sub -eq 'run') {
                $k = [array]::IndexOf($restU, 'run') + 1
                while ($k -lt $restU.Count -and $restU[$k] -like '-*') { if ($restU[$k] -in @('-n', '--name', '-p', '--prefix', '--cwd')) { $k += 2 } else { $k++ } }
                if ($k -lt $rest.Count) { Test-Command (($rest | Select-Object -Skip $k) -join ' ') ($depth + 1) }
            }
            return
        }
        '^pip3?$' { Test-Pip $rest; return }
        '^uv$' {
            if ($restU.Count -ge 2 -and $restU[0] -eq 'pip' -and $restU[1] -eq 'install') { Block 'Ad-hoc uv pip install is not allowed. Use scripts/lock.ps1 and scripts/create_env.ps1.' }
            return
        }
        '^(python3?|py)$' {
            if (@($restU | Where-Object { $_ -match '\.reference' }).Count -gt 0) { Block 'Running code from .reference/ is not allowed: it is untrusted study material.' }
            for ($k = 0; $k -lt $restU.Count - 1; $k++) {
                if ($restU[$k] -eq '-m' -and $restU[$k + 1] -eq 'pip') { Test-Pip @($restU | Select-Object -Skip ($k + 2)); return }
                if ($restU[$k] -eq '-m' -and $restU[$k + 1] -eq 'uv' -and $k + 3 -lt $restU.Count -and $restU[$k + 2] -eq 'pip' -and $restU[$k + 3] -eq 'install') { Block 'Ad-hoc uv pip install is not allowed.' }
            }
            return
        }
        '^(pytest|py\.test|node|npm|npx|make|cargo|go)$' {
            if (@($restU | Where-Object { $_ -match '\.reference' }).Count -gt 0) { Block 'Running code from .reference/ is not allowed: it is untrusted study material.' }
            return
        }
        '^set-executionpolicy$' { Block 'Changing the execution policy is the owner''s decision.' }
        '^docker$' { Test-Docker $rest; return }
        '^docker-compose$' {
            $j = ' ' + ($restU -join ' ').ToLowerInvariant() + ' '
            if ($j -match ' down ' -and $j -match ' (-v|--volumes)[ =]') { Block 'docker compose down -v deletes volumes.' }
            return
        }
        '^(cat|type|more|less|head|tail|gc|get-content|bat|nl|sed|awk|strings|xxd|od|cp|copy|copy-item|cpi|mv|move|move-item|mi|base64|certutil|tac)$' {
            foreach ($tok in $rest) { if (Test-EnvToken $tok) { Block 'Reading or copying .env is not allowed: it holds the owner''s API keys. Use .env.example for the variable names.' } }
            return
        }
        '^(grep|egrep|fgrep|rg|ag|sls|select-string|findstr)$' {
            # Only an UNQUOTED operand naming the file counts; a quoted ".env" is a search pattern.
            foreach ($tok in $rest) {
                if ($tok.StartsWith('"') -or $tok.StartsWith("'")) { continue }
                if (Test-EnvToken $tok) { Block 'Reading .env is not allowed: it holds the owner''s API keys.' }
            }
            return
        }
    }
}

function Test-Command([string]$text, [int]$depth) {
    if ($depth -gt 4 -or -not $text) { return }
    foreach ($m in [regex]::Matches($text, '\$\(([^()]*)\)')) { Test-Command $m.Groups[1].Value ($depth + 1) }
    foreach ($seg in (Split-Segments $text)) { Test-Segment $seg $depth }
}

# 1. Pipelines into a shell / Invoke-Expression (segments would split them apart).
if ($cmd -match '\b(curl|wget)\b[^;&|\n]*\|\s*(sudo\s+)?(ba|z|da)?sh\b') { Block 'Piping downloaded scripts into a shell is not allowed.' }
if ($cmd -match '\b(iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b[^;&\n]*\|\s*(iex|Invoke-Expression)\b') { Block 'Piping downloaded scripts into Invoke-Expression is not allowed.' }

# 2. Drop heredoc and here-string bodies (data, not commands).
$work = [regex]::Replace($cmd, '(?ms)<<-?\s*([''"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$', '<<HEREDOC')
$work = [regex]::Replace($work, '(?ms)@([''"])\r?\n.*?^\1@', '@HERESTRING@')

# 3. Normalize absolute paths into the repo to '.'.
if ($root) {
    $r = ($root -replace '\\', '/').TrimEnd('/')
    $variants = New-Object System.Collections.Generic.List[string]
    $variants.Add($r)
    $variants.Add(($r -replace '/', '\'))
    if ($r -match '^([A-Za-z]):/(.*)$') {
        $variants.Add('/' + $Matches[1].ToLower() + '/' + $Matches[2])
        $variants.Add('/mnt/' + $Matches[1].ToLower() + '/' + $Matches[2])
    }
    foreach ($v in $variants) {
        $work = [regex]::Replace($work, [regex]::Escape($v) + '(?=[\\/\s''"]|$)', '.', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    }
}

# 4. Analyze. Blocks exit immediately; an "ask" is reported only if nothing in the command was blocked.
$script:AskReason = $null
Test-Command $work 0
if ($script:AskReason) {
    $out = @{ hookSpecificOutput = @{ hookEventName = 'PreToolUse'; permissionDecision = 'ask'; permissionDecisionReason = $script:AskReason } }
    [Console]::Out.Write(($out | ConvertTo-Json -Compress -Depth 4))
}
exit 0
