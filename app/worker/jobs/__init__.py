"""Worker job functions."""

# RQ imports the package __init__ before any job module, so register models once.
import app.db.models  # noqa: F401
