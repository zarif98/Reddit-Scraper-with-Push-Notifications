# Use the official Python image from the Docker Hub
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Set Python to use UTF-8 encoding for handling Unicode characters
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Copy the requirements file to the working directory
COPY requirements.txt .

# Install the required packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code to the working directory
COPY . .

# Command to run the application
CMD ["python", "bot.py"]
