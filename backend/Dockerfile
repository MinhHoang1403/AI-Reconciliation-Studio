# Image backend: Python 3.12 + phụ thuộc đã khóa trong uv.lock.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend

# Cài phụ thuộc trước để Docker tái dùng lớp này khi chỉ sửa source.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY backend ./backend

# Chạy bằng người dùng thường, không dùng root; thư mục lưu tệp thuộc người dùng này.
RUN useradd --system --uid 10001 studio && mkdir -p /data/files && chown studio /data/files
USER studio

ARG STUDIO_REVISION=unknown
ENV STUDIO_REVISION=$STUDIO_REVISION

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"]
# Nâng cấu trúc DB lên bản mới nhất rồi mới mở API.
CMD ["sh", "-c", "python -m studio.migrate && exec uvicorn studio.main:app --host 0.0.0.0 --port 8000"]
