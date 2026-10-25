FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ARG CACHE_BUST=unknown
COPY test.py ap_lookup.py server.py ./

ENV AP_SERVER_PORT=8090 \
    LIBRESPEED_URL=http://192.168.110.54:8088

EXPOSE 8090

CMD ["python", "server.py"]
