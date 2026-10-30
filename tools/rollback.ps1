param([ValidatePattern('^[a-f0-9]{7,40}$')][string]$ReleaseRevision = '5f358c4')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$taskImages = @{}
foreach ($taskService in @('backend', 'frontend')) {
    $taskTag = "ai-reconciliation-studio-${taskService}:accepted-main-$ReleaseRevision"
    $taskImage = docker image inspect $taskTag --format '{{json .}}' | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $taskImage.Config.Labels.'org.opencontainers.image.source' -ne 'https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git' -or -not $taskImage.Config.Labels.'org.opencontainers.image.revision'.StartsWith($ReleaseRevision)) { throw 'Accepted source/image identity mismatch.' }
    $taskImages[$taskService] = $taskTag
}
# Chỉ biết compatibility của migration additive này. Không dùng như bypass migration tổng quát.
$taskGuard = @'
from sqlalchemy import text
from studio.database import SessionFactory
with SessionFactory() as db:
    revision=db.scalar(text('SELECT version_num FROM alembic_version'))
    assert revision in {'create_reconciliation','create_conversations'}, 'Unknown schema: compatibility review required'
    assert db.scalar(text("SELECT count(*) FROM jobs WHERE status IN ('QUEUED','RUNNING','RETRYABLE_FAILURE')")) == 0, 'Wait for active jobs'
    assert db.scalar(text("SELECT count(*) FROM workspaces WHERE id='demo'")) == 1
    print('PASS compatible additive schema and no active jobs', revision)
'@
$taskGuard | docker compose exec -T backend python -
if ($LASTEXITCODE -ne 0) { throw 'Rollback compatibility gate failed.' }
# Main cũ không nhận revision Alembic mới. Khởi tạo proof riêng rồi chạy cùng API cũ;
# không chạy upgrade/downgrade hoặc sửa database. Override thuộc đúng Compose hiện có.
$taskStartup = "import os,secrets; from studio.config import settings; assert len(settings.session_secret.get_secret_value())>=32; settings.instance_path.parent.mkdir(parents=True,exist_ok=True); settings.instance_path.write_text(secrets.token_urlsafe(32)); settings.demo_proof_path.unlink(missing_ok=True); os.execvp('uvicorn',['uvicorn','studio.api:app','--host','0.0.0.0','--port','8000','--no-proxy-headers','--no-access-log'])"
$taskOverride = @{services=@{
    backend=@{image=$taskImages.backend; command=@('python','-c',$taskStartup)}
    worker=@{image=$taskImages.backend}
    frontend=@{image=$taskImages.frontend}
}}
$taskPath = Join-Path $PWD 'runtime/rollback-compose.json'
[IO.File]::WriteAllText($taskPath,($taskOverride | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
docker compose -f compose.yaml -f $taskPath up -d --no-build --wait
if ($LASTEXITCODE -ne 0) { throw 'Rollback deployment failed; keep volumes and inspect health.' }
& (Join-Path $PSScriptRoot 'verify-local.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Rollback local verification failed.' }
Write-Output 'Rollback running accepted main images on unchanged schema/volumes. Use the same override for operations; plain compose up returns to local candidate images.'
