"""SQL literal rendering for Athena / Trino query construction.

Athena's `StartQueryExecution` takes a query string. There is no bind-parameter
form of it, so every value that reaches a query has to be rendered safely by the
caller, and two handlers had been interpolating values straight into f-strings:

    WHERE equipment_id = '{equipment_id}'   # scada_analyzer
    WHERE file_key = '{file_key}'           # cdr_analyzer

Both values arrive from data, not from configuration — `equipment_id` is read out
of an object on the watched volume and `file_key` is the object's own key — so
anyone able to write a file into the volume could close the quote and continue the
statement. These are reference architectures that partners copy, which makes the
pattern more consequential than the individual query.

`make security` would have reported this on the first run. It never ran: the
`security` target was missing from `.PHONY` and collided with the `security/`
directory, so make answered "up to date" and bandit was never invoked.

Escaping, not validation, is the control here. An allowlist of shapes would reject
identifiers a real SCADA or CDR feed legitimately uses; doubling the quote is what
the SQL standard defines and what Trino implements.

A second copy of this logic lives in `solutions/amplify-portal/functions/audit-log/
index.py` as `_sql_literal` / `_like_operand`, deliberately. That Lambda has no
`SharedPythonLayer` attached, and adding one to import three lines would buy a
deployment dependency whose content `ampx sandbox` does not reliably refresh. Both
copies carry their own tests. **If the rendering rule changes here, change it there
too** — that is the cost of the duplication, and it is the reason this note exists.
"""

from __future__ import annotations

__all__ = ["like_operand", "sql_literal"]


def sql_literal(value: str) -> str:
    """Render a value as a single-quoted SQL string literal.

    A single quote inside the value is doubled, which is how the SQL standard and
    Trino (Athena's engine) express a literal quote. The result includes its own
    surrounding quotes, so callers must not add more:

        f"WHERE id = {sql_literal(equipment_id)}"   # correct
        f"WHERE id = '{sql_literal(equipment_id)}'" # wrong: quotes twice

    Args:
        value: Value to embed. Coerced with `str()` so a caller passing an int or
            a `None` read from JSON cannot produce a `TypeError` at query time.

    Returns:
        The quoted literal, ready to concatenate into a query.
    """
    return "'" + str(value).replace("'", "''") + "'"


def like_operand(value: str) -> str:
    r"""Escape LIKE metacharacters so a value matches literally.

    Requires `ESCAPE '\'` on the comparison. Without this, a value containing `%`
    matches far more rows than intended — a silent correctness bug rather than an
    injection, and one that only shows up as an over-broad result set.

    Args:
        value: Value to be used as a LIKE operand.

    Returns:
        The value with `\`, `%` and `_` escaped. Still needs `sql_literal()`
        around it to become a literal.
    """
    return str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
