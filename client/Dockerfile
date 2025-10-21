# --- Frontend build stage (React + Vite)
FROM node:20-alpine AS frontend_builder
WORKDIR /frontend

# Install deps
COPY package*.json ./
RUN npm ci

# Build static assets
COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# --- Backend runtime stage (FastAPI)
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python deps
COPY requirements.docker.txt ./
RUN pip install --no-cache-dir -r requirements.docker.txt

# Copy backend source
COPY Backend ./Backend
COPY Server.py ./

# Copy built frontend to be served by FastAPI StaticFiles(directory="dist")
COPY --from=frontend_builder /frontend/dist ./dist
# 🔹 加上 public (例如 Logo.png, favicon)
COPY --from=frontend_builder /frontend/public ./public

EXPOSE 8700

CMD ["uvicorn", "Server:app", "--host", "0.0.0.0", "--port", "8700"]
