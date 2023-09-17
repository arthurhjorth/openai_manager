# Use an official Python runtime as a parent image
FROM python:3.11.3

# Set the working directory in the container to /app
WORKDIR /app

RUN apt-get update && apt-get install -y netcat && apt-get install -y --no-install-recommends gcc

# Add the current directory contents into the container at /app
ADD . /app

# Install any needed packages specified in requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

# Make port 5001 available to the world outside this container
EXPOSE 5001

# Run app.py when the container launches
# CMD ["python", "-u", "app.py"]
CMD ["gunicorn", "-w", "8", "--bind", "0.0.0.0:8000", "app:app"]
