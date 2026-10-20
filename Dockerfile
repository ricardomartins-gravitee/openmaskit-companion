FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv
FROM python:3.12.15-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /build
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md LICENSE /build/
COPY src/ /build/src/
RUN uv sync --frozen --no-dev --no-editable --python /usr/local/bin/python
FROM python:3.12.15-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
LABEL org.opencontainers.image.source="https://github.com/ricardomartins-gravitee/openmaskit-companion" org.opencontainers.image.licenses="Apache-2.0"
COPY --from=build /opt/venv /opt/venv
COPY LICENSE /usr/share/doc/openmaskit-companion/LICENSE
ENV PATH=/opt/venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
USER 10001:10001
EXPOSE 9495
ENTRYPOINT ["openmaskit-companion"]
