"""The cross-lane tests never skip silently: Lane C's source defaults to the repository root."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class PlatformSource(unittest.TestCase):
    def test_lane_c_imports_without_the_environment_variable(self):
        env = {k: v for k, v in os.environ.items() if k != 'HARVESTNET_PLATFORM_SOURCE'}
        code = 'import platform_source, harvestnet_platform.approvals; print(platform_source.SOURCE)'
        # Run outside the repository root, so only the helper can put the platform on the path.
        paths = [str(HERE)] + [str(Path(p).resolve()) for p in env.get('PYTHONPATH', '').split(os.pathsep) if p]
        out = subprocess.run([sys.executable, '-c', code], cwd=HERE, env={**env, 'PYTHONPATH': os.pathsep.join(paths)}, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(Path(out.stdout.strip()), HERE.parent)


if __name__ == '__main__':
    unittest.main()
