"""Domain logic for the archive-verify-delete pattern.

Lambda handlers and the Fargate entrypoint under
``solutions/data-lifecycle/archive-verify-delete/`` stay thin and import from
here, so the rules that decide whether a file may be deleted live in one place
and are tested without AWS.
"""
