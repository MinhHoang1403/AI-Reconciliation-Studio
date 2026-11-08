param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not $SkipBuild) {
    # Buildx's Git label can equal HEAD even when Docker copies modified source.
    # Ordinary builds must therefore have committed build inputs. A deliberately
    # uncommitted acceptance candidate needs an explicit content-derived label;
    # it must never be published or described as the unchanged Git revision.
    $taskDirtyBuildInputs = @(git status --porcelain --untracked-files=all -- backend frontend requirements.txt pyproject.toml uv.lock alembic.ini compose.yaml .dockerignore)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot verify Git identity before building application images.' }
    if ($taskDirtyBuildInputs.Count -gt 0) {
        throw 'Application build inputs have uncommitted changes. Commit verified changes before a normal build; an uncommitted acceptance candidate must use explicit content-derived image labels.'
    }
}
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
