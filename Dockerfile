# Use a Python 3.11 slim image as the base.
FROM python:3.11-slim

# Set environment variables to manage where large models are stored and to prevent Python buffering.
ENV PYTHONUNBUFFERED 1
# Configure SentenceTransformer and HuggingFace cache directories to point to the model volume.
ENV SENTENCE_TRANSFORMERS_HOME /app/models
ENV TRANSFORMERS_CACHE /app/models

# Set the working directory inside the container.
WORKDIR /app

# Copy the requirements file and install dependencies.
# This step is the most time-consuming due to PyTorch and model-related libraries.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container.
COPY main.py .

# Expose the port that Uvicorn will run on.
EXPOSE 8000

# Command to run the application with Uvicorn.
# We must use --host 0.0.0.0 so the server is accessible outside the container.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
