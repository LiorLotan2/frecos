FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends make \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the test suite and the smoke benchmark. To reproduce the report's
# experiments and figures instead, override the command, e.g.:
#   docker run frecos make experiments
#   docker run frecos make figures
CMD ["make", "verify"]
