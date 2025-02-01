#LABEL authors="issacamara"
FROM python:3.9-slim
#WORKDIR tradvisor/scripts/

WORKDIR tradvisor/scripts/

#COPY . /app


COPY scrape_shares.py main.py
COPY helper.py helper.py
COPY config.yml scrape_brvm_shares.py
COPY requirements.txt requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

#CMD ["python", "--bind", ":8080", "scrape_brvm_shares:main"]
CMD ["functions-framework", "--target", "entry_point"]