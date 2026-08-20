# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip wheel --wheel-dir /wheels .


FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="LedgerLens" \
      org.opencontainers.image.description="Explainable invoice OCR and validation API" \
      org.opencontainers.image.source="https://github.com/aelsaeed/LedgerLens" \
      org.opencontainers.image.licenses="MIT"

ENV PATH="/opt/ledgerlens/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 ledgerlens \
    && useradd --uid 10001 --gid ledgerlens --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin ledgerlens

COPY --from=builder /wheels /wheels
RUN python -m venv /opt/ledgerlens \
    && /opt/ledgerlens/bin/python -m pip install --no-index --find-links=/wheels ledgerlens \
    && rm -rf /wheels

WORKDIR /app
USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3); raise SystemExit(response.status != 200)"]

CMD ["uvicorn", "invoice_scanner.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
