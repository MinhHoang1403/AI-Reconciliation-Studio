$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
docker compose cp tools/check-persistence.py backend:/tmp/check-persistence.py
docker compose exec -T backend python /tmp/check-persistence.py snapshot
if ($LASTEXITCODE -ne 0) { throw 'Persistence snapshot failed.' }
foreach ($operation in @('restart', 'recreate', 'frontend-recreate')) {
    if ($operation -eq 'restart') { docker compose restart }
    elseif ($operation -eq 'frontend-recreate') { docker compose up -d --no-deps --force-recreate --wait frontend }
    else { docker compose up -d --force-recreate --wait }
    if ($LASTEXITCODE -ne 0) { throw 'Application restart/recreate failed.' }
    docker compose up -d --wait
    if ($LASTEXITCODE -ne 0) { throw 'Healthchecks failed after restart/recreate.' }
    $status = 0
    try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:18180/api/session' -TimeoutSec 10; $status = [int]$response.StatusCode }
    catch { $status = [int]$_.Exception.Response.StatusCode }
    if ($status -ne 403) { throw 'Demo auto-access did not fail closed before re-verification.' }
    Write-Output "PASS: $operation invalidated local demo proof."
    & (Join-Path $PSScriptRoot 'verify-local.ps1')
    docker compose cp tools/check-persistence.py backend:/tmp/check-persistence.py
    docker compose exec -T backend python /tmp/check-persistence.py verify
    if ($LASTEXITCODE -ne 0) { throw 'Persistence verification failed.' }
}
