# For more information, please refer to https://aka.ms/vscode-docker-python
FROM sk4la/volatility3

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1


WORKDIR /memdiff
RUN mkdir -p volatilitycache
RUN mkdir -p results
COPY memory-processing/memdiff.sh .

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
USER root
RUN chown -R unprivileged /memdiff
RUN chmod +x memdiff.sh

RUN mkdir -p /disk
RUN mkdir -p /memory

# RUN touch /disk/from
# RUN touch /disk/to

# RUN touch /memory/from
# RUN touch /memory/to

# USER appuser
USER unprivileged

# ENTRYPOINT [ "/usr/bin/dumb-init", "--", "volatility3" ]
ENTRYPOINT [ "/bin/sh", "memdiff.sh" ]
