FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# FastAPI will run on the port defined by the PORT environment variable
# If not defined, it defaults to 8000 in main.py
CMD ["python", "main.py"]
