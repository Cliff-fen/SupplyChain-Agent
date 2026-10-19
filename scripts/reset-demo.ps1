param(
  [switch]$WithVolumes,
  [switch]$Build,
  [switch]$SkipStart
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if ($WithVolumes) {
  Write-Warning "This will remove Docker Compose containers and named volumes for the current project."
  Write-Warning "Use it only for classroom demo reset, never against a production environment."
  $confirmation = Read-Host "Type RESET to continue"
  if ($confirmation -ne "RESET") {
    Write-Output "Reset cancelled."
    exit 0
  }
  docker compose down --volumes --remove-orphans
} else {
  docker compose down --remove-orphans
}

if ($SkipStart) {
  Write-Output "Environment stopped. Start was skipped."
  exit 0
}

if ($Build) {
  docker compose up -d --build
} else {
  docker compose up -d
}

Write-Output "Waiting for API readiness..."
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
  try {
    Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/ready" -TimeoutSec 3 | Out-Null
    $ready = $true
    break
  } catch {
    Start-Sleep -Seconds 2
  }
}

if (-not $ready) {
  docker compose ps
  throw "API did not become ready within the expected time."
}

docker compose ps
Write-Output "Demo environment is ready at http://localhost:5173."
