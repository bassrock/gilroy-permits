FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY checker.py web.py main.py geocoder.py alerts.py ./

RUN mkdir -p /data

EXPOSE 5000

CMD ["python", "main.py"]
