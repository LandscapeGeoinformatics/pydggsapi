FROM python:3.12-slim
LABEL description.short="DGGS API"
LABEL description.long="OGC API for DGGS (Discretized Global Grid System) data management and processing."
LABEL maintainer="Francis Charette-Migneault <francis.charette-migneault@crim.ca>"
LABEL vendor="CRIM"
LABEL version="0.1.5"

ARG DGGRID_VERSION=8.42

# setup paths
ENV APP_DIR=/opt/local/src/pydggsapi
ENV APP_CONFIG_DIR=${APP_DIR}/config
WORKDIR ${APP_DIR}

# obtain dependency files
COPY pyproject.toml poetry.lock ${APP_DIR}/

# install utility dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gcc \
        g++ \
        make \
        cmake \
        gdal-bin \
        libgdal-dev \
        python3-gdal \
    # build DGGRID and install it
    && cd /tmp \
    && curl -L https://github.com/sahrk/DGGRID/archive/refs/tags/v${DGGRID_VERSION}.tar.gz | tar -zxf - \
    && mkdir -p DGGRID-${DGGRID_VERSION}/build \
    && cd DGGRID-${DGGRID_VERSION}/build \
    && cmake -D CMAKE_BUILD_TYPE=Release .. \
    && make -j $(nproc) \
    && cp src/apps/dggrid/dggrid /usr/local/bin/dggrid \
    && rm -rf /tmp/DGGRID-${DGGRID_VERSION} \
    # install project python packages
    && cd ${APP_DIR} \
    && pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-root --no-directory --no-cache --only main -v \
    # cleanup
    && rm -fr ~/.cache/ \
    && apt-get remove -y \
        curl \
        make \
        cmake \
        gcc \
        g++ \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# setup directory and config structure
# NOTE:
#   minimal TinyDB definition is not useful and MUST be overriden by volume mount of custom config
#   only provided to have the minimal application setup to start the API and obtain relevant error messages
RUN mkdir -p ${APP_CONFIG_DIR}

COPY dggs_api_config_example.json ${APP_CONFIG_DIR}/pydggsapi-config.json
ENV dggs_api_config=${APP_CONFIG_DIR}/pydggsapi-config.json
ENV DGGRID_PATH=/usr/local/bin/dggrid

# obtain dependency source files
COPY README.md LICENSE ${APP_DIR}/
COPY pydggsapi/ ${APP_DIR}/pydggsapi/

# install package (only) incrementally
RUN poetry install --only-root --no-cache

# command with sh to allow for environment variable expansion
CMD [ \
    "sh", "-c", \
    "uvicorn pydggsapi.api:app \
        --host ${PYDGGSAPI_HOST:-0.0.0.0} \
        --port ${PYDGGSAPI_PORT:-8000} \
        --workers ${PYDGGSAPI_WORKERS:-8} \
        --log-level ${PYDGGSAPI_LOG_LEVEL:-info} \
    " \
]
