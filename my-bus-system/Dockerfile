FROM node:20-bullseye AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Node deps for building frontend via npm run serve
COPY package*.json ./
RUN npm ci

# Python deps
COPY requirements.docker.txt ./
RUN pip3 install --no-cache-dir -r requirements.docker.txt

# App source
COPY . .

EXPOSE 8600

# npm run serve will: build frontend and start uvicorn with SSL paths under /ssl
CMD ["npm", "run", "serve"]
