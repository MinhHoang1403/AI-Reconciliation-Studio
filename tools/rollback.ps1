param([ValidatePattern('^([a-f0-9]{7,40})?$')][string]$ReleaseRevision = '')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$taskImages = @{}
$taskRevisions = @{}
foreach ($taskService in @('backend', 'frontend')) {
    $taskTag = if ($ReleaseRevision) { "ai-reconciliation-studio-${taskService}:accepted-main-$ReleaseRevision" } else { "ai-reconciliation-studio-${taskService}:rollback" }
    $taskImage = docker image inspect $taskTag --format '{{json .}}' | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $taskImage.Config.Labels.'org.opencontainers.image.source' -ne 'https://github.com/MinhHoang1403/AI-Reconciliation-Studio.git' -or $taskImage.Config.Labels.'org.opencontainers.image.revision' -notmatch '^[a-f0-9]{40}$' -or ($ReleaseRevision -and -not $taskImage.Config.Labels.'org.opencontainers.image.revision'.StartsWith($ReleaseRevision))) { throw 'Rollback source/image identity mismatch.' }
    $taskImages[$taskService] = $taskTag
    $taskRevisions[$taskService] = $taskImage.Config.Labels.'org.opencontainers.image.revision'
}
if ($taskRevisions.backend -ne $taskRevisions.frontend) { throw 'Rollback images must have the same source revision.' }
# Source của image đã xác minh cho biết có đọc được nullable request policy hay không.
$taskBackendRevision = $taskRevisions.backend
$taskConfigSource = git show "${taskBackendRevision}:backend/studio/config.py"
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify rollback configuration compatibility from repository history.' }
$taskSupportsNullable = ($taskConfigSource -join "`n") -match 'external_ai_request_budget:\s+int\s*\|\s*None'
$taskLifecycleSource = git ls-tree --name-only $taskBackendRevision backend/studio/resource_lifecycle.py
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify lifecycle compatibility from repository history.' }
$taskSupportsLifecycle = $taskLifecycleSource -eq 'backend/studio/resource_lifecycle.py'
# Chỉ các migrations additive đã review; không downgrade DB hoặc suy compatibility tổng quát.
$taskGuard = @'
import sys
from sqlalchemy import text
from studio.config import settings
from studio.database import SessionFactory
with SessionFactory() as db:
    if sys.argv[1] != 'True':
        assert all(value is not None for value in (
            settings.external_ai_request_budget, settings.agent_request_budget,
            settings.planner_request_budget, settings.assistant_request_budget,
        )), 'Restore the audited finite environment before using a pre-nullable rollback image; retain all request history'
        assert db.scalar(text("SELECT count(*) FROM workspaces WHERE policy->'external_request_budget' = 'null'::jsonb")) == 0, 'Restore compatible finite workspace policy from the audited backup; never reset the request ledger'
    revision=db.scalar(text('SELECT version_num FROM alembic_version'))
    assert revision in {'create_reconciliation','create_conversations','create_agent_workflows','add_resource_lifecycle'}, 'Unknown schema: compatibility review required'
    if revision == 'add_resource_lifecycle' and sys.argv[2] != 'True':
        for table in ('projects', 'datasets'):
            assert not db.scalar(text(f'SELECT EXISTS (SELECT 1 FROM {table} WHERE archived_at IS NOT NULL OR deleted_at IS NOT NULL)')), 'Inactive data requires a lifecycle-aware backend; roll back frontend only'
    assert db.scalar(text("SELECT count(*) FROM jobs WHERE status IN ('QUEUED','RUNNING','RETRYABLE_FAILURE')")) == 0, 'Wait for active jobs'
    if revision in {'create_agent_workflows','add_resource_lifecycle'}:
        assert db.scalar(text("SELECT count(*) FROM agent_workflows WHERE state IN ('CREATED','RUNNING')")) == 0, 'Wait for workflows to settle'
        # Reviews remain untouched; resumption requires a compatible accepted source.
        print('Agent reviews are retained; resumption depends on the selected accepted source')
    assert db.scalar(text("SELECT count(*) FROM workspaces WHERE id='demo'")) == 1
    print('PASS compatible additive schema and no active jobs', revision)
'@
$taskGuard | docker compose exec -T backend python - "$taskSupportsNullable" "$taskSupportsLifecycle"
if ($LASTEXITCODE -ne 0) { throw 'Rollback compatibility gate failed.' }
# Giữ schema hiện hành đã qua compatibility gate; không chạy upgrade/downgrade.
# Khởi tạo proof riêng rồi chạy API của image đã chọn trong cùng Compose hiện có.
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
Write-Output 'Rollback running verified Studio images on unchanged schema/volumes. Use the same override for operations; plain compose up returns to local candidate images.'
