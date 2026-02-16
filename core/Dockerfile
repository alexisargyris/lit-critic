FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY contracts /app/contracts
COPY core /app/core
COPY server /app/server

EXPOSE 8080

CMD ["uvicorn", "core.api:app", "--host", "0.0.0.0", "--port", "8080"]
