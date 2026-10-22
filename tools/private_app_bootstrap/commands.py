"""Run argument-vector commands with secret-safe diagnostics."""

import json
import os
import subprocess
from pathlib import Path


class Commands:
    def __init__(self, config, journal):
        self.config = config
        self.bench = Path(config["bench_path"])
        self.runtime = journal.path.parent / (journal.path.stem + "-runtime")
        self.env = dict(os.environ)
        self.env["PATH"] = os.pathsep.join(
            [
                str(self.runtime / "bin"),
                str(self.bench / "env/bin"),
                self.env.get("PATH", ""),
            ]
        )
        self.env.update(
            {
                "CI": "Yes",
                "GIT_AUTHOR_NAME": config["publisher"],
                "GIT_COMMITTER_NAME": config["publisher"],
                "GIT_AUTHOR_EMAIL": config["email"],
                "GIT_COMMITTER_EMAIL": config["email"],
            }
        )
        self.secrets = [
            os.environ.get(config[key], "")
            for key in ("admin_password_env", "db_root_password_env")
        ]
        for key in ("admin_password_env", "db_root_password_env"):
            self.env.pop(config[key], None)
        self.env.pop("GH_REPO", None)

    def run(
        self, args, cwd=None, check=True, input_text=None, timeout=900, stream=False
    ):
        print(f"Running {args[0]} {args[1] if len(args) > 1 else ''}", flush=True)
        result = subprocess.run(
            [str(arg) for arg in args],
            cwd=cwd,
            env=self.env,
            input=input_text,
            text=True,
            capture_output=not stream,
            timeout=timeout,
        )
        if check and result.returncode:
            raise ValueError(
                self.redact(
                    f"Command failed ({result.returncode}): {result.stderr or result.stdout}"
                )
            )
        return result

    def json(self, args, cwd=None):
        return json.loads(self.run(args, cwd=cwd).stdout)

    def redact(self, text):
        for value in self.secrets:
            if value:
                text = text.replace(value, "<redacted>")
        return text

    def new_app(self):
        c = self.config
        inputs = [
            c["title"],
            c["description"],
            c["publisher"],
            c["email"],
            c["license"],
            "N",
            "main",
        ]
        print("Scaffolding the Frappe app with piped metadata.", flush=True)
        with subprocess.Popen(
            ["printf", "%s\n", *inputs], stdout=subprocess.PIPE, env=self.env
        ) as source:
            result = subprocess.run(
                ["bench", "new-app", c["app_name"]],
                stdin=source.stdout,
                cwd=self.bench,
                env=self.env,
                text=True,
                capture_output=True,
                timeout=900,
            )
            source.stdout.close()
            source.wait()
        if result.returncode:
            raise ValueError(
                self.redact(f"App scaffolding failed: {result.stderr or result.stdout}")
            )
