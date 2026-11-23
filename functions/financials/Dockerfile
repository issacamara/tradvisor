FROM python:3.11.11-slim-bookworm@sha256:081075da77b2b55c23c088251026fb69a7b2bf92471e491ff5fd75c192fd38e5

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY archive/legacy-ingestion/scripts/requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /app/requirements.lock

RUN mkdir -p /app/functions/financials
COPY functions/financials/fi1_job.py /app/functions/financials/
COPY functions/financials/scrape_financials_job.py /app/functions/financials/
COPY functions/financials/monthly_financials.py /app/functions/financials/
COPY functions/financials/scrape_financials /usr/local/bin/scrape_financials
COPY functions/financials/monthly_financials /usr/local/bin/monthly_financials
COPY functions/financials/insert_financials.py /app/insert_financials.py
COPY archive/legacy-ingestion/scripts/helper.py /app/helper.py
COPY archive/legacy-ingestion/scripts/ingestion_observability.py /app/ingestion_observability.py
RUN chmod 0555 /usr/local/bin/scrape_financials /usr/local/bin/monthly_financials

USER 10001:10001
ENTRYPOINT ["scrape_financials"]
