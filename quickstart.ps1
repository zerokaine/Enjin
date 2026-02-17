<#
.SYNOPSIS
    Enjin OSINT Platform - Quick-start for local testing (Windows)

.DESCRIPTION
    Spins up the full stack with a fast hot-reload frontend (no production build).
    Databases, API, and frontend are always started.
    The ingestion worker is opt-in via -WithIngestion.

.EXAMPLE
    .\quickstart.ps1                   # API + frontend + databases
    .\quickstart.ps1 -WithIngestion    # Also start the ingestion worker
    .\quickstart.ps1 -Down             # Stop and remove all containers
    .\quickstart.ps1 -Logs             # Follow logs after starting
#>

param(
    [switch]$WithIngestion,
    [switch]$Logs,
    [switch]$Down,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# ── Helpers ──────────────────────────────────────────────────────────────────

function Write-Info    { param($Msg) Write-Host "[info]  $Msg" -ForegroundColor Cyan }
function Write-Ok      { param($Msg) Write-Host "[ok]    $Msg" -ForegroundColor Green }
function Write-Warn    { param($Msg) Write-Host "[warn]  $Msg" -ForegroundColor Yellow }
function Write-Err     { param($Msg) Write-Host "[error] $Msg" -ForegroundColor Red }

function Stop-WithError {
    param($Msg)
    Write-Err $Msg
    exit 1
}

function Test-Endpoint {
    param([string]$Url, [int]$TimeoutSec = 120, [string]$Label = "Service")

    Write-Info "Waiting for $Label..."
    $elapsed = 0
    $interval = 5

    while ($elapsed -lt $TimeoutSec) {
        try {
            $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
            Write-Ok "$Label is ready"
            return $true
        } catch {
            Start-Sleep -Seconds $interval
            $elapsed += $interval
            Write-Host "  waiting... ${elapsed}s" -NoNewline
            Write-Host "`r" -NoNewline
        }
    }

    Write-Warn "$Label did not respond within ${TimeoutSec}s."
    return $false
}

# ── Help ─────────────────────────────────────────────────────────────────────

if ($Help) {
    Get-Help $PSCommandPath -Detailed
    exit 0
}

# ── Resolve script directory ──────────────────────────────────────────────────

$ScriptDir = Split-Path -Parent $PSCommandPath
Push-Location $ScriptDir

try {

# ── Compose file lists ────────────────────────────────────────────────────────

$BaseFiles = @("-f", "docker-compose.yml", "-f", "docker-compose.test.yml")
$Profiles  = @()
if ($WithIngestion) { $Profiles = @("--profile", "ingestion") }

$DC = @("docker", "compose") + $BaseFiles + $Profiles

# ── --Down shortcut ───────────────────────────────────────────────────────────

if ($Down) {
    Write-Info "Stopping and removing all Enjin test containers..."
    & $DC[0] ($DC[1..($DC.Length-1)] + @("down", "--remove-orphans"))
    Write-Ok "All containers stopped."
    exit 0
}

# ── Preflight checks ─────────────────────────────────────────────────────────

Write-Host ""
Write-Host "  Enjin OSINT Platform - Quick-start" -ForegroundColor White
Write-Host ""

# Docker installed?
try {
    $null = Get-Command docker -ErrorAction Stop
} catch {
    Stop-WithError "Docker is not installed. Get Docker Desktop at https://docs.docker.com/get-docker/"
}

# Docker running?
$dockerInfo = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "Docker daemon is not running. Start Docker Desktop first."
}

# Compose available?
docker compose version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "Docker Compose not found. Update Docker Desktop."
}

$dockerVer  = (docker --version) -replace '.*version\s+', '' -replace ',.*', ''
$composeVer = (docker compose version --short)
Write-Ok "Docker $dockerVer"
Write-Ok "Docker Compose $composeVer"

# ── Environment file ─────────────────────────────────────────────────────────

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Info "Created .env from .env.example (edit it if you need custom values)."
    } else {
        Write-Warn ".env not found and no .env.example to copy from - services may fail to start."
    }
} else {
    Write-Info "Using existing .env"
}

# ── Bring up the stack ───────────────────────────────────────────────────────

Write-Host ""
Write-Info "Starting services (this may take a few minutes on first run while images build)..."
if ($WithIngestion) {
    Write-Info "  Mode: full stack (databases + API + frontend + ingestion)"
} else {
    Write-Info "  Mode: core stack (databases + API + frontend)"
}
Write-Host ""

& $DC[0] ($DC[1..($DC.Length-1)] + @("up", "--build", "-d"))
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "docker compose up failed. Check the output above."
}

# ── Wait for services ────────────────────────────────────────────────────────

Write-Host ""
Test-Endpoint -Url "http://localhost:8000/health" -Label "API"
Test-Endpoint -Url "http://localhost:3000"         -Label "Frontend"

# ── Summary ──────────────────────────────────────────────────────────────────

$baseFileStr = $BaseFiles -join " "

Write-Host ""
Write-Host "  =====================================================" -ForegroundColor White
Write-Host "    Enjin is running!" -ForegroundColor Green
Write-Host "  =====================================================" -ForegroundColor White
Write-Host ""
Write-Host "  Frontend        http://localhost:3000"
Write-Host "  API             http://localhost:8000"
Write-Host "  API docs        http://localhost:8000/docs"
Write-Host "  API health      http://localhost:8000/health"
Write-Host ""
Write-Host "  Neo4j browser   http://localhost:7474  (neo4j / enjin_dev)"
Write-Host "  Meilisearch     http://localhost:7700  (key: enjin_dev_key)"
Write-Host "  PostgreSQL      localhost:5432         (enjin / enjin_dev)"
Write-Host "  Redis           localhost:6379"
Write-Host ""
Write-Host "  Useful commands:"
Write-Host "    Follow all logs:   docker compose $baseFileStr logs -f"
Write-Host "    Follow API logs:   docker compose $baseFileStr logs -f api"
Write-Host "    Stop everything:   .\quickstart.ps1 -Down"
Write-Host "    Rebuild:           .\quickstart.ps1 (re-run this script)"
Write-Host ""
Write-Host "  =====================================================" -ForegroundColor White

if ($Logs) {
    Write-Host ""
    Write-Info "Following logs (Ctrl+C to stop)..."
    & $DC[0] ($DC[1..($DC.Length-1)] + @("logs", "-f"))
}

} finally {
    Pop-Location
}
