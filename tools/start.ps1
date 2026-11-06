param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path -LiteralPath '.env')) {
    function New-LocalSecret {
        $bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        return -join ($bytes | ForEach-Object { $_.ToString('x2') })
    }
    $config = Get-Content -LiteralPath '.env.example' -Raw
    $config = $config.Replace('replace-with-random-local-password', (New-LocalSecret))
    $config = $config.Replace('replace-with-at-least-32-random-characters', (New-LocalSecret))
    # The company URL is supplied by the operator in the ignored .env, never bundled in JS.
    [System.IO.File]::WriteAllText((Join-Path $PWD '.env'), $config)
}
if ($SkipBuild) {
    docker compose up -d --no-build --wait
} else {
    # Keep source identity in ordinary builds as well as release builds.
    $taskPreviousGitLabels = $env:BUILDX_GIT_LABELS
    try {
        $env:BUILDX_GIT_LABELS = 'full'
        docker compose up -d --build --wait
        $taskBuildExitCode = $LASTEXITCODE
    } finally {
        $env:BUILDX_GIT_LABELS = $taskPreviousGitLabels
    }
    if ($taskBuildExitCode -ne 0) { throw 'Docker build or startup failed.' }
}
if ($LASTEXITCODE -ne 0) { throw 'Docker services did not become healthy.' }
& (Join-Path $PSScriptRoot 'verify-local.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Loopback verification failed.' }
Write-Output 'Open http://127.0.0.1:18180'
