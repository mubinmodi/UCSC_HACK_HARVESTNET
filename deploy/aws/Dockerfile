# One image for every HarvestNet service on the AWS instance: the Lane C platform
# (organization hosts, systems, approvals), the Lane B agents package, and the
# Lane A core API. Built on the instance by deploy/aws/remote_deploy.sh.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements-agntcy.txt ./
COPY harvestnet_platform ./harvestnet_platform
COPY agents/pyproject.toml ./agents/pyproject.toml
COPY agents/src ./agents/src
# The organization hosts register in the AGNTCY Directory (deploy/aws/compose.directory.yaml)
# with the Directory SDK only, at the version pinned in requirements-agntcy.txt. The heavier
# App SDK host (compose.agntcy.yaml) is not installed here. The agents `claude` extra adds the
# anthropic SDK for the core's voice-intake extractor (#22); it only calls out when a key and a cap are set.
RUN pip install --no-cache-dir . "./agents[claude]" "$(grep -E '^agntcy-dir==' requirements-agntcy.txt)"
# INSTALL_AGNTCY_APP_SDK=1 adds the App SDK, for HARVESTNET_ORG_HOST=harvestnet_platform.agntcy_server
# (remote_deploy.sh passes it when the secret chooses the native host).
ARG INSTALL_AGNTCY_APP_SDK=0
RUN if [ "$INSTALL_AGNTCY_APP_SDK" = "1" ]; then pip install --no-cache-dir -r requirements-agntcy.txt; fi
# The core is run from /app (python -m harvestnet_core.server); it reads its fixture from docs/contracts.
COPY harvestnet_core ./harvestnet_core
COPY docs/contracts/examples ./docs/contracts/examples
COPY core_fixtures ./core_fixtures
RUN useradd --uid 10001 --create-home harvestnet \
    && mkdir -p /app/runtime /app/budget /app/data \
    && chown harvestnet /app/runtime /app/budget /app/data
USER harvestnet
CMD ["python", "-m", "harvestnet_core.server"]
