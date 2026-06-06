FROM python:3.11-slim
WORKDIR /app

# Install backend dependencies first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the FastAPI app after dependencies are installed.
COPY app ./app

# The backend API listens on port 8000 inside the container.
EXPOSE 8000

# Start the technician workflow API.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
