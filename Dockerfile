FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --requirement requirements.txt

RUN addgroup --system careerpilot \
    && adduser --system --ingroup careerpilot careerpilot

COPY --chown=careerpilot:careerpilot app ./app
COPY --chown=careerpilot:careerpilot alembic ./alembic
COPY --chown=careerpilot:careerpilot alembic.ini ./alembic.ini

USER careerpilot

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
