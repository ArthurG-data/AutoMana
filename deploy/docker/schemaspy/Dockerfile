# syntax=docker/dockerfile:1
FROM eclipse-temurin:17-jre

ARG SCHEMASPY_VERSION=6.2.4
ARG POSTGRES_JDBC_VERSION=42.7.4
ARG APP_UID=1000
ARG APP_GID=1000

ENV SCHEMASPY_DIR=/usr/local/lib/schemaspy \
    DRIVERS_DIR=/drivers

RUN apt-get update && apt-get install -y --no-install-recommends \
      graphviz \
      fontconfig \
      curl \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN mkdir -p ${SCHEMASPY_DIR} ${DRIVERS_DIR} \
 && curl -fsSL -o ${SCHEMASPY_DIR}/schemaspy-${SCHEMASPY_VERSION}.jar \
      https://github.com/schemaspy/schemaspy/releases/download/v${SCHEMASPY_VERSION}/schemaspy-${SCHEMASPY_VERSION}.jar \
 && curl -fsSL -o ${DRIVERS_DIR}/postgresql.jar \
      https://jdbc.postgresql.org/download/postgresql-${POSTGRES_JDBC_VERSION}.jar

RUN (getent group ${APP_GID} || groupadd -g ${APP_GID} appgrp) \
 && (getent passwd ${APP_UID} || useradd -m -u ${APP_UID} -g ${APP_GID} appuser) \
 && mkdir -p /app/docs/db-schema \
 && chown -R ${APP_UID}:${APP_GID} /app ${DRIVERS_DIR} ${SCHEMASPY_DIR}

USER ${APP_UID}:${APP_GID}
WORKDIR /app

ENTRYPOINT ["java", "-jar"]
CMD ["/usr/local/lib/schemaspy/schemaspy-6.2.4.jar"]
