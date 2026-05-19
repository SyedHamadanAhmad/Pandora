FROM python:3.11-slim

WORKDIR /app

COPY pandora_shared /app/pandora_shared
RUN pip install --no-cache-dir -e /app/pandora_shared

COPY workers/stub/requirements.txt /tmp/stub-requirements.txt
RUN pip install --no-cache-dir -r /tmp/stub-requirements.txt

COPY workers/stub/pandora_stub /app/pandora_stub

ENV PYTHONPATH=/app

CMD ["python", "-m", "pandora_stub.downstream_worker"]
