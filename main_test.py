"""Manual test entry point: read sensors without sending API requests."""

from main import run


run(test_mode=True, send_data=False)
