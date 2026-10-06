# ==============================================================================
# Multi-stage Unified Dockerfile (Root)
# Builds both the frontend and backend for production deployment in a single image.
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build the React + Vite frontend
# ------------------------------------------------------------------------------
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Build the FastAPI backend runtime
# ------------------------------------------------------------------------------
FROM python:3.13-slim AS production

WORKDIR /app

# Set Python environment flags
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install backend dependencies
COPY backend/pyproject.toml .
RUN pip install --no-cache-dir .

# Copy backend source code and migrations
COPY backend/app ./app
COPY backend/alembic.ini .
COPY backend/alembic ./alembic

# Create uploads directory
RUN mkdir -p /app/uploads

# Copy built frontend assets from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend_dist

# Expose backend port
EXPOSE 8000

# Start backend application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
