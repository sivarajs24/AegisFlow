# services/ingestion/Dockerfile - build from the repo root. The image carries
# ml/src/aegis_ml too, because online_features.py compiles definitions.py (one source).
FROM python:3.12-slim
WORKDIR /app
COPY services/ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY services/ingestion/src /app/services/ingestion/src
COPY ml/src /app/ml/src
ENV PYTHONPATH=/app/services/ingestion/src:/app/ml/src
EXPOSE 8001
HEALTHCHECK --interval=15s --retries=10 CMD python -c \
    "import urllib.request as u; u.urlopen('http://localhost:8001/health')"
CMD ["uvicorn", "ingestion.main:app", "--host", "0.0.0.0", "--port", "8001"]
