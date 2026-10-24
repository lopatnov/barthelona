<#
.SYNOPSIS
    Launches the barthelona worker and Streamlit UI.

.DESCRIPTION
    Starts the worker process (which claims queued runs and drives the engine graph)
    and the Streamlit UI (New Request, Approvals, Live Run pages) in parallel.
    Both processes share the same SQLite database (var/app.sqlite) for coordination.

.EXAMPLE
    .\scripts\run.ps1
    .\scripts\run.ps1 -WorkerOnly
    .\scripts\run.ps1 -UiOnly
    .\scripts\run.ps1 -StreamlitPort 8502

.NOTES
    Requires the conda environment 'barthelona' to be created (scripts/create_env.ps1).
    The worker and Streamlit communicate via SQLite (invariant 8: engine never imports Streamlit).
#>

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

param(
    [string]$DbPath = "var/app.sqlite",
    [string]$CheckpointsPath = "var/checkpoints.sqlite",
    [string]$RunsPath = "var/runs",
    [string]$CatalogPath = "config/models.yaml",
    [string]$FactsSql = "",
    [float]$PollInterval = 1.0,
    [switch]$WorkerOnly,
    [switch]$UiOnly,
    [int]$StreamlitPort = 8501
)

# Guard inactive process IDs before strict mode can complain
$workerProcess = $null
$uiProcess = $null

# Ensure we run from the repo root
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# Activate the conda environment for this command only
$envScript = ".\scripts\dev.ps1"
if (-not (Test-Path $envScript)) {
    Write-Error "Environment script not found: $envScript"
    exit 1
}

function Invoke-Worker {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param(
        [string]$Db,
        [string]$Checkpoints,
        [string]$Runs,
        [string]$Catalog,
        [string]$Facts,
        [float]$Poll,
        [switch]$Once
    )

    $cmdArgs = @(
        "python", "-m", "barthelona", "worker",
        "--db", $Db,
        "--checkpoints", $Checkpoints,
        "--runs", $Runs,
        "--catalog", $Catalog,
        "--poll", $Poll
    )
    if ($Facts) { $cmdArgs += "--facts-sql", $Facts }
    if ($Once) { $cmdArgs += "--once" }

    if ($PSCmdlet.ShouldProcess("worker process", "Start worker")) {
        Write-Host "Starting worker: $($cmdArgs -join ' ')" -ForegroundColor Cyan
        $scriptBlock = [scriptblock]::Create("& `"$envScript`" " + ($cmdArgs | ForEach-Object { [System.Management.Automation.CodeGenerator]::EncodeScriptBlockParameter($_) }) -join " ")
        return Start-Process powershell -ArgumentList "-Command", $scriptBlock -PassThru
    }
}

function Invoke-Ui {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param(
        [int]$Port
    )

    $cmdArgs = @(
        "streamlit", "run", "src/barthelona/ui/app.py",
        "--server.port", $Port,
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false"
    )

    if ($PSCmdlet.ShouldProcess("Streamlit UI process", "Start Streamlit UI")) {
        Write-Host "Starting Streamlit UI: $($cmdArgs -join ' ')" -ForegroundColor Green
        $scriptBlock = [scriptblock]::Create("& `"$envScript`" " + ($cmdArgs | ForEach-Object { [System.Management.Automation.CodeGenerator]::EncodeScriptBlockParameter($_) }) -join " ")
        return Start-Process powershell -ArgumentList "-Command", $scriptBlock -PassThru
    }
}

# Create required directories
$null = New-Item -ItemType Directory -Force -Path "var", "var/runs", "workspaces"

try {
    if (-not $UiOnly) {
        $workerProcess = Invoke-Worker -Db $DbPath -Checkpoints $CheckpointsPath -Runs $RunsPath -Catalog $CatalogPath -Facts $FactsSql -Poll $PollInterval
        Start-Sleep -Seconds 2  # Give worker time to start
    }

    if (-not $WorkerOnly) {
        $uiProcess = Invoke-Ui -Port $StreamlitPort
    }

    Write-Host ""
    Write-Host "barthelona is running." -ForegroundColor Yellow
    Write-Host "  Worker:  $($workerProcess.Id)" -ForegroundColor Cyan
    Write-Host "  Streamlit: $($uiProcess.Id) on http://127.0.0.1:$StreamlitPort" -ForegroundColor Green
    Write-Host ""
    Write-Host "Press Ctrl+C to stop both processes." -ForegroundColor Yellow

    # Wait for both processes, detect which exits first
    $processes = @()
    if ($workerProcess) { $processes += $workerProcess }
    if ($uiProcess) { $processes += $uiProcess }

    if ($processes.Count -gt 0) {
        $exited = Wait-Process -Id $processes.Id -ErrorAction SilentlyContinue -PassThru
        # Stop the remaining process
        foreach ($p in $processes) {
            if (-not $p.HasExited) {
                Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
            }
        }
        if ($exited.ExitCode -ne 0) {
            exit $exited.ExitCode
        }
    }
}
catch {
    Write-Error "Error: $_"
    exit 1
}
finally {
    Write-Host "Stopping processes..." -ForegroundColor Yellow
    if ($workerProcess -and -not $workerProcess.HasExited) { Stop-Process -Id $workerProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($uiProcess -and -not $uiProcess.HasExited) { Stop-Process -Id $uiProcess.Id -Force -ErrorAction SilentlyContinue }
    Write-Host "Stopped." -ForegroundColor Yellow
}