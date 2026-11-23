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
