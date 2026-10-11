#!/usr/bin/env python3
"""Offline stand-in for the ``aws`` CLI, used only by the lab tests.

It sits first on PATH (``tests/stubs/aws`` is a three-line wrapper that runs this
file) so a lab script can never reach a real AWS endpoint. For every call it:

1. validates the argument shape against the botocore service model
   (exit 97): subcommand, flag names, required members, enum values, structure
   keys, string ``pattern`` / length limits, and ``^arn:`` for every member whose
   name ends in ``Arn`` / ``ARN``. ``--cli-input-json`` and
   ``--generate-cli-skeleton`` are refused because they hide the arguments from
   the guards and tests. ``cloudformation deploy`` and ``lambda invoke`` are
   AWS CLI customizations that the model does not describe; their flags are a
   hand-written table below;
2. requires ``--output json`` (exit 98);
3. records the call (argv, parsed flags, profile, Region, environment hints) as
   one JSON line in ``$STUB_CALL_LOG``;
4. answers from the scenario file ``$STUB_SCENARIO`` (JSON: ``"<service>
   <subcommand> [--flag] [!--flag]"`` -> ``{"body", "rc", "stderr"}`` or a list of
   those, returned in order with the last one repeated). A call with no scenario
   entry exits 99 with ``UNSTUBBED call: <key>`` (default deny).

What this does NOT prove: that AWS accepts the call (permissions, service-side
validation, CLI-level differences in flag names). The shape check is only as
good as the botocore version pinned in requirements-dev.txt.

Messages that start with ``stub:`` mean the stub rejected or crashed; the test
harness turns them into test failures.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any

REJECT = 97
BAD_OUTPUT = 98
UNSTUBBED = 99
CRASH = 96

VERSION_LINE = "aws-cli/2.99.0 (stub)"

# Global options accepted anywhere on the command line.
GLOBAL_VALUE_FLAGS = {"--profile", "--region", "--output", "--query", "--cli-binary-format"}
GLOBAL_BOOL_FLAGS = {"--no-cli-pager"}

# Options the CLI adds to paginated operations.
PAGINATION_VALUE_FLAGS = {"--max-items", "--starting-token", "--page-size"}
PAGINATION_BOOL_FLAGS = {"--no-paginate"}

REFUSED_FLAGS = {"--cli-input-json", "--cli-input-yaml", "--generate-cli-skeleton"}

# CLI service name -> botocore service name where they differ.
SERVICE_ALIASES = {"s3api": "s3", "configservice": "config"}

# AWS CLI customizations that are not API operations. Hand-written flag tables:
# name -> (arity, enum). arity: bool, one, many.
CUSTOM_COMMANDS: dict[tuple[str, str], dict[str, Any]] = {
    ("cloudformation", "deploy"): {
        "flags": {
            "--template-file": ("one", None),
            "--stack-name": ("one", None),
            "--s3-bucket": ("one", None),
            "--s3-prefix": ("one", None),
            "--force-upload": ("bool", None),
            "--kms-key-id": ("one", None),
            "--parameter-overrides": ("many", None),
            "--capabilities": (
                "many",
                {"CAPABILITY_IAM", "CAPABILITY_NAMED_IAM", "CAPABILITY_AUTO_EXPAND"},
            ),
            "--no-execute-changeset": ("bool", None),
            "--disable-rollback": ("bool", None),
            "--no-disable-rollback": ("bool", None),
            "--role-arn": ("one", None),
            "--notification-arns": ("many", None),
            "--fail-on-empty-changeset": ("bool", None),
            "--no-fail-on-empty-changeset": ("bool", None),
            "--tags": ("many", None),
        },
        "required": ["--template-file", "--stack-name"],
        "positionals": 0,
    },
    ("lambda", "invoke"): {
        "flags": {
            "--function-name": ("one", None),
            "--invocation-type": ("one", {"Event", "RequestResponse", "DryRun"}),
            "--log-type": ("one", {"None", "Tail"}),
            "--client-context": ("one", None),
            "--payload": ("one", None),
            "--qualifier": ("one", None),
        },
        "required": ["--function-name"],
        "positionals": 1,
    },
}

# Subcommands that exist in the CLI but not in the API model (waiters and friends).
UNMODELED_NAMES = {"deploy", "package", "wait", "help", "invoke"}


class Reject(Exception):
    """A call the stub refuses (exit 97)."""


def die(code: int, message: str) -> None:
    """Print a stub message to stderr and exit.

    Args:
        code: Exit code.
        message: Text after the ``stub:`` marker (or a bare line for 99).
    """
    sys.stderr.write(message + "\n")
    sys.exit(code)


# --------------------------------------------------------------------------
# Command-line parsing
# --------------------------------------------------------------------------


def split_options(argv: list[str]) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """Split argv into leading words and (flag, following tokens) groups.

    Global options (``--profile``, ``--region``, ``--output``, ``--query``,
    ``--cli-binary-format``, ``--no-cli-pager``) are taken out first, wherever they
    are, because the lab wrappers put them before the service name. A global value
    option consumes exactly one token.

    Args:
        argv: Arguments after ``aws``.

    Returns:
        The non-option words that precede the first remaining option (service and
        subcommand), and one (flag, tokens) pair per option; ``tokens`` runs up
        to the next token that starts with ``--``. Global options come first.
    """
    glob: list[tuple[str, list[str]]] = []
    rest: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        name, eq, value = token.partition("=") if token.startswith("--") else (token, "", "")
        if name in GLOBAL_VALUE_FLAGS:
            if eq:
                glob.append((name, [value]))
                index += 1
            else:
                glob.append((name, argv[index + 1 : index + 2]))
                index += 2
        elif name in GLOBAL_BOOL_FLAGS:
            glob.append((name, []))
            index += 1
        else:
            rest.append(token)
            index += 1
    words: list[str] = []
    groups: list[tuple[str, list[str]]] = []
    for token in rest:
        if token.startswith("--") and len(token) > 2:
            if "=" in token:
                name, _, value = token.partition("=")
                groups.append((name, [value]))
            else:
                groups.append((token, []))
        elif groups:
            groups[-1][1].append(token)
        else:
            words.append(token)
    return words, glob + groups


def split_top(text: str, sep: str = ",") -> list[str]:
    """Split on ``sep`` outside brackets, braces and quotes.

    Args:
        text: Shorthand text.
        sep: Separator character.

    Returns:
        Parts in order.
    """
    parts: list[str] = []
    depth = 0
    quote = ""
    current = ""
    for ch in text:
        if quote:
            current += ch
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            current += ch
        elif ch in "[{":
            depth += 1
            current += ch
        elif ch in "]}":
            depth -= 1
            current += ch
        elif ch == sep and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return parts


def parse_shorthand(text: str) -> dict[str, str]:
    """Parse ``Key=Value,Key2=V1,V2`` shorthand into a dict of strings.

    Args:
        text: Shorthand text.

    Returns:
        Mapping of key to the raw value text.

    Raises:
        Reject: When the text is not shorthand.
    """
    out: dict[str, str] = {}
    last = ""
    for part in split_top(text):
        match = re.match(r"^([A-Za-z0-9_.:/-]+)=(.*)$", part, re.S)
        if match:
            last = match.group(1)
            out[last] = match.group(2)
        elif last:
            out[last] += "," + part
        else:
            raise Reject(f"BAD SHORTHAND {text!r}")
    return out


# --------------------------------------------------------------------------
# Model validation
# --------------------------------------------------------------------------


def check_string(shape: Any, value: str, member: str, path: str) -> None:
    """Validate a string against enum, pattern, length and the Arn rule.

    Args:
        shape: botocore string shape.
        value: Candidate value.
        member: Name of the member that carries it (decides the Arn rule).
        path: Location text for messages.

    Raises:
        Reject: When any rule fails.
    """
    enum = list(getattr(shape, "enum", None) or [])
    if enum and value not in enum:
        raise Reject(f"BAD ENUM {path}={value!r} not in {enum}")
    meta = shape.metadata
    if "min" in meta and len(value) < int(meta["min"]):
        raise Reject(f"TOO SHORT {path}={value!r} (min {meta['min']})")
    if "max" in meta and len(value) > int(meta["max"]):
        raise Reject(f"TOO LONG {path}={value!r} (max {meta['max']})")
    pattern = meta.get("pattern")
    if pattern:
        try:
            matched = re.search(pattern, value) is not None
        except re.error:
            matched = True  # a pattern Python cannot compile is not enforced
        if not matched:
            raise Reject(f"PATTERN {path}={value!r} does not match {pattern}")
    if member.lower().endswith(("arn", "arns")) and not value.startswith("arn:"):
        raise Reject(f"NOT AN ARN {path}={value!r}")


def coerce_json(text: str) -> Any:
    """Parse a JSON argument value, or return None when it is not JSON.

    Args:
        text: Argument text.

    Returns:
        The parsed object/array, or None.
    """
    stripped = text.strip()
    if stripped[:1] in ("{", "["):
        try:
            return json.loads(stripped)
        except ValueError:
            return None
    return None


def validate(shape: Any, value: Any, member: str, path: str) -> None:
    """Validate a parsed value against a botocore shape, recursively.

    Args:
        shape: botocore shape.
        value: Parsed value (str from the command line or JSON types).
        member: Name of the enclosing member.
        path: Location text for messages.

    Raises:
        Reject: When the value does not fit the shape.
    """
    kind = shape.type_name
    if kind == "structure":
        if isinstance(value, str):
            parsed = coerce_json(value)
            if parsed is None:
                inner = value.strip()
                if inner.startswith("{") and inner.endswith("}"):
                    inner = inner[1:-1]
                parsed = parse_shorthand(inner)
            value = parsed
        if not isinstance(value, dict):
            raise Reject(f"NOT A STRUCTURE {path}")
        unknown = sorted(set(value) - set(shape.members))
        if unknown:
            raise Reject(f"UNKNOWN KEY {path}: {unknown}")
        missing = sorted(set(shape.required_members) - set(value))
        if missing:
            raise Reject(f"MISSING REQUIRED KEY {path}: {missing}")
        for key, sub in value.items():
            validate(shape.members[key], sub, key, f"{path}.{key}")
    elif kind == "list":
        if isinstance(value, str):
            parsed = coerce_json(value)
            if parsed is None:
                inner = value.strip()
                if inner.startswith("[") and inner.endswith("]"):
                    inner = inner[1:-1]
                parsed = split_top(inner)
            value = parsed
        if not isinstance(value, list):
            raise Reject(f"NOT A LIST {path}")
        for index, sub in enumerate(value):
            validate(shape.member, sub, member, f"{path}[{index}]")
    elif kind == "map":
        if isinstance(value, str):
            parsed = coerce_json(value)
            value = parsed if parsed is not None else parse_shorthand(value)
        if not isinstance(value, dict):
            raise Reject(f"NOT A MAP {path}")
        for key, sub in value.items():
            validate(shape.key, key, member, f"{path}.<key>")
            validate(shape.value, sub, member, f"{path}.{key}")
    elif kind == "string":
        if not isinstance(value, str):
            raise Reject(f"NOT A STRING {path}={value!r}")
        check_string(shape, value, member, path)
    elif kind in ("integer", "long"):
        if isinstance(value, bool) or not (
            isinstance(value, int) or (isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value))
        ):
            raise Reject(f"NOT AN INTEGER {path}={value!r}")
        number = int(value)
        meta = shape.metadata
        if "min" in meta and number < int(meta["min"]):
            raise Reject(f"TOO SMALL {path}={number} (min {meta['min']})")
        if "max" in meta and number > int(meta["max"]):
            raise Reject(f"TOO LARGE {path}={number} (max {meta['max']})")
    elif kind in ("double", "float"):
        try:
            float(value)
        except (TypeError, ValueError):
            raise Reject(f"NOT A NUMBER {path}={value!r}") from None
    elif kind == "boolean":
        if not (isinstance(value, bool) or value in ("true", "false")):
            raise Reject(f"NOT A BOOLEAN {path}={value!r}")
    # timestamp and blob: any text is accepted


def arity_of(shape: Any) -> str:
    """Return how many command-line tokens a member consumes.

    Args:
        shape: botocore member shape.

    Returns:
        ``bool`` (none), ``many`` (a list takes every following token) or ``one``.
    """
    if shape.type_name == "boolean":
        return "bool"
    if shape.type_name == "list":
        return "many"
    return "one"


def validate_modeled(
    service: str, sub: str, groups: list[tuple[str, list[str]]]
) -> tuple[dict[str, list[str]], list[str]]:
    """Validate a call against the botocore model.

    Args:
        service: CLI service name.
        sub: CLI subcommand.
        groups: (flag, tokens) pairs from :func:`split_options`.

    Returns:
        Parsed non-global flags (name -> values) and positional leftovers.

    Raises:
        Reject: When the call does not fit the model.
    """
    import botocore.session
    from botocore import xform_name
    from botocore.exceptions import DataNotFoundError, UnknownServiceError

    # Reading the service model needs no profile, and a profile named in the
    # environment (the lab sets AWS_PROFILE for portal children) would make botocore
    # look for a config file that does not exist here. The environment was recorded
    # before this point.
    for name in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE"):
        os.environ.pop(name, None)
    os.environ["AWS_CONFIG_FILE"] = os.devnull
    os.environ["AWS_SHARED_CREDENTIALS_FILE"] = os.devnull
    session = botocore.session.get_session()
    model_name = SERVICE_ALIASES.get(service, service)
    try:
        model = session.get_service_model(model_name)
    except (UnknownServiceError, DataNotFoundError):
        raise Reject(f"UNKNOWN SERVICE {service}") from None
    operations = {xform_name(name, "-"): name for name in model.operation_names}
    if sub not in operations:
        if sub in UNMODELED_NAMES:
            raise Reject(f"UNMODELED SUBCOMMAND {service} {sub}")
        raise Reject(f"UNKNOWN SUBCOMMAND {service} {sub}")
    operation = model.operation_model(operations[sub])
    input_shape = operation.input_shape
    members = dict(input_shape.members) if input_shape is not None else {}
    required = list(input_shape.required_members) if input_shape is not None else []
    flag_to_member = {"--" + xform_name(m, "-"): m for m in members}
    pageable = False
    try:
        pageable = operations[sub] in session.get_paginator_model(model_name)._paginator_config
    except DataNotFoundError:
        pageable = False

    parsed: dict[str, list[str]] = {}
    positional: list[str] = []
    for flag, tokens in groups:
        if flag in REFUSED_FLAGS:
            raise Reject(f"REFUSED FLAG {flag} (hides the arguments)")
        if flag in GLOBAL_VALUE_FLAGS:
            continue
        if flag in GLOBAL_BOOL_FLAGS:
            positional.extend(tokens)
            continue
        if pageable and flag in PAGINATION_VALUE_FLAGS:
            positional.extend(tokens[1:])
            continue
        if pageable and flag in PAGINATION_BOOL_FLAGS:
            positional.extend(tokens)
            continue
        negated = False
        member = flag_to_member.get(flag)
        if member is None and flag.startswith("--no-"):
            candidate = flag_to_member.get("--" + flag[5:])
            if candidate is not None and members[candidate].type_name == "boolean":
                member = candidate
                negated = True
        if member is None:
            raise Reject(f"UNKNOWN FLAG {flag} ({service} {sub})")
        shape = members[member]
        mode = arity_of(shape)
        if mode == "bool":
            values: list[str] = []
            positional.extend(tokens)
        elif mode == "many":
            values = list(tokens)
        else:
            values = tokens[:1]
            positional.extend(tokens[1:])
        if mode != "bool" and not values:
            raise Reject(f"MISSING VALUE {flag}")
        if negated:
            parsed[flag] = []
            continue
        if mode == "many":
            if len(values) == 1 and coerce_json(values[0]) is not None:
                validate(shape, values[0], member, flag)
            else:
                validate(shape, values, member, flag)
        elif mode == "one":
            validate(shape, values[0], member, flag)
        parsed[flag] = values
    if positional:
        raise Reject(f"UNEXPECTED POSITIONAL ARGUMENT(S) {positional} ({service} {sub})")
    present = {m for f, m in flag_to_member.items() if f in parsed}
    missing = sorted("--" + xform_name(m, "-") for m in required if m not in present)
    if missing:
        raise Reject(f"MISSING REQUIRED {missing}")
    return parsed, positional


def validate_custom(
    service: str, sub: str, groups: list[tuple[str, list[str]]]
) -> tuple[dict[str, list[str]], list[str]]:
    """Validate an AWS CLI customization against the hand-written flag table.

    Args:
        service: CLI service name.
        sub: CLI subcommand.
        groups: (flag, tokens) pairs.

    Returns:
        Parsed flags and positional leftovers.

    Raises:
        Reject: On an unknown flag, a missing required flag or a bad enum value.
    """
    spec = CUSTOM_COMMANDS[(service, sub)]
    table = spec["flags"]
    parsed: dict[str, list[str]] = {}
    positional: list[str] = []
    for flag, tokens in groups:
        if flag in REFUSED_FLAGS:
            raise Reject(f"REFUSED FLAG {flag} (hides the arguments)")
        if flag in GLOBAL_VALUE_FLAGS or flag == "--no-cli-pager":
            if flag in GLOBAL_BOOL_FLAGS:
                positional.extend(tokens)
            continue
        if flag not in table:
            raise Reject(f"UNKNOWN FLAG {flag} ({service} {sub})")
        arity, enum = table[flag]
        if arity == "bool":
            values: list[str] = []
            positional.extend(tokens)
        elif arity == "many":
            values = list(tokens)
        else:
            values = tokens[:1]
            positional.extend(tokens[1:])
        if arity != "bool" and not values:
            raise Reject(f"MISSING VALUE {flag}")
        if enum is not None:
            for item in values:
                if item not in enum:
                    raise Reject(f"BAD ENUM {flag}={item!r} not in {sorted(enum)}")
        if flag == "--parameter-overrides":
            for item in values:
                if not (item.startswith("file://") or coerce_json(item) is not None or re.match(r"^[^=\s]+=", item)):
                    raise Reject(f"BAD PARAMETER OVERRIDE {item!r}")
        if flag == "--tags":
            for item in values:
                if not re.match(r"^[^=\s]+=", item):
                    raise Reject(f"BAD TAG {item!r}")
        parsed[flag] = values
    missing = sorted(f for f in spec["required"] if f not in parsed)
    if missing:
        raise Reject(f"MISSING REQUIRED {missing}")
    if len(positional) != spec["positionals"]:
        raise Reject(f"EXPECTED {spec['positionals']} POSITIONAL ARGUMENT(S), got {positional}")
    return parsed, positional


# --------------------------------------------------------------------------
# Scenario
# --------------------------------------------------------------------------


def match_scenario(scenario: dict[str, Any], service: str, sub: str, flags: set[str]) -> str | None:
    """Pick the most specific scenario key for a call.

    A key is ``"<service> <subcommand> [--flag ...] [!--flag ...]"``: the listed
    flags must be present and the ``!`` flags absent. The key with the most
    constraints wins; ties go to the first in file order.

    Args:
        scenario: Parsed scenario file.
        service: CLI service name.
        sub: CLI subcommand.
        flags: Flags present in the call (non-global flags and global ones).

    Returns:
        The matching key, or None.
    """
    best: str | None = None
    best_score = -1
    for key in scenario:
        tokens = key.split()
        if len(tokens) < 2 or tokens[0] != service or tokens[1] != sub:
            continue
        required = {t for t in tokens[2:] if not t.startswith("!")}
        forbidden = {t[1:] for t in tokens[2:] if t.startswith("!")}
        if not required <= flags or forbidden & flags:
            continue
        score = len(required) + len(forbidden)
        if score > best_score:
            best, best_score = key, score
    return best


def next_response(key: str, entry: Any, state_path: Path) -> dict[str, Any]:
    """Return the next response for a scenario entry (lists advance per call).

    Args:
        key: Scenario key.
        entry: A response dict or a list of them.
        state_path: File that keeps per-key call counters between processes.

    Returns:
        The response dict.
    """
    if isinstance(entry, dict):
        return entry
    state: dict[str, int] = {}
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except ValueError:
            state = {}
    index = state.get(key, 0)
    state[key] = index + 1
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return entry[min(index, len(entry) - 1)]


def record(path: str, payload: dict[str, Any]) -> None:
    """Append one JSON line to the call log.

    Args:
        path: Log file path (empty disables logging).
        payload: Record to append.
    """
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------


def run(argv: list[str]) -> int:
    """Handle one ``aws`` invocation.

    Args:
        argv: Arguments after ``aws``.

    Returns:
        Exit code.
    """
    if argv == ["--version"]:
        print(VERSION_LINE)
        return 0
    log_path = os.environ.get("STUB_CALL_LOG", "")
    words, groups = split_options(argv)
    if len(words) < 2:
        die(REJECT, f"stub: need <service> <subcommand>, got {words!r}")
    service, sub = words[0], words[1]
    global_values: dict[str, str] = {}
    for flag, tokens in groups:
        if flag in GLOBAL_VALUE_FLAGS and tokens:
            global_values[flag] = tokens[0]
    base = {
        "service": service,
        "subcommand": sub,
        "argv": argv,
        "profile": global_values.get("--profile"),
        "region": global_values.get("--region"),
        "env": {
            "AWS_PROFILE": os.environ.get("AWS_PROFILE"),
            "AWS_REGION": os.environ.get("AWS_REGION"),
            "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION"),
            "AWS_ACCESS_KEY_ID_set": "AWS_ACCESS_KEY_ID" in os.environ,
            "AWS_SECRET_ACCESS_KEY_set": "AWS_SECRET_ACCESS_KEY" in os.environ,
            "AWS_SESSION_TOKEN_set": "AWS_SESSION_TOKEN" in os.environ,
        },
    }
    try:
        if (service, sub) in CUSTOM_COMMANDS:
            parsed, positional = validate_custom(service, sub, groups)
        else:
            parsed, positional = validate_modeled(service, sub, groups)
        if global_values.get("--output") != "json":
            record(log_path, {**base, "args": parsed, "stub_rc": BAD_OUTPUT})
            die(BAD_OUTPUT, f"stub: --output json is required (got {global_values.get('--output')!r})")
        query = global_values.get("--query")
        if query is not None:
            import jmespath

            try:
                jmespath.compile(query)
            except jmespath.exceptions.JMESPathError as exc:
                raise Reject(f"BAD QUERY {query!r}: {exc}") from None
    except Reject as exc:
        record(log_path, {**base, "args": {}, "stub_rc": REJECT, "reason": str(exc)})
        die(REJECT, f"stub: {exc}")

    flags_present = set(parsed) | {f for f, _ in groups}
    scenario_path = os.environ.get("STUB_SCENARIO", "")
    scenario: dict[str, Any] = {}
    if scenario_path and Path(scenario_path).is_file():
        scenario = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    key = match_scenario(scenario, service, sub, flags_present)
    call_key = f"{service} {sub}"
    if key is None:
        record(log_path, {**base, "args": parsed, "positional": positional, "stub_rc": UNSTUBBED})
        die(UNSTUBBED, f"UNSTUBBED call: {call_key}")
    state_path = Path((log_path or scenario_path or "/tmp/aws-stub") + ".state")
    response = next_response(key, scenario[key], state_path)
    rc = int(response.get("rc", 0))
    record(log_path, {**base, "args": parsed, "positional": positional, "stub_rc": rc, "key": key})
    if rc != 0:
        sys.stderr.write(str(response.get("stderr", "")) + "\n")
        return rc
    if (service, sub) == ("lambda", "invoke"):
        Path(positional[0]).write_text(json.dumps(response.get("body", {})), encoding="utf-8")
        print(response.get("stdout", json.dumps({"StatusCode": 200})))
        return 0
    body = response.get("body", {})
    if query is not None:
        import jmespath

        body = jmespath.search(query, body)
    print(json.dumps(body, indent=2))
    return 0


def main() -> int:
    """Run the stub, turning an unexpected exception into a ``stub:`` crash line.

    Returns:
        Exit code.
    """
    try:
        return run(sys.argv[1:])
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - a crash must be loud, never an exit 0
        sys.stderr.write("stub: internal error\n" + traceback.format_exc())
        return CRASH


if __name__ == "__main__":
    sys.exit(main())
