FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.110.0" \
    "uvicorn[standard]>=0.29.0" \
    "websockets>=12.0" \
    "pydantic>=2.6.0"

# Copy only the drone package (relay + common) — no ML weights, no platform code
COPY drone/__init__.py ./drone/__init__.py
COPY drone/common/ ./drone/common/
COPY drone/relay/ ./drone/relay/

EXPOSE 8800

CMD ["uvicorn", "drone.relay.server:app", "--host", "0.0.0.0", "--port", "8800"]
