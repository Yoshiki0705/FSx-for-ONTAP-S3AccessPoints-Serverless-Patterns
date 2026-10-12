"""Test harness for the shared-vault lab scripts.

The harness never reaches AWS. Every run uses:

* a copy of the lab at ``<tmp>/repo/infrastructure/shared-backup-vault-lab`` with a
  fake repository-root ``Makefile`` beside it (the layout the scripts expect);
* ``PATH = tests/stubs : <per-test tools dir> : <pytest python dir> : <dir with only jq> : /usr/bin:/bin``.
  The per-test tools dir starts empty; ``add_tool`` puts fake ``node``, ``npm`` and
  the like in it and records their calls.
  The dir with only jq is a temporary directory holding one symlink. Homebrew keeps
  ``jq`` and the real ``aws`` in the same directory, so putting jq's own directory on
  PATH would expose the real CLI;
* a temporary ``HOME`` and a temporary working directory;
* an environment built from scratch (no ``AWS_*`` or ``LAB_*`` from the caller).

Scripts are started with ``/bin/bash`` (3.2 on macOS, 5.x on Ubuntu).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

LAB_SRC = Path(__file__).resolve().parents[1]
REPO_SRC = LAB_SRC.parents[1]
STUBS = Path(__file__).resolve().parent / "stubs"
# Fake node, npm, npx and make. Not on the default PATH: a test that needs them links
# them into its tools dir with ``Lab.use_external_stubs``.
EXTERNAL_STUBS = STUBS / "external"

# One value per kind, never shared between kinds, so a script that passes a name
# where an id belongs (or the reverse) is caught by the value assertion.
SENTINEL = SimpleNamespace(
    OWNER="111122223333",
    RECIPIENT="444455556666",
    FS="fs-0bbbbbbbbbbbbbbbb",
    SVM="svm-0aaaaaaaaaaaaaaaa",
    VOLUME="fsvol-0cccccccccccccccc",
    SUBNET="subnet-0dddddddddddddddd",
    RECIPIENT_SUBNET="subnet-0d0d0d0d0d0d0d0d0",
    SG="sg-0eeeeeeeeeeeeeeee",
    NAME_SVM="name_of_svm",
    NAME_VOLUME="name_of_volume",
    NAME_FS="name_of_fs",
)

BASE_LAB_ENV = {
    "LAB_OWNER_PROFILE": "lab-owner",
    "LAB_RECIPIENT_PROFILE": "lab-recipient",
    "LAB_OWNER_ACCOUNT_ID": SENTINEL.OWNER,
    "LAB_RECIPIENT_ACCOUNT_ID": SENTINEL.RECIPIENT,
    "LAB_PRIMARY_REGION": "ap-northeast-1",
    "LAB_OWNER_SUBNET_ID": SENTINEL.SUBNET,
    "LAB_RECIPIENT_SUBNET_ID": SENTINEL.RECIPIENT_SUBNET,
}


def arn(service: str, region: str, account: str, resource: str) -> str:
    """Build a complete ARN in the aws partition.

    Args:
        service: Service namespace (backup, fsx, ram, iam, kms).
        region: Region, or an empty string for global services.
        account: 12-digit account id.
        resource: Resource part.

    Returns:
        The ARN.
    """
    return f"arn:aws:{service}:{region}:{account}:{resource}"


def assert_called(
    calls: list[dict[str, Any]],
    service: str,
    subcommand: str,
    flags: dict[str, str | list[str]] | None = None,
    profile: str | None = None,
    region: str | None = None,
    times: int | None = None,
) -> dict[str, Any]:
    """Assert that a recorded call matches, including the flag VALUES.

    Checking only that a subcommand was called lets a script pass an id where a
    name is expected (or the reverse) when the model has no pattern for the member.
    Every expected flag must be present with exactly the expected value(s).

    Args:
        calls: Records from the stub call log.
        service: CLI service name.
        subcommand: CLI subcommand.
        flags: Expected flag -> value (or list of values).
        profile: Expected ``--profile`` value, when given.
        region: Expected ``--region`` value, when given.
        times: Expected number of matching calls, when given.

    Returns:
        The first matching call.

    Raises:
        AssertionError: When no call matches, or the count differs.
    """
    wanted = {k: ([v] if isinstance(v, str) else list(v)) for k, v in (flags or {}).items()}
    matches = []
    for call in calls:
        if call["service"] != service or call["subcommand"] != subcommand:
            continue
        if profile is not None and call.get("profile") != profile:
            continue
        if region is not None and call.get("region") != region:
            continue
        if any(call["args"].get(flag) != values for flag, values in wanted.items()):
            continue
        matches.append(call)
    if times is not None:
        assert len(matches) == times, f"{service} {subcommand}: expected {times} matching call(s), got {len(matches)}"
    else:
        assert matches, (
            f"no recorded call matches {service} {subcommand} flags={wanted} profile={profile} region={region}; "
            f"recorded: {[(c['service'], c['subcommand'], c['args']) for c in calls]}"
        )
    return matches[0]


def substitute_with_echo(text: str, call_literal: str) -> str:
    """Replace one real call with ``echo`` in a copy of a script.

    ``call_literal`` is the literal call site, for example
    ``aws_owner backup start-backup-job`` or ``run_external npx``. A script that
    only *prints* the call must make the success-path tests fail, so these
    substituted copies are run and the tests must go red.

    Args:
        text: Script text.
        call_literal: Literal call site to replace (every occurrence).

    Returns:
        The script with the call replaced by ``echo``.

    Raises:
        AssertionError: When the literal does not occur (the expectation claims a
            call the script does not make, or builds the call in a variable).
    """
    assert call_literal in text, f"call site not found as a literal: {call_literal!r}"
    return text.replace(call_literal, "echo")


@dataclass
class Result:
    """Outcome of one script run."""

    rc: int
    out: str
    err: str
    lab: Lab
    calls: list[dict[str, Any]] = field(default_factory=list)


class Lab:
    """A throwaway copy of the lab plus the means to run its scripts offline."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.repo = tmp / "repo"
        self.root = self.repo / "infrastructure" / "shared-backup-vault-lab"
        self.scripts = self.root / "scripts"
        self.home = tmp / "home"
        self.cwd = tmp / "cwd"
        self.jq_dir = tmp / "jqbin"
        self.tools_dir = tmp / "tools"
        self.external_log = tmp / "external-calls.log"
        self.external_jsonl = tmp / "external-calls.jsonl"
        self.chromium_path = tmp / "chromium" / "chrome"
        self.portal = self.repo / "solutions" / "amplify-portal"
        self.call_log = tmp / "aws-calls.jsonl"
        self.scenario_path = tmp / "scenario.json"
        self.sleep_log = tmp / "sleep.log"
        for directory in (self.home, self.cwd, self.jq_dir, self.tools_dir):
            directory.mkdir(parents=True)
        shutil.copytree(
            LAB_SRC,
            self.root,
            ignore=shutil.ignore_patterns("__pycache__", "tests", "docs", ".pytest_cache", "*.local.*"),
        )
        (self.repo / "Makefile").write_text(
            "portal-demo-user:\n\t@echo 'fake portal-demo-user $(ARGS)'\n", encoding="utf-8"
        )
        jq = shutil.which("jq")
        if jq is None:
            if os.environ.get("CI"):
                pytest.fail("jq is required on PATH in CI")
            pytest.skip("jq is not installed")
        (self.jq_dir / "jq").symlink_to(jq)
        self.write_scenario({})

    # -- environment ------------------------------------------------------

    def path(self) -> str:
        """PATH for lab runs: stubs, the pytest python, a dir with only jq, system dirs."""
        return os.pathsep.join(
            [str(STUBS), str(self.tools_dir), str(Path(sys.executable).parent), str(self.jq_dir), "/usr/bin", "/bin"]
        )

    def env(self, extra: dict[str, str | None] | None = None, lab_env: bool = True) -> dict[str, str]:
        """Build the environment for a run.

        Args:
            extra: Variables to add; a value of None removes the variable.
            lab_env: Include the minimal valid LAB_* variables.

        Returns:
            Complete environment mapping.
        """
        env = {
            "PATH": self.path(),
            "HOME": str(self.home),
            "TERM": "dumb",
            "PYTHONUTF8": "1",
            "STUB_SCENARIO": str(self.scenario_path),
            "STUB_CALL_LOG": str(self.call_log),
            "STUB_SLEEP_LOG": str(self.sleep_log),
            "STUB_EXTERNAL_LOG": str(self.external_log),
            "STUB_EXTERNAL_JSONL": str(self.external_jsonl),
            "STUB_DIR": str(EXTERNAL_STUBS),
            "STUB_CHROMIUM_PATH": str(self.chromium_path),
        }
        if lab_env:
            env.update(BASE_LAB_ENV)
        for key, value in (extra or {}).items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        return env

    # -- scenario and records ----------------------------------------------

    def write_scenario(self, scenario: dict[str, Any]) -> None:
        """Write the stub scenario (``"<service> <sub> [--flag] [!--flag]"`` -> response)."""
        self.scenario_path.write_text(json.dumps(scenario), encoding="utf-8")

    def calls(self) -> list[dict[str, Any]]:
        """Return the recorded stub calls in order."""
        if not self.call_log.is_file():
            return []
        return [json.loads(line) for line in self.call_log.read_text(encoding="utf-8").splitlines() if line]

    def sleeps(self) -> list[str]:
        """Return the arguments the stubbed sleep was called with."""
        if not self.sleep_log.is_file():
            return []
        return self.sleep_log.read_text(encoding="utf-8").splitlines()

    def records(self) -> list[dict[str, Any]]:
        """Return the lab-run.local.jsonl records written by the scripts."""
        path = self.root / "lab-run.local.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def add_tool(self, name: str, body: str = "") -> Path:
        """Put a fake external command (node, npm, ...) in the per-test tools dir.

        The fake appends ``<name> <arguments>`` to the external-call log, then runs
        ``body`` (shell text, for example ``echo v20.11.0``).

        Args:
            name: Command name.
            body: Shell lines to run after the call is logged.

        Returns:
            The path of the fake.
        """
        path = self.tools_dir / name
        path.write_text(
            f'#!/bin/sh\nprintf \'%s\\n\' "{name} $*" >>"$STUB_EXTERNAL_LOG"\n{body}\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def external_calls(self) -> list[str]:
        """Return the logged calls of the fake external commands (``name args``)."""
        if not self.external_log.is_file():
            return []
        return self.external_log.read_text(encoding="utf-8").splitlines()

    def use_external_stubs(self, *names: str) -> None:
        """Link the fake ``node``, ``npm``, ``npx`` or ``make`` into the tools dir.

        Args:
            *names: Command names; none means all four.
        """
        for name in names or ("node", "npm", "npx", "make"):
            link = self.tools_dir / name
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(EXTERNAL_STUBS / name)

    def external_records(self) -> list[dict[str, Any]]:
        """Return the JSON records (cwd and environment values) of the fake external commands."""
        if not self.external_jsonl.is_file():
            return []
        return [json.loads(line) for line in self.external_jsonl.read_text(encoding="utf-8").splitlines() if line]

    def make_portal(
        self,
        outputs: bool = True,
        node_modules: bool = True,
        chromium: bool = True,
        config: bool = True,
    ) -> Path:
        """Create a fake portal directory and the repository's ``portal_preflight.py``.

        ``scripts/sandbox.sh`` records its call and exits with ``$STUB_SANDBOX_RC``.

        Args:
            outputs: Create ``amplify_outputs.json`` (an existing sandbox).
            node_modules: Create ``node_modules/@playwright/test`` and ``.bin/ampx``.
            chromium: Create the file the fake ``node -e`` reports as the browser.
            config: Create ``amplify/portal-config.ts``.

        Returns:
            The portal directory.
        """
        portal = self.portal
        (portal / "scripts").mkdir(parents=True, exist_ok=True)
        (portal / "amplify").mkdir(parents=True, exist_ok=True)
        sandbox = portal / "scripts" / "sandbox.sh"
        sandbox.write_text('#!/bin/sh\nexec python3 "$STUB_DIR/sandbox_stub.py" "$@"\n', encoding="utf-8")
        sandbox.chmod(0o755)
        (portal / "amplify" / "portal-config.example.ts").write_text("// example\n", encoding="utf-8")
        if config:
            (portal / "amplify" / "portal-config.ts").write_text("// config\n", encoding="utf-8")
        if outputs:
            (portal / "amplify_outputs.json").write_text(
                json.dumps({"auth": {"user_pool_id": "us-east-1_StubPool", "aws_region": "ap-northeast-1"}}),
                encoding="utf-8",
            )
        if node_modules:
            (portal / "node_modules" / "@playwright" / "test").mkdir(parents=True, exist_ok=True)
            (portal / "node_modules" / ".bin").mkdir(parents=True, exist_ok=True)
            ampx = portal / "node_modules" / ".bin" / "ampx"
            ampx.write_text("#!/bin/sh\n", encoding="utf-8")
            ampx.chmod(0o755)
        if chromium:
            self.chromium_path.parent.mkdir(parents=True, exist_ok=True)
            self.chromium_path.write_text("chromium", encoding="utf-8")
        (self.repo / "scripts").mkdir(parents=True, exist_ok=True)
        (self.repo / "scripts" / "portal_preflight.py").write_text(
            "import os\nimport sys\n\nsys.path.insert(0, os.environ['STUB_DIR'])\n"
            "import preflight_stub\n\npreflight_stub.main(sys.argv[1:])\n",
            encoding="utf-8",
        )
        return portal

    def install_script(self, name: str, text: str) -> Path:
        """Write an executable script under ``scripts/`` of the lab copy.

        Args:
            name: File name.
            text: Script text.

        Returns:
            The path.
        """
        path = self.scripts / name
        path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
        return path

    # -- running -------------------------------------------------------------

    def _finish(self, proc: subprocess.CompletedProcess[str], allow_stub_failure: bool) -> Result:
        calls = self.calls()
        result = Result(proc.returncode, proc.stdout, proc.stderr, self, calls)
        if not allow_stub_failure:
            crashed = [c for c in calls if c.get("stub_rc") in (96, 97, 98)]
            if crashed:
                pytest.fail(f"the aws stub rejected a call: {crashed[0].get('reason') or crashed[0]['argv']}")
            for stream in (proc.stdout, proc.stderr):
                if "Traceback" in stream or any(line.startswith("stub:") for line in stream.splitlines()):
                    pytest.fail(f"the stub crashed or rejected a call:\n{stream}")
        return result

    def run(
        self,
        script: str,
        *args: str,
        env: dict[str, str | None] | None = None,
        lab_env: bool = True,
        stdin: str | None = None,
        timeout: int = 120,
        allow_stub_failure: bool = False,
    ) -> Result:
        """Run a lab script (a path under ``scripts/``) with /bin/bash.

        Args:
            script: Script path relative to ``scripts/``.
            *args: Script arguments.
            env: Environment overrides (None removes a variable).
            lab_env: Include the minimal valid LAB_* variables.
            stdin: Text for standard input.
            timeout: Seconds before the run is killed.
            allow_stub_failure: Do not fail the test on a stub rejection.

        Returns:
            The result, with the stub call records attached.
        """
        proc = subprocess.run(
            ["/bin/bash", str(self.scripts / script), *args],
            cwd=self.cwd,
            env=self.env(env, lab_env),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return self._finish(proc, allow_stub_failure)

    def bash(
        self,
        snippet: str,
        name: str = "02_driver.sh",
        env: dict[str, str | None] | None = None,
        lab_env: bool = True,
        library: bool = True,
        timeout: int = 120,
        allow_stub_failure: bool = False,
    ) -> Result:
        """Run a bash snippet that has sourced ``lib/common.sh``.

        ``$0`` is set to ``name`` so the library sees a script called 02_driver.sh
        (use ``01_driver.sh`` to get the preflight behaviour).

        Args:
            snippet: Bash code to run after sourcing.
            name: Value of ``$0``.
            env: Environment overrides.
            lab_env: Include the minimal valid LAB_* variables.
            library: Source common.sh first.
            timeout: Seconds before the run is killed.
            allow_stub_failure: Do not fail the test on a stub rejection.

        Returns:
            The result.
        """
        prelude = "set -euo pipefail\n"
        if library:
            prelude += f'. "{self.scripts}/lib/common.sh"\n'
        proc = subprocess.run(
            ["/bin/bash", "-c", prelude + snippet, name],
            cwd=self.cwd,
            env=self.env(env, lab_env),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return self._finish(proc, allow_stub_failure)

    def stub(self, *argv: str, env: dict[str, str | None] | None = None) -> subprocess.CompletedProcess[str]:
        """Run the stub directly (for its own negative controls).

        Args:
            *argv: Arguments after ``aws``.
            env: Environment overrides.

        Returns:
            The completed process (not checked for stub failures).
        """
        return subprocess.run(
            [sys.executable, str(STUBS / "aws_stub.py"), *argv],
            cwd=self.cwd,
            env=self.env(env),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
