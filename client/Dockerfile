FROM node:20-alpine AS frontend_builder
WORKDIR /frontend
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.docker.txt ./
RUN pip install --no-cache-dir -r requirements.docker.txt
COPY Backend ./Backend
COPY Server.py ./
COPY --from=frontend_builder /frontend/dist ./dist
COPY --from=frontend_builder /frontend/public ./public
EXPOSE 8700