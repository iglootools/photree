"""Regression test: the CLI must not load the face ML stack at startup.

insightface, cv2, faiss and sklearn together used to add ~0.5 s to every
``photree`` invocation, including ``--version``. They are imported lazily by
the face pipeline; this test catches a module-level import creeping back in.
"""

from __future__ import annotations

import subprocess
import sys

HEAVY_ML_MODULES = ("insightface", "onnxruntime", "cv2", "faiss", "sklearn")


def test_importing_cli_does_not_load_ml_libraries() -> None:
    # A fresh interpreter: this test process may already have imported them.
    script = (
        "import sys, photree.cli\n"
        f"print(','.join(m for m in {HEAVY_ML_MODULES!r} if m in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == ""
