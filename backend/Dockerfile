FROM python:3.12.14-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend POLARS_MAX_THREADS=2
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home studio
COPY backend backend
COPY alembic.ini alembic.ini
RUN mkdir -p /var/lib/studio /run/studio && chown -R studio:studio /var/lib/studio /run/studio
USER studio
CMD ["python", "-m", "studio.startup"]
