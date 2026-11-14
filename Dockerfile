FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY retailpulse retailpulse
COPY sql sql
COPY tableau tableau
CMD ["python", "-m", "retailpulse"]
