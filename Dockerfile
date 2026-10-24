FROM mcr.microsoft.com/playwright/python:v1.55.0-noble
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY metro ./metro
ENV PYTHONUNBUFFERED=1 METRO_DB=/data/metro.sqlite
RUN mkdir -p /data
# Cloud Run Jobs ejecuta este proceso hasta finalizar; no necesita servidor HTTP.
ENTRYPOINT ["python", "-m", "metro"]
CMD ["scrape"]
