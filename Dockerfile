FROM python:3.10-slim

# Install Node.js & OpenCode CLI
RUN apt-get update && apt-get install -y curl nodejs npm
RUN npm install -g opencode-ai netlify-cli

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

CMD ["python", "main.py"]