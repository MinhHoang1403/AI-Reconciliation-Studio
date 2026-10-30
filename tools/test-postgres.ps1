param([switch]$All, [switch]$Source)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
# Reuse backend and PostgreSQL containers. No additional Compose project or database server.
docker compose exec -T --user root backend python -c "from pathlib import Path; import shutil; p=Path('/tmp/studio-tests'); assert p.resolve()==Path('/tmp/studio-tests'); shutil.rmtree(p) if p.exists() else None"
if ($LASTEXITCODE -ne 0) { throw 'Cannot refresh temporary synthetic test source.' }
docker compose cp tests backend:/tmp/studio-tests
docker compose cp tools/check-backup-restore.py backend:/tmp/studio-tests/check-backup-restore.py
if ($LASTEXITCODE -ne 0) { throw 'Cannot copy backup verification helper.' }
docker compose cp tools/check-reconciliation.py backend:/tmp/studio-tests/check-reconciliation.py
if ($LASTEXITCODE -ne 0) { throw 'Cannot copy reconciliation acceptance helper.' }
docker compose cp pyproject.toml backend:/tmp/studio-pyproject.toml
if ($LASTEXITCODE -ne 0) { throw 'Cannot copy synthetic tests.' }
docker compose exec -T backend python -m pip install --quiet --upgrade --target /tmp/studio-checks pytest==9.1.1 hypothesis==6.170.12
if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare temporary test tooling in backend.' }
$pytestArgs = @('-q', '-c', '/tmp/studio-pyproject.toml', '-o', 'cache_dir=/tmp/studio-pytest-cache')
if (-not $All) { $pytestArgs += @('-m', 'integration') }
$pytestArgs += '/tmp/studio-tests'
$taskPythonPath = '/app/backend:/tmp/studio-checks'
$taskWorkingDirectory = '/app'
if ($Source) {
    # Test feature source in temporary files of the existing container; never alter /app.
    docker compose exec -T --user root backend python -c "from pathlib import Path; import shutil; p=Path('/tmp/studio-source'); assert p.resolve()==Path('/tmp/studio-source'); shutil.rmtree(p) if p.exists() else None; p.mkdir(); shutil.chown(p,user='studio',group='studio')"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare temporary source directory.' }
    docker compose cp backend backend:/tmp/studio-source/backend
    if ($LASTEXITCODE -ne 0) { throw 'Cannot copy backend source.' }
    docker compose cp alembic.ini backend:/tmp/studio-source/alembic.ini
    if ($LASTEXITCODE -ne 0) { throw 'Cannot copy migration configuration.' }
    $taskPythonPath = '/tmp/studio-source/backend:/tmp/studio-checks'
    $taskWorkingDirectory = '/tmp/studio-source'
}
docker compose exec -T -w $taskWorkingDirectory -e STUDIO_POSTGRES_TESTS=1 -e HYPOTHESIS_STORAGE_DIRECTORY=/tmp/studio-hypothesis -e "PYTHONPATH=$taskPythonPath" backend python -m pytest @pytestArgs
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL integration failed.' }
