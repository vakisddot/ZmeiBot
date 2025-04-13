# Use an official lightweight Python image.
FROM python:3.9-slim

# Set environment variables to prevent Python from buffering stdout/stderr.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container.
WORKDIR /app

# (Optional) If you have a requirements file at the project root or in src,
# copy it first to leverage Docker cache when installing dependencies.
# Adjust the file path if your requirements file is located elsewhere.
COPY requirements.txt .

# Install dependencies. If you don’t have a requirements.txt, either create one
# or add the necessary pip install commands here.
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code.
COPY . .

# (Optional) Expose a port if the bot is serving a web hook or similar.
# EXPOSE 8000

# Set the default command to run your bot.
# Adjust the command if your startup script is different.
CMD ["python", "src/main.py"]