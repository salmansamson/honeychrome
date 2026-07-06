"""Pytest configuration for the UI (pytest-qt) test suite.

By default these tests run *head-less* (Qt "offscreen" platform) so they work in
CI and over SSH without a display. To actually SEE the GUI while a test runs,
set the environment variable HONEYCHROME_SHOW_UI=1 before running pytest, e.g.

    PowerShell:   $env:HONEYCHROME_SHOW_UI=1; pytest tests/ui -s
    bash:         HONEYCHROME_SHOW_UI=1 pytest tests/ui -s

(The -s flag is recommended so pytest does not capture the GUI event loop.)
"""
import os

SHOW_UI = os.environ.get("HONEYCHROME_SHOW_UI", "").lower() in ("1", "true", "yes", "on")

if not SHOW_UI:
    # Use Qt's off-screen platform plugin unless the caller already chose one.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
