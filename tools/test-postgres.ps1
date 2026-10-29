param([switch]$All)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
# Reuse backend and PostgreSQL containers. No additional Compose project or database server.
docker compose exec -T --user root backend python -c "from pathlib import Path; import shutil; p=Path('/tmp/studio-tests'); assert p.resolve()==Path('/tmp/studio-tests'); shutil.rmtree(p) if p.exists() else None"
if ($LASTEXITCODE -ne 0) { throw 'Cannot refresh temporary synthetic test source.' }
docker compose cp tests backend:/tmp/studio-tests
docker compose cp pyproject.toml backend:/tmp/studio-pyproject.toml
if ($LASTEXITCODE -ne 0) { throw 'Cannot copy synthetic tests.' }
docker compose exec -T backend python -m pip install --quiet --upgrade --target /tmp/studio-checks pytest==9.1.1 hypothesis==6.170.12
if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare temporary test tooling in backend.' }
$pytestArgs = @('-q', '-c', '/tmp/studio-pyproject.toml', '-o', 'cache_dir=/tmp/studio-pytest-cache')
if (-not $All) { $pytestArgs += @('-m', 'integration') }
$pytestArgs += '/tmp/studio-tests'
docker compose exec -T -e STUDIO_POSTGRES_TESTS=1 -e HYPOTHESIS_STORAGE_DIRECTORY=/tmp/studio-hypothesis -e PYTHONPATH=/app/backend:/tmp/studio-checks backend python -m pytest @pytestArgs
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL integration failed.' }
