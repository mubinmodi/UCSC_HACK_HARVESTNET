"""Build the Lambda deployment zip for the API skeleton (stdlib only).

    cd api_skeleton && uv run python -m harvestnet_api_skeleton.build_lambda
    # writes api_skeleton/dist/harvestnet-api-skeleton-lambda.zip

The zip holds the ``harvestnet_api_skeleton`` package (without this build script) and a
copy of every public API example at ``harvestnet_api_skeleton/examples/public-api/``, so the
function needs nothing else at run time.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
API_DIR = PACKAGE_DIR.parents[1]
REPO_EXAMPLES = API_DIR.parent / "docs" / "contracts" / "examples" / "public-api"
DEFAULT_OUT = API_DIR / "dist" / "harvestnet-api-skeleton-lambda.zip"
RUNTIME_MODULES = ("__init__.py", "routes.py", "lambda_function.py", "server.py")
_FIXED_TIME = (2026, 10, 11, 0, 0, 0)  # same bytes on every build


def build(out: str | Path = DEFAULT_OUT, examples: str | Path = REPO_EXAMPLES) -> Path:
    out, examples = Path(out), Path(examples)
    files = sorted(examples.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"no example files in {examples}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in RUNTIME_MODULES:
            _add(zf, f"harvestnet_api_skeleton/{name}", (PACKAGE_DIR / name).read_bytes())
        for path in files:
            _add(zf, f"harvestnet_api_skeleton/examples/public-api/{path.name}", path.read_bytes())
    return out


def _add(zf: zipfile.ZipFile, arcname: str, data: bytes) -> None:
    info = zipfile.ZipInfo(arcname, date_time=_FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, data)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    out = build(args.out)
    print(out)


if __name__ == "__main__":
    main()
