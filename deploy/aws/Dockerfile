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
RUN pip install --no-cache-dir . ./agents
# The core is run from /app (python -m harvestnet_core.server); it reads its fixture from docs/contracts.
COPY harvestnet_core ./harvestnet_core
COPY docs/contracts/examples ./docs/contracts/examples
COPY core_fixtures ./core_fixtures
RUN useradd --uid 10001 --create-home harvestnet \
    && mkdir -p /app/runtime /app/budget /app/data \
    && chown harvestnet /app/runtime /app/budget /app/data
USER harvestnet
CMD ["python", "-m", "harvestnet_core.server"]
