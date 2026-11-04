$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$containerIds = @(docker compose ps -q)
if ($LASTEXITCODE -ne 0 -or $containerIds.Count -ne 4) { throw 'Expected exactly four running application services.' }
# Inspect only non-sensitive identity/labels and actual published ports; do not expose env/secrets.
$containers = @()
$taskStartTimes = @{}
foreach ($containerId in $containerIds) {
    $raw = docker inspect --format '{{json .}}' $containerId | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or -not $raw -or $raw.State.Status -ne 'running' -or $raw.State.Health.Status -ne 'healthy') {
        throw 'A Studio service is unavailable or unhealthy; run tools/start.ps1 -SkipBuild.'
    }
    $containers += @{ Id = $raw.Id; Config = @{ Labels = $raw.Config.Labels }; NetworkSettings = @{ Ports = $raw.NetworkSettings.Ports } }
    $taskStartTimes[$containerId] = $raw.State.StartedAt
}
$containers | ConvertTo-Json -Depth 12 -Compress | docker compose exec -T backend python -m studio.access
if ($LASTEXITCODE -ne 0) { throw 'Actual published bindings do not satisfy local demo policy.' }

# A deployment proof is necessary, but only same-origin HTTP proves that a user
# can bootstrap a session through Nginx and read authorized workspace resources.
$taskBase = 'http://127.0.0.1:18180'
$taskSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
function Get-VerifiedLocalResponse([string]$Path) {
    try {
        $taskResponse = Invoke-WebRequest -Uri ($taskBase + $Path) -WebSession $taskSession -UseBasicParsing -TimeoutSec 15 -MaximumRedirection 0
    } catch {
        $taskStatus = if ($_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 'unavailable' }
        throw "Local verification failed at GET $Path (HTTP $taskStatus). Run tools/start.ps1 -SkipBuild; inspect Studio health and deployment proof if it still fails."
    }
    if ($taskResponse.StatusCode -ne 200) { throw "Local verification expected HTTP 200 at GET $Path." }
    return $taskResponse
}
$null = Get-VerifiedLocalResponse '/'
$taskFrontend = Get-VerifiedLocalResponse '/health'
$taskFrontendId = ($containers | Where-Object { $_.Config.Labels.'com.docker.compose.service' -eq 'frontend' }).Id
$taskLiveId = [string]$taskFrontend.Headers['X-Studio-Instance']
if ($taskLiveId.Length -lt 12 -or -not $taskFrontendId.StartsWith($taskLiveId)) { throw 'Frontend HTTP identity differs from the verified deployment.' }
$null = Get-VerifiedLocalResponse '/api/live'
$null = Get-VerifiedLocalResponse '/api/ready'
$taskActor = (Get-VerifiedLocalResponse '/api/session').Content | ConvertFrom-Json
if ($taskActor.workspace_id -ne 'demo' -or $taskActor.actor_id -ne 'demo-owner' -or $taskActor.role -notin @('owner', 'editor', 'viewer')) {
    throw 'Local session returned an unexpected principal, workspace or role.'
}
$taskCookie = $taskSession.Cookies.GetCookies([uri]($taskBase + '/api/session'))['studio_session']
if (-not $taskCookie -or -not $taskCookie.HttpOnly -or $taskCookie.Path -ne '/api') { throw 'Local session cookie is missing or has unexpected scope.' }
$taskSettings = (Get-VerifiedLocalResponse '/api/settings').Content | ConvertFrom-Json
if (-not $taskSettings.workspace_name) { throw 'Authorized workspace settings did not load.' }
$taskProjects = (Get-VerifiedLocalResponse '/api/projects?limit=1').Content | ConvertFrom-Json
if ($null -eq $taskProjects.PSObject.Properties['items']) { throw 'Authorized project listing did not load.' }
$taskFinalIds = @(docker compose ps -q)
if ($LASTEXITCODE -ne 0 -or @(Compare-Object ($containerIds | Sort-Object) ($taskFinalIds | Sort-Object)).Count -ne 0) {
    throw 'Studio containers changed during verification; rerun tools/start.ps1 -SkipBuild after the last recreate.'
}
foreach ($containerId in $taskFinalIds) {
    $taskState = docker inspect --format '{{json .State}}' $containerId | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $taskState.Status -ne 'running' -or $taskState.Health.Status -ne 'healthy' -or $taskState.StartedAt -ne $taskStartTimes[$containerId]) {
        throw 'A Studio service restarted or became unhealthy during verification; rerun tools/start.ps1 -SkipBuild.'
    }
}
Write-Output 'Verified local HTTP, frontend identity, session, settings and project access.'
