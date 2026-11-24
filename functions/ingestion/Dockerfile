#LABEL authors="issacamara"
FROM python:3.9-slim-buster as base

WORKDIR tradvisor/scripts/
COPY requirements.txt .
COPY helper.py .
RUN pip install --no-cache-dir -r requirements.txt

######## SHARES ########
FROM base as scrape_shares
COPY scrape_shares.py main.py
CMD ["functions-framework", "--target=entry_point", "--port=8080"]

FROM base as insert_shares
COPY insert_shares.py main.py
CMD ["functions-framework", "--target=entry_point", "--port=8080"]

######## DIVIDENDS ########
FROM base as scrape_dividends
COPY scrape_dividends.py main.py
CMD ["functions-framework", "--target=entry_point", "--port=8080"]

FROM base as insert_dividends
COPY insert_dividends.py main.py
CMD ["functions-framework", "--target=entry_point", "--port=8080"]
