#!/bin/bash
# HarvestNet instance bootstrap. EC2 runs this once, as root, at first boot.
# It installs Docker and nothing else. It holds no secrets and no GitHub token:
# deploys arrive later through SSM Run Command (deploy/aws/setup.sh), which
# downloads a release bundle from the private S3 bucket.
set -euo pipefail
exec >>/var/log/harvestnet-bootstrap.log 2>&1
echo "harvestnet bootstrap start $(date -u +%FT%TZ)"

# The Elastic IP is attached a few seconds after launch; wait for internet access.
for _ in $(seq 1 120); do
  if curl -sS -o /dev/null --max-time 5 https://s3.amazonaws.com; then break; fi
  sleep 5
done

# 1 GB swap so a small instance survives the image build peak and about eleven containers.
if [ -z "$(swapon --show --noheadings)" ]; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=900 update -q
apt-get -o DPkg::Lock::Timeout=900 install -y -q docker.io docker-compose-v2 docker-buildx python3-boto3

# Container logs stay on the instance, capped at 30 MB per container (no CloudWatch cost).
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{"log-driver": "json-file", "log-opts": {"max-size": "10m", "max-file": "3"}}
JSON
systemctl enable docker
systemctl restart docker

mkdir -p /opt/harvestnet/releases /var/lib/harvestnet
chmod 700 /opt/harvestnet
touch /var/lib/harvestnet/bootstrap-done
echo "harvestnet bootstrap done $(date -u +%FT%TZ)"
