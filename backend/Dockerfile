# Use Python 3.13 as the base image.
# Your project requires Python >= 3.11.
FROM python:3.13-slim

# All commands after this will run from /app
# inside the Docker image/container.
WORKDIR /app

# Copy the project configuration into the image.
COPY pyproject.toml .

# Install the dependencies defined in pyproject.toml.
RUN pip install --no-cache-dir .

# Copy the actual application source code.
COPY app ./app

# Copy Alembic files because we will need them for database migrations.
COPY alembic.ini .
COPY alembic ./alembic

# Tell Docker that the application listens on port 8000.
EXPOSE 8000

# Start the FastAPI application.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]