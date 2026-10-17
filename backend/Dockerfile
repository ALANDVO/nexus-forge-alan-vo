FROM python:3.12-slim AS base
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app

FROM base AS runtime
COPY --chown=app:app backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app backend/app ./app
ENV NEXUS_DB_PATH=/data/ledger.sqlite
RUN mkdir -p /data && chown -R app:app /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=5 \
  CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]