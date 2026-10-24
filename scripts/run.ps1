<#>
.SYNOPSIS
    Launches the barthelona worker and Streamlit UI.

.DESCRIPTION
    Starts the worker process (which claims queued runs and drives the engine graph)
    and the Streamlit UI (New Request, Approvals, Live Run pages) in parallel.
    Both processes share the same SQLite database (var/app.sqlite) for coordination.

.EXAMPLE
    .\scripts\run.ps1

.NOTES
    Requires the conda environment 'barthelona' to be created (scripts/create_env.ps1).
    The worker and Streamlit communicate via SQLite (invariant 8: engine never imports Streamlit).
#>

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

    Write-Host "Starting worker: $($cmdArgs -join ' ')" -ForegroundColor Cyan
    return Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:PYTHONPATH='src'; $($cmdArgs -join ' ')" -PassThru
}

function Invoke-Ui {
    param(
        [int]$Port
    )

    $cmdArgs = @(
        "streamlit", "run", "src/barthelona/ui/app.py",
        "--server.port", $Port,
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false"
    )

    Write-Host "Starting Streamlit UI: $($cmdArgs -join ' ')" -ForegroundColor Green
    return Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:PYTHONPATH='src'; $($cmdArgs -join ' ')" -PassThru
}

# Create required directories
$null = New-Item -ItemType Directory -Force -Path "var", "var/runs", "workspaces"

$workerProcess = $null
$uiProcess = $null

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

    # Wait for both processes
    $processes = @()
    if ($workerProcess) { $processes += $workerProcess }
    if ($uiProcess) { $processes += $uiProcess }

    Wait-Process -Id $processes.Id -ErrorAction SilentlyContinue
}
catch {
    Write-Error "Error: $_"
}
finally {
    Write-Host "Stopping processes..." -ForegroundColor Yellow
    if ($workerProcess -and -not $workerProcess.HasExited) { Stop-Process -Id $workerProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($uiProcess -and -not $uiProcess.HasExited) { Stop-Process -Id $uiProcess.Id -Force -ErrorAction SilentlyContinue }
    Write-Host "Stopped." -ForegroundColor Yellow
}