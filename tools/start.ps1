# Build và chạy bộ 3 container, kiểm tra đủ 3/3 healthy, rồi dọn image cũ của dự án.
# Cách chạy (từ thư mục gốc repo):  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path -LiteralPath '.env')) {
    throw 'Thiếu tệp .env. Sao chép .env.example thành .env rồi điền POSTGRES_PASSWORD.'
}

# Gắn commit Git vào image để biết container đang chạy bản source nào.
$revision = (git rev-parse HEAD)
if ($LASTEXITCODE -ne 0) { throw 'Không đọc được commit Git hiện tại.' }
$changes = @(git status --porcelain -- backend frontend pyproject.toml uv.lock compose.yaml)
if ($changes.Count -gt 0) { $revision = "$revision-dirty" }
$env:STUDIO_REVISION = $revision

docker compose up --detach --build --wait --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'Build hoặc khởi động container thất bại.' }

# Kiểm đúng 3 container và cả 3 đều healthy.
$ids = @(docker compose ps --quiet)
if ($ids.Count -ne 3) { throw "Cần 3 container, đang có $($ids.Count)." }
foreach ($container in (docker inspect $ids | Out-String | ConvertFrom-Json)) {
    if ($container.State.Health.Status -ne 'healthy') {
        throw "Container $($container.Name) chưa healthy ($($container.State.Health.Status))."
    }
}

# Dọn image cũ không còn được dùng, chỉ của dự án này (RULES R9).
docker image prune --force --filter 'label=com.docker.compose.project=ai-reconciliation-studio' | Out-Null

$reply = Invoke-RestMethod -Uri 'http://127.0.0.1:18180/api/ready' -TimeoutSec 10
if ($reply.status -ne 'ok') { throw 'Backend chưa sẵn sàng.' }
Write-Output "3/3 container healthy, bản $revision. Mở http://127.0.0.1:18180"
