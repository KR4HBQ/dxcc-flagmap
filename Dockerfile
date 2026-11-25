FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
# mount a config at /config/config.yaml and an output dir at /out
ENTRYPOINT ["wavelog-flagmap"]
CMD ["-c", "/config/config.yaml", "-o", "/out"]
