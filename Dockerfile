FROM python:3.10-slim

# git dibutuhkan oleh main.py untuk push ke GitHub
RUN apt-get update && apt-get install -y curl git nodejs npm \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g opencode-ai netlify-cli

WORKDIR /app
COPY requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

CMD ["python", "main.py"]