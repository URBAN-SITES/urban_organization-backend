"""Exercise deployment decisions using local Git repositories and fake Docker."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "update.sh"


class DeploymentTests(unittest.TestCase):
    def test_deploy_skip_and_failed_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("backend-resenha", "frontend-resenha"):
                repo = root / name
                repo.mkdir()
                self.git(repo, "init", "-b", "main")
                self.git(repo, "remote", "add", "origin", ".")
                (repo / "README").write_text("fixture")
                self.commit(repo)
            backend = root / "backend-resenha"
            infrastructure = backend / "deployment"
            (infrastructure / "deploy").mkdir(parents=True)
            (infrastructure / "compose.prod.yml").write_text("name: fixture\n")
            (infrastructure / "deploy" / "nginx.conf").write_text("fixture")
            shutil.copy(SCRIPT, infrastructure / "update.sh")
            self.commit(backend)
            binaries = root / "bin"
            binaries.mkdir()
            docker = binaries / "docker"
            docker.write_text(
                '#!/bin/bash\necho "$*" >> "$RESENHA_WORKSPACE/calls"\n'
                'if [[ ${FAIL_BUILD:-} == 1 && " $* " == *" build "* ]]; then exit 1; fi\n'
            )
            curl = binaries / "curl"
            curl.write_text("#!/bin/sh\nexit 0\n")
            for executable in (docker, curl):
                executable.chmod(0o755)
            environment = dict(os.environ, RESENHA_WORKSPACE=str(root))
            environment["PATH"] = str(binaries) + ":" + environment["PATH"]
            self.run_update(environment)
            state = (root / "deploy/current-revision").read_text()
            calls = (root / "calls").read_text()
            self.assertIn(" build", calls)
            self.assertIn(" up -d --wait", calls)
            self.run_update(environment)
            self.assertEqual((root / "calls").read_text(), calls)
            (root / "frontend-resenha/README").write_text("new main")
            self.commit(root / "frontend-resenha")
            result = self.run_update(dict(environment, FAIL_BUILD="1"), check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root / "deploy/current-revision").read_text(), state)
            new_calls = (root / "calls").read_text()[len(calls) :]
            self.assertIn(" build", new_calls)
            self.assertNotIn(" up ", new_calls)

    def git(self, repo, *arguments):
        subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def commit(self, repo):
        self.git(repo, "add", ".")
        self.git(
            repo,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "fixture",
        )

    def run_update(self, environment, check=True):
        return subprocess.run(
            ["bash", str(SCRIPT)],
            env=environment,
            check=check,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    unittest.main()
