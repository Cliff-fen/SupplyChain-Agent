param(
  [switch]$RunTests,
  [switch]$RunE2E,
  [switch]$RunHelm,
  [string]$OutputDirectory = "output/acceptance"
)

$ErrorActionPreference = "Continue"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$reportDir = Join-Path $repoRoot $OutputDirectory
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
$reportPath = Join-Path $reportDir "acceptance-$timestamp.md"

$results = New-Object System.Collections.Generic.List[object]

function Invoke-Check {
  param(
    [string]$Name,
    [string]$Command,
    [string]$WorkingDirectory = $repoRoot
  )

  Write-Output "Running: $Name"
  $started = Get-Date
  $output = & powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-Location '$WorkingDirectory'; $Command" 2>&1
  $exitCode = $LASTEXITCODE
  if ($null -eq $exitCode) {
    $exitCode = 0
  }
  $duration = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
  $results.Add([pscustomobject]@{
    Name = $Name
    Command = $Command
    ExitCode = $exitCode
    Duration = $duration
    Output = ($output -join "`n")
  })
}

Invoke-Check "Git working tree" "git status --short"
Invoke-Check "Compose config" "docker compose config --quiet"
Invoke-Check "Compose services" "docker compose ps"
Invoke-Check "API live" "Invoke-RestMethod http://localhost:8000/api/v1/health/live | ConvertTo-Json -Depth 5"
Invoke-Check "API ready" "Invoke-RestMethod http://localhost:8000/api/v1/health/ready | ConvertTo-Json -Depth 5"
Invoke-Check "Frontend HTTP" "(Invoke-WebRequest http://localhost:5173).StatusCode"

if ($RunTests) {
  Invoke-Check "Backend pytest" "docker compose exec -T api pytest -q"
  Invoke-Check "Backend ruff" "docker compose exec -T api ruff check app scripts tests"
  Invoke-Check "Frontend unit tests" "npm --prefix frontend test"
  Invoke-Check "Frontend build" "npm --prefix frontend run build"
}

if ($RunE2E) {
  Invoke-Check "Frontend Playwright E2E" "`$env:PLAYWRIGHT_BASE_URL='http://localhost:5173'; npm --prefix frontend run test:e2e"
}

if ($RunHelm) {
  Invoke-Check "Helm smoke" "powershell -ExecutionPolicy Bypass -File scripts/helm-smoke.ps1"
}

$failed = $results | Where-Object { $_.ExitCode -ne 0 }
$status = if ($failed.Count -eq 0) { "PASS" } else { "FAIL" }

$content = New-Object System.Collections.Generic.List[string]
$content.Add("# SupplyMind Local Acceptance Report")
$content.Add("")
$content.Add("- Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')")
$content.Add("- Repository: $repoRoot")
$content.Add("- Result: $status")
$content.Add("")
$content.Add("## Summary")
$content.Add("")
$content.Add("| Check | Exit | Duration |")
$content.Add("| --- | ---: | ---: |")
foreach ($result in $results) {
  $content.Add("| $($result.Name) | $($result.ExitCode) | $($result.Duration)s |")
}
$content.Add("")

foreach ($result in $results) {
  $content.Add("## $($result.Name)")
  $content.Add("")
  $content.Add("Command:")
  $content.Add("")
  $content.Add('```powershell')
  $content.Add($result.Command)
  $content.Add('```')
  $content.Add("")
  $content.Add("Output:")
  $content.Add("")
  $content.Add('```text')
  $content.Add($result.Output)
  $content.Add('```')
  $content.Add("")
}

Set-Content -Path $reportPath -Value $content -Encoding UTF8

Write-Output "Acceptance report written to $reportPath"
if ($failed.Count -ne 0) {
  exit 1
}
