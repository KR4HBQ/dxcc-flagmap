FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE requirements-publish.txt ./
COPY src ./src
RUN pip install --no-cache-dir --require-hashes -r requirements-publish.txt \
 && pip install --no-cache-dir --no-deps . \
 && useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin flagmap
# runs unprivileged (uid 1000): the mounted /out must be writable by it (or pass --user)
USER flagmap
# mount a config at /config/config.yaml and an output dir at /out
ENTRYPOINT ["dxcc-flagmap"]
CMD ["-c", "/config/config.yaml", "-o", "/out"]
