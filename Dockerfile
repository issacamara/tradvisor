FROM python:3.9
WORKDIR tradvisor/

RUN apt-get install -y git

RUN git clone https://github.com/issacamara/tradvisor.git .

RUN pip install -r requirements.txt

RUN export PYTHONPATH="${PYTHONPATH}:~/tradvisor"
EXPOSE 8501

ENTRYPOINT ["streamlit", "run", "webapp/app.py", "--server.port=8501", "--server.address=0.0.0.0"]