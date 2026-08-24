FROM python:3.12-slim

WORKDIR /app

# .pyc file -> x
ENV PYTHONDONTWRTIEBYCODE=1

# print python logs immediately
ENV PYTHONBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

