FROM python:3.12-slim
WORKDIR /assurance
COPY pyproject.toml README.md LICENSE ./
COPY assurancegraph ./assurancegraph
COPY fixtures ./fixtures
RUN pip install --no-cache-dir . && useradd --uid 10001 assurance
USER 10001
ENTRYPOINT ["assurancegraph"]
