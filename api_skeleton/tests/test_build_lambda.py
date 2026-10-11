"""The Lambda zip holds the handler and every example, and works on its own."""

import json
import subprocess
import sys
import zipfile

from conftest import EVENTS, api_example_files
from harvestnet_api_skeleton.build_lambda import build


def test_zip_contains_the_package_and_every_example(tmp_path):
    out = build(tmp_path / "lambda.zip")
    names = set(zipfile.ZipFile(out).namelist())
    for module in ("__init__.py", "routes.py", "lambda_function.py"):
        assert f"harvestnet_api_skeleton/{module}" in names
    for path in api_example_files():
        assert f"harvestnet_api_skeleton/examples/public-api/{path.name}" in names
    assert not any("tests/" in n or "__pycache__" in n or n.endswith("build_lambda.py") for n in names)


def test_zip_runs_without_the_repo(tmp_path):
    out = build(tmp_path / "lambda.zip")
    script = (
        "import json, sys\n"
        "from harvestnet_api_skeleton.lambda_function import lambda_handler\n"
        "import harvestnet_api_skeleton.routes as r\n"
        "print(json.dumps({'source': r.examples_source(), 'result': lambda_handler(json.load(sys.stdin), None)}))\n"
    )
    # -I: isolated, so only the zip (not the source tree or the installed package) is importable.
    proc = subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(out)!r}); exec({script!r})"],
        input=(EVENTS / "get_health.json").read_text(),
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["source"] == "packaged"
    assert data["result"]["statusCode"] == 200
