# Use an official Python runtime as a parent image
FROM python:3.11-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port Uvicorn will run on
EXPOSE 8000

# Set environment variable for the API Key (DO NOT hardcode sensitive keys here in production!)
# In production, use Kubernetes Secrets, Docker Secrets, or your cloud provider's secret management.
# For demo, you can pass it via -e GEMINI_API_KEY=your_key when running docker run.
# ENV GEMINI_API_KEY="YOUR_GEMINI_API_KEY" # Uncomment for demo if you want to bake it in for testing only

# Command to run the application
# Use 0.0.0.0 to bind to all available network interfaces
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]