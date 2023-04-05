# For more information, please refer to https://aka.ms/vscode-docker-python
FROM ubuntu:22.04

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    gcc \ 
    python3 \
    python3-pip
# python3-dfvfs 


# Install pip requirements
COPY backend/requirements.txt .

RUN pip3 install dfvfs==20220816

# CRIME TIME
# Copy in our patched pyvmdk with delta disk support, putting it in the same directory as `vmdk_file_io.py` 
COPY backend/pyvmdk_delta.py /usr/local/lib/python3.10/dist-packages/dfvfs/file_io
COPY backend/vmdk_file_io.py /usr/local/lib/python3.10/dist-packages/dfvfs/file_io


# Put config.py in the same relative location as outside the containers so it can be imported.
COPY config.py /

WORKDIR /backend


# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
# RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
# USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["python3", "vmdiff.py"]
