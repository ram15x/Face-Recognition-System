FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ATTENDANCE_DATA_DIR=/data \
    ATTENDANCE_MODELS_DIR=/models

RUN useradd --create-home --uid 10001 app \
 && mkdir /data /models \
 && chown app /data /models

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY faceattend ./faceattend

USER app
# Bake the two model files into the image so the container starts offline.
RUN python -m faceattend.models

VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

CMD ["python", "-m", "faceattend", "--host", "0.0.0.0", "--port", "8000"]
