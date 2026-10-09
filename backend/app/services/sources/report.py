"""What each job source did during a discovery run.

Sources fail quietly on purpose (one bad feed must never stop the rest), but
that left "this source returned nothing" impossible to tell apart from "this
source is switched off" or "the site blocked us". Adapters call problem() or
not_configured() next to the print they already do, and run_discovery() reads
them back with take() to build the per-source report shown in Admin.

Discovery runs one at a time (a guard in the pipeline router), so a plain
module-level dict is enough.
"""
_notes: dict[str, list[str]] = {}
_off: set[str] = set()
MAX_NOTES = 3


def problem(source: str, message: str) -> None:
    notes = _notes.setdefault(source, [])
    if len(notes) < MAX_NOTES and message not in notes:
        notes.append(str(message)[:240])


def not_configured(source: str, env_vars: str) -> None:
    _off.add(source)
    problem(source, f"Switched off: set {env_vars} on the server to turn it on.")


def take(source: str) -> tuple[list[str], bool]:
    """(notes, switched_off) for a source, clearing them."""
    notes = _notes.pop(source, [])
    off = source in _off
    _off.discard(source)
    return notes, off
