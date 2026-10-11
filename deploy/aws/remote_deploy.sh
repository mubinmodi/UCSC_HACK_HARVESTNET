#!/usr/bin/env bash
# Runs ON the instance, as root, through SSM Run Command (see deploy_commands in
# deploy/aws/setup.sh). Loads the secret into a 0600 env file, builds the one app
# image, and starts the stack. Prints no secret values.
#
#   remote_deploy.sh RELEASE_DIR SECRET_ID REGION RELEASE
set -euo pipefail

release_dir="$1" secret_id="$2" region="$3" release="$4"
state=/opt/harvestnet
env_file="$state/deploy.env"

exec 9>"$state/deploy.lock"
flock 9
cd "$release_dir"

echo "loading configuration from Secrets Manager"
( umask 077; python3 deploy/load_secrets.py --secret-id "$secret_id" --region "$region" --output "$env_file" )
chmod 600 "$env_file"

[ -f deploy/aws/frontends.caddy ] || printf 'handle /apps.txt {\n\trespond "Frontend apps: none" 200\n}\n' > deploy/aws/frontends.caddy
mkdir -p frontend-dist

echo "building image harvestnet-app:$release"
docker build --quiet --tag "harvestnet-app:$release" --file deploy/aws/Dockerfile . >/dev/null

export HARVESTNET_RELEASE="$release"
compose=(docker compose --project-name harvestnet --env-file "$env_file"
         -f compose.platform.yaml -f deploy/aws/compose.aws.yaml)
# config --quiet validates without printing interpolated secrets.
"${compose[@]}" config --quiet
"${compose[@]}" up --detach --no-build --remove-orphans --wait --wait-timeout 300

ln -sfn "$release_dir" "$state/current"
echo "$release" > "$state/current-release"

# Keep the three newest releases on disk and only the running image.
find "$state/releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -rn | tail -n +4 \
  | cut -d' ' -f2- | while IFS= read -r old; do rm -rf "$old"; done
docker images harvestnet-app --format '{{.Tag}}' | { grep -vxF "$release" || true; } | while IFS= read -r tag; do
  docker rmi "harvestnet-app:$tag" >/dev/null || true
done
docker image prune --force >/dev/null

"${compose[@]}" ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}'
echo "deployed release $release"
