# Dựng lại graph code của dự án bằng Graphify bản mã nguồn mở (chạy trên máy, miễn phí).
# Chỉ đọc code bằng tree-sitter (--code-only): không gọi LLM, không gửi code ra ngoài.
# Kết quả: graphify-out/graph.json (cho MCP "graphify" của Claude Code) và
# graphify-out/graph.html (xem tại http://127.0.0.1:3114/graph.html, container code-graph).
# Cách chạy:  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\code-graph.ps1

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = 'utf-8'

graphify extract . --code-only
if ($LASTEXITCODE -ne 0) { throw "graphify extract lỗi (mã $LASTEXITCODE)." }
graphify export html
if ($LASTEXITCODE -ne 0) { throw "graphify export html lỗi (mã $LASTEXITCODE)." }
Write-Host "Đã dựng lại graph code. Mở http://127.0.0.1:3114/graph.html"

# Nhập graph vào agentmemory (tab Graph ở http://127.0.0.1:3113) nếu máy chủ đang chạy.
# Không gọi LLM. Khóa đọc từ .env của agentmemory trên máy, không in ra.
$envFile = 'C:\Work\agentmemory\.env'
$match = if (Test-Path $envFile) { Select-String -Path $envFile -Pattern '^AGENTMEMORY_SECRET=(.+)$' }
if (-not $match) {
    Write-Host 'Bỏ qua nhập vào agentmemory: không thấy khóa trong C:\Work\agentmemory\.env.'
    return
}
$headers = @{ Authorization = "Bearer $($match.Matches[0].Groups[1].Value)"; 'Content-Type' = 'application/json' }
try {
    $reply = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:3111/agentmemory/graph/import-graphify' `
        -Headers $headers -Body '{"cwd":"/import/ai-reconciliation-studio"}' -TimeoutSec 300
    Write-Host "Đã nhập vào agentmemory: $($reply.nodesImported) nút, $($reply.edgesImported) liên kết. Mở http://127.0.0.1:3113/#graph"
} catch {
    Write-Host "Chưa nhập được vào agentmemory (máy chủ chưa chạy?): $($_.Exception.Message)"
}
