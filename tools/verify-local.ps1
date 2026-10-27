$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$containerIds = @(docker compose ps -q)
if ($LASTEXITCODE -ne 0 -or $containerIds.Count -ne 4) { throw 'Expected exactly four running application services.' }
# Inspect only non-sensitive identity/labels and actual published ports; do not expose env/secrets.
$containers = @()
foreach ($containerId in $containerIds) {
    $raw = docker inspect --format '{{json .}}' $containerId | ConvertFrom-Json
    $containers += @{ Id = $raw.Id; Config = @{ Labels = $raw.Config.Labels }; NetworkSettings = @{ Ports = $raw.NetworkSettings.Ports } }
}
$containers | ConvertTo-Json -Depth 12 -Compress | docker compose exec -T backend python -m studio.access
if ($LASTEXITCODE -ne 0) { throw 'Actual published bindings do not satisfy local demo policy.' }
