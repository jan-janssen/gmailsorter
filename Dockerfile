FROM condaforge/mambaforge:4.14.0-0
MAINTAINER Jan Janssen <jan.janssen@outlook.com>

# Install via conda
RUN mamba update --all --yes && \
    mamba install --yes gmailsorter && \
    mamba clean --all --force-pkgs-dirs --yes && \
    mamba list

# Setup crontab
ADD crontab /tmp/crontab
RUN apt-get update && \
    apt-get -y install cron && \
    crontab /tmp/crontab && \
    rm /tmp/crontab

# Set environment variables - these optional variables can be overwritten
ENV MAILSORT_ENV_CREDENTIALS_FILE='/tmp/credentials.json'
ENV MAILSORT_ENV_DATABASE_URL='sqlite:////tmp/email.db'
ENV MAILSORT_ENV_SECRET_KEY='e0f9eb0f0a16667771fa697ccbfaec952c410c6eaab54868'

ENTRYPOINT ["tini", "--"]
EXPOSE 8080
CMD printenv | grep "MAILSORT_ENV" >> /etc/environment && cron && cd /tmp && python -m gmailsorter.webapp