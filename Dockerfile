FROM selenium/standalone-chrome:latest

USER root
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    --no-install-recommends && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    ln -sf /usr/bin/python3 /usr/local/bin/python && \
    touch /var/log/naukri.log

WORKDIR /app

COPY requirements.txt .
RUN /home/seluser/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Runs once and exits — scheduling handled by host cron
ENTRYPOINT ["/home/seluser/venv/bin/python", "/app/main.py"]