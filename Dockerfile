FROM node:lts-alpine as frontend
WORKDIR /app
ENV PATH /app/node_modules/.bin:$PATH
COPY frontend ./
RUN yarn install --production
RUN yarn build --production


# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.8-slim


EXPOSE 5000

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install pip requirements
COPY server_requirements.txt .
RUN python -m pip install -r server_requirements.txt

WORKDIR /app
COPY --from=frontend /app/build /react-build/
COPY backend/ backend/
COPY server.py .
COPY config.py .


# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "server:app"]
