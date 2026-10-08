FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV GARI_DB=/data/gari.db PORT=8000
VOLUME /data
# GARI_SECRET must be provided at runtime (>= 32 random bytes)
CMD ["gunicorn","-w","3","-b","0.0.0.0:8000","--access-logfile","-","app:create_app()"]
