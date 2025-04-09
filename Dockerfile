FROM python:3.9-slim
#FROM ubuntu:18.04
WORKDIR tradvisor/

#RUN apt-get install -y git

#RUN git clone https://github.com/issacamara/tradvisor.git .
COPY database/ database/
#COPY webapp/requirements.txt .
COPY webapp/ webapp/
#COPY webapp/config.yml .

RUN pip install -r webapp/requirements.txt

#RUN export PYTHONPATH="${PYTHONPATH}:$HOME/tradvisor/util/"
#RUN mkdir "data"
#RUN mkdir "database"
#RUN mkdir "processed_data"
#RUN python scripts/scrape_brvm_shares.py
#RUN python scripts/insert_shares.py

# Set environment variables
ENV PORT=8501
EXPOSE 8501

#ENTRYPOINT ["streamlit", "run", "webapp/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
CMD streamlit run webapp/app.py --server.port=$PORT --server.address=0.0.0.0 --server.enableCORS=false --server.enableXsrfProtection=false