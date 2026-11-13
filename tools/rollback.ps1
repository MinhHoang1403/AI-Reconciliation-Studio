param(
    [ValidatePattern('^([a-f0-9]{7,40})?$')][string]$ReleaseRevision = '',
    [switch]$PreviousPreparation,
    [switch]$VerifyOnly
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($ReleaseRevision -and $PreviousPreparation) { throw 'Choose one rollback image pair.' }
$taskImages = @{}
$taskRevisions = @{}
foreach ($taskService in @('backend', 'frontend')) {
    $taskTag = if ($ReleaseRevision) {
        "ai-reconciliation-studio-${taskService}:accepted-main-$ReleaseRevision"
    } elseif ($PreviousPreparation) {
        "ai-reconciliation-studio-${taskService}:pre-automatic-preparation"
    } else {
        "ai-reconciliation-studio-${taskService}:rollback"
    }
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
$taskReservationMigration = 'backend/migrations/versions/retain_purged_reservations.py'
$taskReservationSource = git ls-tree --name-only $taskBackendRevision $taskReservationMigration
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify reservation ledger compatibility from repository history.' }
$taskSupportsRetainedReservations = $taskReservationSource -eq $taskReservationMigration
$taskQualityMigration = 'backend/migrations/versions/add_data_quality_decisions.py'
$taskQualitySource = git ls-tree --name-only $taskBackendRevision $taskQualityMigration
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify data quality compatibility from repository history.' }
$taskSupportsQuality = $taskQualitySource -eq $taskQualityMigration
$taskPreparationSource = git ls-tree --name-only $taskBackendRevision backend/studio/observed_reconciliation.py
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify automatic preparation compatibility from repository history.' }
$taskSupportsPreparation = $taskPreparationSource -eq 'backend/studio/observed_reconciliation.py'
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
    purge_revisions = {'add_purge_receipts', 'retain_purged_reservations', 'add_data_quality_decisions'}
    lifecycle_revisions = purge_revisions | {'add_resource_lifecycle'}
    workflow_revisions = lifecycle_revisions | {'create_agent_workflows'}
    assert revision in workflow_revisions | {'create_reconciliation', 'create_conversations'}, 'Unknown schema: compatibility review required'
    if revision in {'retain_purged_reservations', 'add_data_quality_decisions'}:
        assert sys.argv[3] == 'True', 'Rollback image must retain provider reservations after workspace purge'
    if revision == 'add_data_quality_decisions' and sys.argv[4] != 'True':
        assert not db.scalar(text('SELECT EXISTS (SELECT 1 FROM data_quality_decisions)')), 'Use a rollback image that can read stored data quality decisions'
        assert not db.scalar(text("SELECT EXISTS (SELECT 1 FROM agent_workflows WHERE jsonb_path_exists(detail, '$.blocks[*].quality_draft'))")), 'Use a rollback image that can read active data quality drafts'
    if revision in purge_revisions:
        assert not db.scalar(text('SELECT EXISTS (SELECT 1 FROM purge_receipts WHERE completed_at IS NULL)')), 'Finish pending filesystem deletion before rollback'
    if revision in lifecycle_revisions and sys.argv[2] != 'True':
        for table in ('projects', 'datasets'):
            assert not db.scalar(text(f'SELECT EXISTS (SELECT 1 FROM {table} WHERE archived_at IS NOT NULL OR deleted_at IS NOT NULL)')), 'Inactive data requires a lifecycle-aware backend; roll back frontend only'
    assert db.scalar(text("SELECT count(*) FROM jobs WHERE status IN ('QUEUED','RUNNING','RETRYABLE_FAILURE')")) == 0, 'Wait for active jobs'
    if revision in workflow_revisions:
        assert db.scalar(text("SELECT count(*) FROM agent_workflows WHERE state IN ('CREATED','RUNNING')")) == 0, 'Wait for workflows to settle'
        # Reviews remain untouched; resumption requires a compatible accepted source.
        print('Agent reviews are retained; resumption depends on the selected accepted source')
    if revision == 'add_data_quality_decisions' and sys.argv[5] != 'True':
        assert not db.scalar(text("""
            SELECT EXISTS (SELECT 1 FROM jobs WHERE kind = 'automatic_preparation')
                OR EXISTS (SELECT 1 FROM mapping_revisions WHERE decision ? 'policy_application')
                OR EXISTS (SELECT 1 FROM reconciliation_contracts WHERE definition ? 'observation')
                OR EXISTS (
                    SELECT 1 FROM agent_workflows
                    WHERE jsonb_path_exists(detail, '$.blocks[*] ? (@.type == "source_comparison")')
                )
        """)), 'New preparation history requires compatible images or an explicit restore of the pre-release backup'
    assert db.scalar(text("SELECT count(*) FROM workspaces WHERE id='demo'")) == 1
    print('PASS compatible additive schema and no active jobs', revision)
'@
$taskGuard | docker compose exec -T backend python - "$taskSupportsNullable" "$taskSupportsLifecycle" "$taskSupportsRetainedReservations" "$taskSupportsQuality" "$taskSupportsPreparation"
if ($LASTEXITCODE -ne 0) { throw 'Rollback compatibility gate failed.' }
if ($VerifyOnly) {
    Write-Output "Verified rollback images for $taskBackendRevision against the current deployment."
    return
}
# Giữ schema hiện hành đã qua compatibility gate; không chạy upgrade/downgrade.
# Khởi tạo proof riêng rồi chạy API của image đã chọn trong cùng Compose hiện có.
$taskAccessSource = git show "${taskBackendRevision}:backend/studio/access.py"
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify rollback local proof compatibility.' }
$taskInstance = if (($taskAccessSource -join "`n") -match 'backend identity differs from host inspection') { 'socket.gethostname()' } else { 'secrets.token_urlsafe(32)' }
$taskStartup = "import os,secrets,socket; from studio.config import settings; assert len(settings.session_secret.get_secret_value())>=32; settings.instance_path.parent.mkdir(parents=True,exist_ok=True); settings.instance_path.write_text($taskInstance); proof=getattr(settings,'local_proof_file',None) or settings.demo_proof_path; proof and proof.unlink(missing_ok=True); os.execvp('uvicorn',['uvicorn','studio.api:app','--host','0.0.0.0','--port','8000','--no-proxy-headers','--no-access-log'])"
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
