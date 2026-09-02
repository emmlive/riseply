"""Shared test environment setup, loaded by pytest BEFORE any test
module in this directory is collected/imported.

This exists to fix a real, recurring class of bug hit repeatedly while
building out this test suite: several test files independently set
DATABASE_URL/CRON_SECRET/etc. via os.environ at module level, each
assuming its own values would be the ones in effect. But app.config's
`settings` singleton and app.database's `engine` are both built ONCE,
the first time they're imported anywhere in the process -- so only
whichever test file pytest happens to import FIRST (alphabetically, by
default) actually has its env vars take effect; every other file's
identical-looking os.environ lines silently no-op, too late to matter.
Adding a new test file could -- and did, more than once -- change
collection order and break a completely unrelated file's assumptions
about what CRON_SECRET or similar was set to.

conftest.py is loaded by pytest before collecting any test module in
its directory, specifically so shared setup like this has one
authoritative place to live instead of every file racing to be first.

Uses setdefault rather than a plain assignment so a real environment
variable already set (e.g. in a CI environment) wins over this
synthetic test value -- unlikely to matter for these test-only
values, but a safe habit regardless.
"""
import os
import tempfile

from cryptography.fernet import Fernet

_tmp_dir = tempfile.mkdtemp(prefix="riseply_test_")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp_dir}/test.db")
os.environ.setdefault("CRON_SECRET", "test-secret-value")
os.environ.setdefault("CALENDAR_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("MICROSOFT_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("MICROSOFT_OAUTH_CLIENT_SECRET", "test-client-secret")
