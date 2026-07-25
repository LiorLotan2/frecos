FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

COPY vendor/gptcache/requirements.txt vendor/gptcache/requirements.txt
RUN pip install --no-cache-dir -r vendor/gptcache/requirements.txt \
    pytest pytest-benchmark flake8 psutil

COPY . .

CMD ["make", "test"]
