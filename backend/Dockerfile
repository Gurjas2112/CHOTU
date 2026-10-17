# CHOTU fleet backend - small runtime image (~70 MB)
FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY chotu_api ./chotu_api
COPY sample_data ./sample_data
COPY migrations ./migrations
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["uvicorn", "chotu_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
