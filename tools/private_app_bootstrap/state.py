"""Atomic, private bootstrap journals guarded by a per-bench lock."""

import copy
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


class Journal:
    def __init__(self, config):
        self.config = copy.deepcopy(config)
        bench = Path(config["bench_path"])
        self.directory = bench.parent / ".frappe-bootstrap"
        self.path = self.directory / f"{bench.name}-{config['app_name']}.json"
        self.lock_path = self.directory / f"{bench.name}.lock"
        self.data = {
            "schema_version": 1,
            "config": copy.deepcopy(config),
            "completed": [],
            "current": None,
            "resources": {},
            "files": {},
        }
        self._locked = False

    @contextmanager
    def acquire(self, resume=False):
        if self.directory.is_symlink():
            raise ValueError("Bootstrap registry must not be a symlink.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        descriptor = os.open(
            self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600
        )
        try:
            os.fchmod(descriptor, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("Another bootstrap owns this bench lock.") from error
            self._locked = True
            self.load(resume)
            yield self
        finally:
            self._locked = False
            os.close(descriptor)

    def load(self, resume):
        if self.path.is_symlink():
            raise ValueError("Bootstrap journal must not be a symlink.")
        if self.path.exists():
            if not resume:
                raise ValueError("Bootstrap journal already exists; use --resume.")
            loaded = json.loads(self.path.read_text())
            if not isinstance(loaded, dict) or loaded.get("schema_version") != 1:
                raise ValueError("Unsupported bootstrap journal schema.")
            if loaded.get("config") != self.config:
                raise ValueError(
                    "Resume configuration differs from the recorded inputs."
                )
            if not isinstance(loaded.get("completed"), list) or not all(
                isinstance(phase, str) for phase in loaded["completed"]
            ):
                raise ValueError("Invalid completed phases in bootstrap journal.")
            if loaded.get("current") is not None and not isinstance(
                loaded["current"], str
            ):
                raise ValueError("Invalid current phase in bootstrap journal.")
            if not isinstance(loaded.get("resources"), dict) or not isinstance(
                loaded.get("files"), dict
            ):
                raise ValueError("Invalid bootstrap journal resources or files.")
            self.data = loaded
        elif resume:
            raise ValueError("Cannot resume: bootstrap journal does not exist.")
        else:
            self.save()

    def save(self):
        if not self._locked:
            raise ValueError("Acquire the bootstrap journal lock before saving.")
        if self.path.is_symlink():
            raise ValueError("Bootstrap journal must not be a symlink.")
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.directory
        )
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(self.data, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def start(self, phase):
        self.data["current"] = phase
        self.save()

    def complete(self, phase):
        if phase not in self.data["completed"]:
            self.data["completed"].append(phase)
        self.data["current"] = None
        self.save()

    def done(self, phase):
        return phase in self.data["completed"]
