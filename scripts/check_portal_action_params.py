#!/usr/bin/env python3
"""Check that the portal's UI sends the parameters its Lambda actions require.

The generic dispatch endpoints (`adminMutation`, `adminQuery`, `protectionMutation`
and the rest) take an action name and an untyped `params` JSON blob. TypeScript
checks that `params` is valid JSON and stops there, so a component can send
`{snapshotName, retentionDays}` to an action that reads `snapshotId` and
`expiryTime` and nothing objects — not the compiler, not the linter, not a test
that mocks the call. The button renders, the click fails, and it fails the same
way every time.

That shipped: the Tamperproof tab's lock button had never once worked.

What this checks, per action:

  * A key the handler *requires* — reads from the event and then refuses the
    request when it is missing — that a call site does not send. This is the
    broken case and it fails the build.
  * A key a call site sends that the handler never reads. Usually harmless, but
    it is how the broken case looks from the other side, so it is reported.

Scope: the generic dispatch only. Single-purpose operations (`getPresignedUrl`,
`searchFiles`) declare their arguments in the GraphQL schema, so the compiler
already checks those.

Most call sites now go through `src/lib/dispatch.ts`, whose per-action parameter
types are generated from these same handlers by `portal_action_types.py`, so the
compiler checks them and this script no longer sees them — the site count it prints
falls as that migration proceeds, and a low count is not a weakening. What it still
covers is any call made straight on the generated client, which an ESLint rule now
refuses, and the handler-side extraction the generated types are built from.

Run:

    python3 scripts/check_portal_action_params.py
"""

from __future__ import annotations

import ast
import copy
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTAL = ROOT / "solutions" / "amplify-portal"


@dataclass
class Endpoint:
    """How one generic-dispatch endpoint reaches its Lambda."""

    name: str
    handler_dir: str
    resolver: str
    # Whether the resolver spreads params into the payload or nests them under a
    # `params` key. Both shapes are in use and the handlers read accordingly, so
    # assuming one of them makes every action on the other endpoint look broken.
    flattened: bool
    # Keys the resolver adds itself, which a handler may read without the UI
    # sending them.
    injected: frozenset[str]


def _read(path: Path) -> str:
    return path.read_text()


def discover_endpoints() -> tuple[list[Endpoint], list[str]]:
    """Work out the endpoint wiring from the files that define it.

    Nothing here is hardcoded, because a hand-written table is exactly what goes
    stale: a renamed data source or a resolver switched from spread to nested
    params would leave the table describing a system that no longer exists, and the
    check would keep passing against it.

    resource.ts gives endpoint -> (dataSource, resolver); the resolver gives the
    payload shape; backend.ts gives dataSource -> functions/<dir>.
    """
    problems: list[str] = []
    resource = _read(PORTAL / "amplify" / "data" / "resource.ts")
    backend = _read(PORTAL / "amplify" / "backend.ts")

    # dataSource name -> the CDK variable holding the function
    source_to_variable = dict(
        re.findall(
            r"""addLambdaDataSource\(\s*["'](?P<source>[A-Za-z0-9_]+)["']\s*,\s*(?P<variable>[A-Za-z0-9_]+)""",
            backend,
        )
    )
    # variable -> functions/<dir>, from the asset path in its declaration
    variable_to_dir: dict[str, str] = {}
    for match in re.finditer(r"const\s+(?P<variable>[A-Za-z0-9_]+)\s*=\s*new\b", backend):
        window = backend[match.end() : match.end() + 1200]
        asset = re.search(r"functions/(?P<dir>[A-Za-z0-9_-]+)", window)
        if asset:
            variable_to_dir[match.group("variable")] = asset.group("dir")

    endpoints: list[Endpoint] = []
    for match in re.finditer(
        r"""(?P<name>[A-Za-z][A-Za-z0-9_]*):\s*a\s*\n"""
        r"""(?P<body>(?:(?!\n\s*[A-Za-z][A-Za-z0-9_]*:\s*a\s*\n).)*?)"""
        r"""dataSource:\s*["'](?P<source>[A-Za-z0-9_]+)["']\s*,\s*entry:\s*["'](?P<entry>[^"']+)["']""",
        resource,
        re.DOTALL,
    ):
        name = match.group("name")
        source = match.group("source")
        entry = match.group("entry")

        # Only the generic dispatch takes an untyped `params`; everything else
        # declares its arguments in the schema and the compiler checks them.
        if "params: a.json()" not in match.group("body"):
            continue

        variable = source_to_variable.get(source)
        handler_dir = variable_to_dir.get(variable or "")
        if not handler_dir:
            problems.append(f"{name}: cannot resolve {source} to a functions/ directory")
            continue
        if not (PORTAL / "functions" / handler_dir).is_dir():
            problems.append(f"{name}: resolves to functions/{handler_dir}, which does not exist")
            continue

        resolver_path = (PORTAL / "amplify" / "data" / entry.lstrip("./")).resolve()
        if not resolver_path.exists():
            problems.append(f"{name}: resolver {entry} does not exist")
            continue

        payload = re.search(r"payload:\s*\{(?P<body>.*?)\}\s*,?\s*\n\s*\};", _read(resolver_path), re.DOTALL)
        if not payload:
            problems.append(f"{name}: cannot read the payload shape from {entry}")
            continue
        body = payload.group("body")
        flattened = "...params" in body
        injected = {
            key
            for key in re.findall(r"(?:^|[\s,{])(?P<key>[A-Za-z][A-Za-z0-9_]*)\s*[:,}]", body)
            if key not in ("params",)
        }
        endpoints.append(Endpoint(name, handler_dir, entry, flattened, frozenset(injected)))

    if not endpoints:
        problems.append("no generic-dispatch endpoints found in amplify/data/resource.ts")
    return endpoints, problems


@dataclass
class ActionContract:
    """What a handler action reads out of its payload."""

    handler: str
    # Each entry is a set of alternatives, at least one of which must be sent.
    groups: list[set[str]] = field(default_factory=list)
    # Every key any code path in this Lambda reads. Deliberately wide: the shared
    # prologue reads for all actions, so a narrower set reports parameters as
    # ignored that the handler does use.
    read: set[str] = field(default_factory=set)
    # Keys read on this action's own branch. Too narrow for the unread-parameter
    # check, but it is what a parameter type should contain — a generated interface
    # built from `read` would let every action accept every key the Lambda knows.
    branch_read: set[str] = field(default_factory=set)
    # Values a key is restricted to, taken from the handler's own guard
    # (`if mode not in ("GOVERNANCE", "COMPLIANCE"): return ...`).
    #
    # Read rather than guessed, because the same parameter name means different sets
    # in different actions: `protocol` is validated against nfs/cifs/s3 for one
    # action and carries ONTAP's FPolicy values (cifs/nfsv3/nfsv4) for another. A
    # table keyed on the name alone got that wrong and rejected working code.
    enums: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def unsatisfied(self, sent: set[str]) -> list[set[str]]:
        """Requirement groups no key in `sent` satisfies, each reported once.

        Deduplicated because one guard can be reached by more than one path through
        the collector — `event["k"]` is recorded by both the subscript visit and the
        assignment visit — and reporting the same missing key twice reads as two
        separate problems.
        """
        seen: set[frozenset[str]] = set()
        out: list[set[str]] = []
        for group in self.groups:
            if group & sent:
                continue
            key = frozenset(group)
            if key in seen:
                continue
            seen.add(key)
            out.append(group)
        return out


@dataclass
class CallSite:
    location: str
    endpoint: str
    action: str
    keys: set[str]
    # A call site assembled with a spread of a computed object cannot be read
    # statically. Those are reported as unknown rather than as missing keys.
    opaque: bool = False


def module_string_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = "literal"` bindings.

    Needed because handlers read some keys through a constant rather than a literal
    — `event.get(_IRREVERSIBLE_ACK_FIELD)` — and a checker that only understood
    literals reported the acknowledgement flag as a parameter nothing reads, on
    every call site that correctly sends it.
    """
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value.value
    return constants


class EventKeyVisitor(ast.NodeVisitor):
    """Collect `event.get("k")` / `event[...]` keys and which of them are required.

    Required means the handler refuses the request without it. Three shapes cover
    the handlers in this repository:

        name = event.get("k", "")   ... if not name: return {...}
        if not event.get("k"): return {...}
        if not all([a, b]): return {...}      # a, b bound from event.get

    Anything else is treated as optional, which is the safe direction: a false
    "optional" only means this check stays quiet, while a false "required" would
    fail the build over a parameter nobody has to send.
    """

    def __init__(self, event_param: str, constants: dict[str, str] | None = None):
        self.event = event_param
        self.constants = constants or {}
        self.keys: set[str] = set()
        # Each group means "at least one of these must be sent". A plain required
        # key is a group of one. Modelling it this way is necessary because
        # `if not days and not years: return ...` demands one of the two, and
        # treating each as required flagged every caller that sent only days.
        self.groups: list[set[str]] = []
        # local variable name -> event key it was bound from
        self.bindings: dict[str, str] = {}
        # (helper name, position of the payload argument), to follow
        self.delegates: set[tuple[str, int]] = set()
        # Functions handed to a helper as a callback, which receive the payload as
        # their own first argument.
        self.callbacks: set[str] = set()
        # Helpers reached only from inside a conditional branch. What such a helper
        # demands is demanded on that branch, not by the action: `_fan_out` calls
        # `_require_confirm` under `if gated:`, and gated is false for the unblock
        # actions. Reported flatly, every unblock button looked like it was missing
        # a confirmation it must not send.
        self.delegates_conditional: set[str] = set()
        self.delegates_unconditional: set[str] = set()
        # Variables an enclosing `if` has already tested for presence. A guard on
        # one of these validates the value's shape when supplied rather than
        # demanding it: `svms` is optional, but inside `if requested is not None:`
        # there is a `if not requested ... : return` that says nothing about
        # whether the caller had to send it.
        self._presence_tested: set[str] = set()
        # How many enclosing conditional branches we are inside. A guard is only a
        # requirement of the action when nothing conditions it.
        self._conditional_depth = 0
        # payload key -> the values the handler restricts it to
        self.enums: dict[str, tuple[str, ...]] = {}
        # local name -> the string constants it was assigned, for guards written as
        # `valid_states = {...}` / `if new_state not in valid_states:` rather than
        # with the set inline. Both spellings state the same accepted set.
        self.literal_sets: dict[str, tuple[str, ...]] = {}

    # --- reads -------------------------------------------------------------

    def _literal_key(self, node: ast.AST) -> str | None:
        """The string a key expression evaluates to, literal or module constant."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self.constants.get(node.id)
        return None

    def _event_key(self, node: ast.AST) -> str | None:
        """The key if `node` is a read of the event, else None."""
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and isinstance(func.value, ast.Name)
                and func.value.id == self.event
                and node.args
            ):
                return self._literal_key(node.args[0])
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == self.event:
            key = self._literal_key(node.slice)
            if key:
                # `event["k"]` raises without the key, so an unguarded one is a
                # requirement. A guarded one is not, and the handlers are full of
                # `if event.get("k"): body["k"] = event["k"]` — optional fields,
                # copied only when supplied. Counting those made three actions look
                # as though they demanded everything they can accept.
                if self._conditional_depth == 0 and key not in self._presence_keys():
                    self.groups.append({key})
                return key
        return None

    def _presence_keys(self) -> set[str]:
        """Payload keys an enclosing condition has already established are present."""
        return {self.bindings.get(name, name) for name in self._presence_tested}

    def visit_Call(self, node: ast.Call) -> None:
        key = self._event_key(node)
        if key:
            self.keys.add(key)
        # A helper receiving the payload reads it on this action's behalf. The
        # position is recorded so the callee's own parameter name can be used,
        # which is not always the same word.
        if isinstance(node.func, ast.Name) and node.func.id.startswith("_"):
            reached = self.delegates_conditional if self._conditional_depth > 0 else self.delegates_unconditional
            reached.add(node.func.id)
            for position, argument in enumerate(node.args):
                if isinstance(argument, ast.Name) and argument.id == self.event:
                    self.delegates.add((node.func.id, position))
                # `single({**event, "svm": ...})` forwards the payload too.
                if isinstance(argument, ast.Dict) and any(
                    key is None and isinstance(value, ast.Name) and value.id == self.event
                    for key, value in zip(argument.keys, argument.values)
                ):
                    self.delegates.add((node.func.id, position))

        # A function handed to a helper as a callback reads the payload as well,
        # one indirection further out. The containment actions are dispatched this
        # way — `_fan_out(event, _arp_disconnect_sessions, ...)` — so without this
        # the parameters those actions read look unread by anything.
        for argument in node.args:
            if isinstance(argument, ast.Name) and argument.id.startswith("_"):
                self.callbacks.add(argument.id)
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        key = self._event_key(node)
        if key:
            self.keys.add(key)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        key = self._event_key(node.value)
        if key and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            self.bindings[node.targets[0].id] = key
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            values = _string_collection(node.value)
            if values:
                self.literal_sets[node.targets[0].id] = values
        self.generic_visit(node)

    # --- guards ------------------------------------------------------------

    def visit_If(self, node: ast.If) -> None:
        if _returns_immediately(node.body) and self._conditional_depth == 0:
            for key, allowed in _membership_constraints(node.test, self.bindings, self.literal_sets).items():
                # A second guard on the same key narrows rather than replaces, but no
                # handler does that, so first one wins and stays predictable.
                self.enums.setdefault(key, allowed)

        if _returns_immediately(node.body):
            # Presence is tracked by variable name, requirements by payload key, so
            # the names have to be resolved through the bindings before comparing.
            # Without that the exemption never matched and `svms` stayed "required".
            exempt = self._presence_keys()
            for alternatives in _requirement_groups(node.test, self.event, self.bindings, self.constants):
                if alternatives & exempt:
                    continue
                self.keys |= alternatives
                # Only an unconditional guard is a requirement of the action. A
                # guard nested inside another branch applies when that branch is
                # taken: SnapLock volumes must give a retention period, ordinary
                # volumes must not, and reporting it flatly told every caller
                # creating a plain volume that it was missing three parameters.
                if self._conditional_depth == 0:
                    self.groups.append(alternatives)

        # Descend with any variable this test checks for presence marked, so a
        # shape guard nested under it is not read as a requirement, and with the
        # conditional depth raised unless this branch is itself a bail-out guard.
        # A guard's own body is not a conditional context: `if not a: return` at the
        # top of a function still leaves the code after it unconditional.
        outer_presence = self._presence_tested
        outer_depth = self._conditional_depth
        self._presence_tested = outer_presence | _presence_tested_names(node.test, self.event, self.constants)
        if not _returns_immediately(node.body):
            self._conditional_depth = outer_depth + 1
        for statement in node.body:
            self.visit(statement)
        self._presence_tested = outer_presence
        self._conditional_depth = outer_depth + 1
        for statement in node.orelse:
            self.visit(statement)
        self._conditional_depth = outer_depth
        self.visit(node.test)


def _returns_immediately(body: list[ast.stmt]) -> bool:
    """Whether this branch bails out, i.e. the guard rejects rather than defaults."""
    return any(isinstance(stmt, ast.Return) for stmt in body)


def _falsy_key(node: ast.AST, event: str, bindings: dict[str, str], constants: dict[str, str]) -> str | None:
    """The payload key a `not X` operand refers to, if any."""
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == event
        and node.args
    ):
        argument = node.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            return argument.value
        if isinstance(argument, ast.Name):
            return constants.get(argument.id)
    return None


def _requirement_groups(
    test: ast.AST, event: str, bindings: dict[str, str], constants: dict[str, str]
) -> list[set[str]]:
    """Requirements implied by a guard that returns, as "at least one of" groups.

    The distinction that matters is between conjunction and disjunction:

        if not a or not b:  -> rejects when either is missing -> {a}, {b}
        if not a and not b: -> rejects only when both are     -> {a, b}
        if not all([a, b]): -> rejects when either is missing -> {a}, {b}
        if not any([a, b]): -> rejects only when both are     -> {a, b}
    """

    def keys_of(node: ast.AST) -> set[str] | None:
        """Keys of a single `not ...` operand, or None if it is not one."""
        if not (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)):
            return None
        operand = node.operand
        if (
            isinstance(operand, ast.Call)
            and isinstance(operand.func, ast.Name)
            and operand.func.id in ("all", "any")
            and operand.args
        ):
            collected = {
                key
                for element in ast.walk(operand.args[0])
                for key in [_falsy_key(element, event, bindings, constants)]
                if key
            }
            if not collected:
                return None
            # not all(...) needs every one; not any(...) needs one of them.
            return {"__each__", *collected} if operand.func.id == "all" else collected
        key = _falsy_key(operand, event, bindings, constants)
        return {key} if key else None

    if isinstance(test, ast.BoolOp):
        parts = [keys_of(value) for value in test.values]
        if any(part is None for part in parts):
            # A mixed condition (`not a and other_thing`) says nothing reliable.
            return []
        if isinstance(test.op, ast.And):
            merged: set[str] = set()
            for part in parts:
                assert part is not None
                merged |= part - {"__each__"}
            return [merged] if merged else []
        groups: list[set[str]] = []
        for part in parts:
            assert part is not None
            groups.extend(_expand(part))
        return groups

    single = keys_of(test)
    return _expand(single) if single else []


def _expand(keys: set[str]) -> list[set[str]]:
    """Turn one operand's keys into groups, honouring the `all()` marker."""
    if "__each__" in keys:
        return [{key} for key in keys - {"__each__"}]
    return [keys] if keys else []


def _string_collection(node: ast.AST) -> tuple[str, ...]:
    """The strings in a tuple/list/set literal, or empty if it is not one of those.

    Empty is also returned when any element is not a string constant, because a
    partially understood set would understate the accepted values and reject calls
    the handler allows.
    """
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return ()
    values = tuple(e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str))
    return values if len(values) == len(node.elts) else ()


def _membership_constraints(
    test: ast.AST,
    bindings: dict[str, str],
    literal_sets: dict[str, tuple[str, ...]] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Values a rejecting guard restricts a key to.

    Matches `if <var> not in ("a", "b"):` where `<var>` was bound from the payload,
    and the same guard written against a named set assigned earlier in the function.
    This is the handler stating its own accepted set, which is more reliable than any
    table kept alongside it.
    """
    found: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(test):
        if not (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.NotIn)):
            continue
        left, right = node.left, node.comparators[0]
        if not (isinstance(left, ast.Name) and left.id in bindings):
            continue
        if isinstance(right, ast.Name):
            values = (literal_sets or {}).get(right.id, ())
        else:
            values = _string_collection(right)
        if values:
            found[bindings[left.id]] = values
    return found


def _presence_tested_names(test: ast.AST, event: str = "", constants: dict[str, str] | None = None) -> set[str]:
    """Names or keys this condition establishes are present, rather than valid."""
    found: set[str] = set()
    for node in ast.walk(test):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], (ast.Is, ast.IsNot)):
            if isinstance(node.left, ast.Name) and isinstance(node.comparators[0], ast.Constant):
                if node.comparators[0].value is None:
                    found.add(node.left.id)
    # `if requested:` — the whole test is the variable.
    if isinstance(test, ast.Name):
        found.add(test.id)
    # `if event.get("k"):` — the whole test is the read, so the key is present in
    # the body. This is the shape used to copy optional fields into a request body.
    if event:
        key = _falsy_key(test, event, {}, constants or {})
        if key:
            found.add(key)
    return found


def _collect(
    func: ast.FunctionDef,
    payload: str,
    functions: dict[str, ast.FunctionDef],
    seen: set[str],
    constants: dict[str, str],
) -> tuple[set[str], list[set[str]], dict[str, tuple[str, ...]]]:
    """Keys, requirement groups and value constraints for `func`.

    Follows helpers it passes the payload to.

    `payload` is the name of the variable holding the caller's parameters. It is
    not always `event`: the agent endpoint nests them, so its handler does
    `params = event.get("params", {})` and every read goes through `params`.
    Assuming `event` there reported every agent action as ignoring its input.
    """
    visitor = EventKeyVisitor(payload, constants)
    visitor.visit(func)
    keys, groups, enums = set(visitor.keys), list(visitor.groups), dict(visitor.enums)

    followed = {(name, position) for name, position in visitor.delegates}
    followed |= {(name, 0) for name in visitor.callbacks}
    conditional_only = visitor.delegates_conditional - visitor.delegates_unconditional

    for name, position in followed:
        if name in seen or name not in functions:
            continue
        callee = functions[name]
        if position >= len(callee.args.args):
            continue
        sub_keys, sub_groups, sub_enums = _collect(
            callee, callee.args.args[position].arg, functions, seen | {name}, constants
        )
        keys |= sub_keys
        if name not in conditional_only:
            groups.extend(sub_groups)
        for key, allowed in sub_enums.items():
            enums.setdefault(key, allowed)

    return keys, groups, enums


def _branch_action(test: ast.AST) -> str | None:
    """The action name an `if`/`elif` test compares against."""
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq):
        left, right = test.left, test.comparators[0]
        if isinstance(left, ast.Name) and left.id == "action" and isinstance(right, ast.Constant):
            if isinstance(right.value, str):
                return right.value
    return None


def _branch_actions(test: ast.AST) -> set[str]:
    """Action names for a test, across the shapes the handlers use.

    Covers `action == "x"`, `action in ("x", "y")`, and `action == "x" and <cond>`
    — the last of which appears in the file listing handler and, when unhandled,
    made a dispatched action look absent.
    """
    single = _branch_action(test)
    if single:
        return {single}
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.In):
        left, right = test.left, test.comparators[0]
        if isinstance(left, ast.Name) and left.id == "action" and isinstance(right, (ast.Tuple, ast.List, ast.Set)):
            return {e.value for e in right.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        found: set[str] = set()
        for value in test.values:
            found |= _branch_actions(value)
        return found
    return set()


def _default_actions(tree: ast.Module, payload_names: set[str]) -> set[str]:
    """Actions served by the fall-through, i.e. the default of the action read.

    `action = event.get("action", "listSnapshots")` dispatches `listSnapshots`
    without ever comparing against it, so a scan for `action == "..."` alone
    concludes the handler does not support the very thing it is mostly for.
    """
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        if node.targets[0].id != "action":
            continue
        call = node.value
        if (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "get"
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id in payload_names
            and len(call.args) == 2
            and isinstance(call.args[1], ast.Constant)
            and isinstance(call.args[1].value, str)
            and call.args[1].value
        ):
            found.add(call.args[1].value)
    return found


def _without_action_branches(body: list[ast.stmt]) -> list[ast.stmt]:
    """`body` with the action dispatch removed, leaving the code common to all actions.

    Descends into `try`/`with`/plain `if`, because the dispatch chain is usually
    nested inside a `try:` and the reads before it are not.
    """
    kept: list[ast.stmt] = []
    for statement in body:
        if isinstance(statement, ast.If):
            if _branch_actions(statement.test):
                continue
            trimmed = ast.If(
                test=statement.test,
                body=_without_action_branches(statement.body) or [ast.Pass()],
                orelse=_without_action_branches(statement.orelse),
            )
            ast.copy_location(trimmed, statement)
            kept.append(trimmed)
            continue
        if isinstance(statement, (ast.Try, ast.With)):
            statement.body = _without_action_branches(statement.body) or [ast.Pass()]
        kept.append(statement)
    return kept


def _payload_variable(tree: ast.Module, flattened: bool) -> str:
    """The variable a handler reads the caller's parameters from.

    Flattened endpoints read the event directly. A nested endpoint binds them
    first, as `params = event.get("params", {})`, and that name is what the reads
    and the delegated helpers use.
    """
    if flattened:
        return "event"
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            call = node.value
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr == "get"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "event"
                and call.args
                and isinstance(call.args[0], ast.Constant)
                and call.args[0].value == "params"
            ):
                return node.targets[0].id
    return "params"


def handler_contracts(path: Path, flattened: bool, injected: frozenset[str]) -> dict[str, ActionContract] | None:
    """Map each action the handler dispatches to what it reads.

    Returns None for a single-purpose Lambda — one that never looks at `action` and
    so does the same thing whatever is sent. The folder download function is one;
    calling it with an action name is inert rather than wrong.
    """
    tree = ast.parse(path.read_text())
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    constants = module_string_constants(tree)
    payload = _payload_variable(tree, flattened)
    label = str(path.relative_to(PORTAL))

    reads_action = any(
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "action"
        for node in ast.walk(tree)
    )
    if not reads_action:
        return None

    contracts: dict[str, ActionContract] = {}

    def record(
        actions: set[str],
        keys: set[str],
        groups: list[set[str]],
        enums: dict[str, tuple[str, ...]],
    ) -> None:
        for action in actions:
            contract = contracts.setdefault(action, ActionContract(handler=label))
            contract.read |= keys - injected
            contract.branch_read |= keys - injected
            for group in groups:
                trimmed = group - injected
                if trimmed:
                    contract.groups.append(trimmed)
            for key, allowed in enums.items():
                contract.enums.setdefault(key, allowed)

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        actions = _branch_actions(node.test)
        if not actions:
            continue

        wrapper = ast.FunctionDef(
            name="_branch",
            args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
            body=node.body,
            decorator_list=[],
            returns=None,
            type_comment=None,
        )
        ast.fix_missing_locations(wrapper)
        record(actions, *_collect(wrapper, payload, functions, set(), constants))  # noqa: B026

    # Keys the code outside every action branch reads. That code runs whatever the
    # action is, so those keys belong to all of them: `list-files` reads `prefix`,
    # `maxKeys` and `continuationToken` once at the top, and attributing them to the
    # default action alone made `listFilesFromAp` look like it takes an AP alias and
    # nothing else — which would have moved the SnapshotCompare bug rather than
    # fixing it, by declaring the prefix it needs to send illegal.
    prologue_keys: set[str] = set()
    for function in functions.values():
        if not any(argument.arg in ("event", payload) for argument in function.args.args):
            continue
        # Only the function that dispatches has a prologue. Every other function is
        # one action's implementation, and taking its whole body as common code gave
        # every action every parameter in the Lambda.
        if not any(isinstance(node, ast.If) and _branch_actions(node.test) for node in ast.walk(function)):
            continue
        outside = ast.FunctionDef(
            name="_prologue",
            args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[], kw_defaults=[], defaults=[]),
            # Copied, because the trim rewrites `try`/`with` bodies in place and the
            # untouched tree is still needed below for the module-wide read set.
            body=_without_action_branches(copy.deepcopy(function.body)) or [ast.Pass()],
            decorator_list=[],
            returns=None,
            type_comment=None,
        )
        ast.fix_missing_locations(outside)
        function_keys, _, _ = _collect(outside, payload, functions, set(), constants)
        prologue_keys |= function_keys

    for contract in contracts.values():
        contract.branch_read |= prologue_keys - injected

    # Every key this Lambda reads anywhere. The prologue before the action branches
    # runs for all of them — `prefix` and `maxKeys` are read there, once, for every
    # listing action — so attributing reads strictly per branch reports parameters
    # as ignored that the handler does in fact use.
    #
    # This is only applied to what the handler *reads*. Requirements stay per
    # branch, where they belong: a guard inside one action says nothing about the
    # others. The effect is that "never reads" means no code path in this Lambda
    # touches the key, which is the claim worth making — and the shape the broken
    # lock button had.
    module_keys: set[str] = set()
    for function in functions.values():
        if any(argument.arg in ("event", payload) for argument in function.args.args):
            function_keys, _, _ = _collect(function, payload, functions, set(), constants)
            module_keys |= function_keys

    for action in _default_actions(tree, {"event", payload}):
        contract = contracts.setdefault(action, ActionContract(handler=label))
        # The default action *is* the module's own code path, so the module's reads
        # are its branch reads. Leaving these empty gave it no parameters at all,
        # and a generated type saying `listSnapshots` takes nothing rejected the
        # `maxResults` every caller sends.
        contract.branch_read |= module_keys - injected
    for contract in contracts.values():
        contract.read |= module_keys - injected

    return contracts


# --- UI side ---------------------------------------------------------------

# The call that reaches a generic-dispatch resolver. Anchoring on this rather than
# on `action:` alone matters: `action` is also an ordinary field name in this code
# base — a confirmation dialog holds `{uuid, action: "breakSnapmirror"}` in state,
# and a decision hook returns `{action: "AUTO_APPROVE"}`. Matching those produced
# fourteen findings about handlers that were never being called.
DISPATCH_CALL_RE = re.compile(r"client\.(?:mutations|queries)\.(?P<endpoint>[A-Za-z][A-Za-z0-9_]*)\s*\(")

ACTION_RE = re.compile(r"""(?:^|[\s,{])action:\s*["'](?P<action>[A-Za-z][A-Za-z0-9_]*)["']""")

# `const { query, mutate } = useAdminApi();` — the shared admin wrapper. Its two
# functions forward to adminQuery and adminMutation with the action as an argument,
# so callers pass a literal that this check can still read.
USE_ADMIN_API_RE = re.compile(r"const\s*\{(?P<names>[^}]*)\}\s*=\s*useAdminApi\s*\(")

# A `const NAME = ...` declaration. Used to find which function a dispatch call with
# a computed action sits inside, so that function can be recognised as a wrapper and
# its own callers read instead.
LOCAL_WRAPPER_RE = re.compile(r"const\s+(?P<name>[A-Za-z][A-Za-z0-9_]*)\s*=\s*")


def _blank_comments(source: str) -> str:
    """Replace comment contents with spaces, preserving length and line breaks."""
    out = list(source)
    index = 0
    length = len(source)
    while index < length:
        if source.startswith("//", index):
            end = source.find("\n", index)
            end = length if end == -1 else end
            for position in range(index, end):
                out[position] = " "
            index = end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = length if end == -1 else end + 2
            for position in range(index, end):
                if out[position] != "\n":
                    out[position] = " "
            index = end
            continue
        index += 1
    return "".join(out)


def _object_body(text: str, start: int) -> tuple[str, int] | None:
    """The balanced `{...}` beginning at or after `start`."""
    open_at = text.find("{", start)
    if open_at == -1:
        return None
    depth = 0
    for index in range(open_at, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[open_at + 1 : index], index
    return None


def _top_level_keys(body: str) -> tuple[set[str], bool]:
    """Keys of an object literal, and whether part of it is not statically readable."""
    keys: set[str] = set()
    opaque = False
    depth = 0
    segment = ""
    segments: list[str] = []
    for char in body:
        if char in "{[(":
            depth += 1
        elif char in "}])":
            depth -= 1
        if char == "," and depth == 0:
            segments.append(segment)
            segment = ""
            continue
        segment += char
    segments.append(segment)

    for raw in segments:
        piece = raw.strip()
        if not piece:
            continue
        if piece.startswith("..."):
            # A conditional spread of a literal is readable; anything else is not.
            spread_keys = set(re.findall(r"""["']?([A-Za-z_][A-Za-z0-9_]*)["']?\s*:""", piece))
            if spread_keys:
                keys |= spread_keys
            else:
                opaque = True
            continue
        named = re.match(r"""["']?(?P<key>[A-Za-z_][A-Za-z0-9_]*)["']?\s*:""", piece)
        if named:
            keys.add(named.group("key"))
            continue
        shorthand = re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", piece)
        if shorthand:
            keys.add(piece)
            continue
        opaque = True
    return keys, opaque


# Call sites this check cannot read. Kept so `--list-opaque` can name them: they
# are the blind spot, and a blind spot nobody can enumerate is worse than one they
# can.
OPAQUE_LOCATIONS: list[str] = []


def call_sites(dispatch_endpoints: set[str]) -> tuple[list[CallSite], int]:
    """Every generic-dispatch call in the portal source, and how many were opaque.

    Opaque means the action or the parameters are computed rather than written
    literally — a shared `runAction(name, uuid, extra)` helper, for instance. Those
    cannot be checked from the source and are counted, not reported: a finding
    nobody can act on is noise.
    """
    sites: list[CallSite] = []
    opaque_count = 0
    global OPAQUE_LOCATIONS
    OPAQUE_LOCATIONS = []

    for path in sorted((PORTAL / "src").rglob("*.ts*")):
        # Comments are blanked rather than removed so line numbers still point at
        # the real source. Without this the usage example in the admin hook's own
        # doc comment was read as a call and reported as a broken one.
        text = _blank_comments(path.read_text())
        wrappers = _wrapper_endpoints(text, dispatch_endpoints)
        wrapper_bodies = _wrapper_body_ranges(text, wrappers)

        for call in DISPATCH_CALL_RE.finditer(text):
            endpoint = call.group("endpoint")
            if endpoint not in dispatch_endpoints:
                # A single-purpose operation with typed arguments in the GraphQL
                # schema. The compiler checks those already.
                continue

            line = text.count("\n", 0, call.start()) + 1
            location = f"{path.relative_to(PORTAL)}:{line}"
            argument = _object_body(text, call.end() - 1)
            if argument is None:
                opaque_count += 1
                OPAQUE_LOCATIONS.append(f"{location} ({endpoint}: argument not an object literal)")
                continue
            body = argument[0]

            action_match = ACTION_RE.search(body)
            if action_match is None:
                # A wrapper forwards whatever action it is given, so its own body is
                # the mechanism the indirect scan reads through, not a gap in
                # coverage. Counting these as blind spots overstated the blind spot
                # by the number of wrappers and hid the calls that really are
                # unreadable behind them.
                if any(start <= call.start() <= end for start, end in wrapper_bodies):
                    continue
                opaque_count += 1
                OPAQUE_LOCATIONS.append(f"{location} ({endpoint}: action is computed)")
                continue
            action = action_match.group("action")

            params_at = body.find("params:")
            if params_at == -1:
                sites.append(CallSite(location, endpoint, action, set()))
                continue
            found = _object_body(body, params_at)
            if not found:
                sites.append(CallSite(location, endpoint, action, set(), opaque=True))
                continue
            keys, opaque = _top_level_keys(found[0])
            sites.append(CallSite(location, endpoint, action, keys, opaque))

        # Indirect calls: a wrapper takes the action as an argument, so the literal
        # lives at its caller. Almost the whole admin UI reaches the backend this
        # way, and treating those as unreadable left the largest group of screens
        # unchecked.
        indirect, still_opaque = _indirect_sites(path, text, dispatch_endpoints)
        sites.extend(indirect)
        opaque_count += len(still_opaque)
        OPAQUE_LOCATIONS.extend(still_opaque)

    return sites, opaque_count


def _wrapper_body_ranges(text: str, wrappers: dict[str, str]) -> list[tuple[int, int]]:
    """Character ranges of the recognised wrappers' own definitions.

    A dispatch call inside one of these forwards an action supplied by its caller,
    which the indirect scan reads. Knowing where they are is what separates "this
    call cannot be checked" from "this call is how the checking works".
    """
    ranges: list[tuple[int, int]] = []
    for name in wrappers:
        for match in re.finditer(rf"\b(?:const|function)\s+{re.escape(name)}\b", text):
            body = _object_body(text, match.end())
            if body:
                ranges.append((match.start(), body[1]))
    return ranges


def _wrapper_endpoints(text: str, dispatch_endpoints: set[str]) -> dict[str, str]:
    """Local names that forward to a dispatch endpoint, mapped to that endpoint."""
    wrappers: dict[str, str] = {}

    # The shared hook, whose two members have fixed endpoints.
    for match in USE_ADMIN_API_RE.finditer(text):
        for entry in match.group("names").split(","):
            name = entry.split(":")[-1].strip()
            if name == "query" and "adminQuery" in dispatch_endpoints:
                wrappers[name] = "adminQuery"
            elif name == "mutate" and "adminMutation" in dispatch_endpoints:
                wrappers[name] = "adminMutation"

    # Component-local wrappers: a function that forwards whatever action it is given.
    declarations = _declaration_ranges(text)
    for call in DISPATCH_CALL_RE.finditer(text):
        endpoint = call.group("endpoint")
        if endpoint not in dispatch_endpoints:
            continue
        argument = _object_body(text, call.end() - 1)
        if argument is None or ACTION_RE.search(argument[0]):
            continue
        name = _innermost_declaration(declarations, call.start())
        if name:
            wrappers.setdefault(name, endpoint)
    return wrappers


def _declaration_ranges(text: str) -> list[tuple[str, int, int]]:
    """`const NAME = ...` declarations with a braced body, as (name, start, end)."""
    found: list[tuple[str, int, int]] = []
    for match in LOCAL_WRAPPER_RE.finditer(text):
        body = _object_body(text, match.end())
        if body:
            found.append((match.group("name"), match.start(), body[1]))
    return found


def _innermost_declaration(declarations: list[tuple[str, int, int]], position: int) -> str | None:
    """The name of the declaration whose body most closely encloses `position`.

    Enclosing, not merely preceding. Taking the nearest declaration *before* the call
    named whichever unrelated `const` happened to sit above it, so `isTransient`,
    `clearSuccess` and `toggleOp` were each treated as a dispatch wrapper — and every
    call to them was then reported as an unreadable dispatch.
    """
    best: tuple[str, int] | None = None
    for name, start, end in declarations:
        if start <= position <= end and (best is None or start > best[1]):
            best = (name, start)
    return best[0] if best else None


def _indirect_sites(path: Path, text: str, dispatch_endpoints: set[str]) -> tuple[list[CallSite], list[str]]:
    """Call sites that name their action when calling a wrapper.

    Returns the readable ones and the locations of those that are not, so the
    unreadable calls can be named rather than merely counted.
    """
    wrappers = _wrapper_endpoints(text, dispatch_endpoints)
    if not wrappers:
        return [], []

    sites: list[CallSite] = []
    unreadable: list[str] = []
    wrapper_bodies = _wrapper_body_ranges(text, wrappers)
    pattern = re.compile(
        r"\b(?P<name>" + "|".join(re.escape(n) for n in sorted(wrappers)) + r")\s*[<(]",
    )
    for match in pattern.finditer(text):
        open_paren = text.find("(", match.start())
        if open_paren == -1:
            continue
        line = text.count("\n", 0, match.start()) + 1
        location = f"{path.relative_to(PORTAL)}:{line}"
        endpoint = wrappers[match.group("name")]

        # A wrapper naming itself inside its own definition is the recursive call
        # of a `useCallback`, not a call site.
        if any(start <= match.start() <= end for start, end in wrapper_bodies):
            continue

        literal = re.match(
            r"""\(\s*["'](?P<action>[A-Za-z][A-Za-z0-9_]*)["']\s*(?P<rest>[,)])""",
            text[open_paren:],
        )
        if not literal:
            unreadable.append(f"{location} ({endpoint} via {match.group('name')}: action is computed)")
            continue
        if literal.group("rest") == ")":
            sites.append(CallSite(location, endpoint, literal.group("action"), set()))
            continue
        found = _object_body(text, open_paren + literal.end())
        if not found:
            sites.append(CallSite(location, endpoint, literal.group("action"), set(), opaque=True))
            continue
        keys, opaque = _top_level_keys(found[0])
        sites.append(CallSite(location, endpoint, literal.group("action"), keys, opaque))
    return sites, unreadable


def contracts_for(endpoint: Endpoint) -> dict[str, ActionContract] | None:
    """Action contracts for the Lambda an endpoint reaches, or None if single-purpose."""
    root = PORTAL / "functions" / endpoint.handler_dir
    merged: dict[str, ActionContract] = {}
    dispatches = False
    for source in sorted(root.rglob("*.py")):
        if "tests" in source.parts or source.name.startswith("test_"):
            continue
        found = handler_contracts(source, endpoint.flattened, endpoint.injected)
        if found is None:
            continue
        dispatches = True
        for action, contract in found.items():
            if action in merged:
                merged[action].read |= contract.read
                merged[action].branch_read |= contract.branch_read
                merged[action].groups.extend(contract.groups)
                for key, allowed in contract.enums.items():
                    merged[action].enums.setdefault(key, allowed)
            else:
                merged[action] = contract
    return merged if dispatches else None


def main() -> int:
    endpoints, problems = discover_endpoints()
    if problems:
        print("wiring (%d):" % len(problems))
        for problem in problems:
            print(f"  {problem}")
        return 1

    by_endpoint: dict[str, Endpoint] = {e.name: e for e in endpoints}
    try:
        contracts: dict[str, dict[str, ActionContract] | None] = {e.name: contracts_for(e) for e in endpoints}
    except SyntaxError as error:
        print(f"could not parse a portal handler: {error}")
        return 1

    sites, opaque_calls = call_sites(set(by_endpoint))

    if "--list-opaque" in sys.argv:
        print(f"call sites this check cannot read ({len(OPAQUE_LOCATIONS)}):")
        for location in OPAQUE_LOCATIONS:
            print(f"  {location}")
        return 0

    broken: list[str] = []
    unread: list[str] = []
    unknown_action: list[str] = []

    for site in sites:
        endpoint = by_endpoint[site.endpoint]
        actions = contracts[site.endpoint]
        if actions is None:
            # Single-purpose Lambda: the action name is decoration.
            continue

        contract = actions.get(site.action)
        if contract is None:
            unknown_action.append(
                f"  {site.location}\n"
                f"      '{site.endpoint}' reaches functions/{endpoint.handler_dir}, which does "
                f"not dispatch '{site.action}'"
            )
            continue
        if site.opaque:
            continue

        for group in contract.unsatisfied(site.keys):
            wanted = sorted(group)
            need = wanted[0] if len(wanted) == 1 else f"one of {wanted}"
            broken.append(
                f"  {site.location}\n"
                f"      '{site.action}' ({contract.handler}) refuses the request without "
                f"{need}.\n"
                f"      sends: {sorted(site.keys) or '(nothing)'}"
            )

        extra = (
            site.keys - contract.read - set().union(*contract.groups) if contract.groups else site.keys - contract.read
        )
        if extra:
            unread.append(f"  {site.location}\n      '{site.action}' ({contract.handler}) never reads {sorted(extra)}")

    # Counted per handler rather than per endpoint: a query and a mutation endpoint
    # share one Lambda, so counting per endpoint doubles its action list.
    covered_actions = {
        (endpoint.handler_dir, action) for endpoint in endpoints for action in (contracts[endpoint.name] or {})
    }
    if not (broken or unknown_action or unread):
        print(
            f"PORTAL ACTION PARAMS: PASS ({len(sites)} literal call sites, "
            f"{len(covered_actions)} actions across {len(endpoints)} endpoints, "
            f"{opaque_calls} call(s) not statically readable)"
        )
        return 0

    if unknown_action:
        print(f"\nunknown-action ({len(unknown_action)}):")
        print("\n".join(unknown_action))
    if broken:
        print(f"\nmissing-required-param ({len(broken)}):")
        print("\n".join(broken))
    if unread:
        print(f"\nunread-param ({len(unread)}):")
        print("\n".join(unread))

    print(f"\nPORTAL ACTION PARAMS: {len(broken) + len(unknown_action)} failure(s), {len(unread)} advisory finding(s)")
    return 1 if (broken or unknown_action) else 0


if __name__ == "__main__":
    sys.exit(main())
