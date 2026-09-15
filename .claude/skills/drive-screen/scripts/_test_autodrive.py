#!/usr/bin/env python3
"""No real transcripts or GUI input: exercise the observation-only CLI boundary."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import autodrive as ad


class ObserveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-work-", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.args = ["--repo", "unused", "--id", "42", "--shot-dir", str(self.root)]
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def test_blind_flag_fails_before_any_access(self):
        with patch.object(ad.sw, "cmd_wait") as wait, patch.object(ad, "screenctl") as screen:
            self.assertEqual(ad.main(self.args + ["--approve-blind"]), 2)
            wait.assert_not_called()
            screen.assert_not_called()

    def test_completed_and_timeout_have_no_gui_calls(self):
        with patch.object(ad, "screenctl") as screen:
            for code in (0, 1):
                with patch.object(ad.sw, "cmd_wait", return_value=code):
                    self.assertEqual(ad.main(self.args), code)
            screen.assert_not_called()

    def test_dry_run_does_not_capture_or_send(self):
        with patch.object(ad.sw, "cmd_wait", return_value=2), patch.object(ad, "screenctl") as screen:
            self.assertEqual(ad.main(self.args + ["--dry-run", "--max", "99"]), 3)
            screen.assert_not_called()

    def test_quiet_capture_only_and_unique_paths(self):
        paths = []
        def capture(*args):
            self.assertEqual(args[:3], ("shot", "--id", "42"))
            path = Path(args[-1])
            paths.append(path)
            path.write_bytes(b"mock screenshot")
            return CompletedProcess(args, 0, "", "")
        with patch.object(ad.sw, "cmd_wait", return_value=2), patch.object(ad, "screenctl", side_effect=capture):
            self.assertEqual(ad.main(self.args), 3)
            self.assertEqual(ad.main(self.args), 3)
        self.assertNotEqual(paths[0], paths[1])
        self.assertIn("no keystrokes are sent", self.output.getvalue())

    def test_empty_or_failed_capture_is_error(self):
        for code in (0, 1):
            with patch.object(ad.sw, "cmd_wait", return_value=2), \
                 patch.object(ad, "screenctl", return_value=CompletedProcess([], code, "", "capture failed")):
                self.assertEqual(ad.main(self.args), 2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unreadable_session_is_error_without_gui_calls(self):
        with patch.object(ad.sw, "cmd_wait", side_effect=OSError("missing")), \
             patch.object(ad, "screenctl") as screen, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ad.main(self.args), 1)
            screen.assert_not_called()

    def test_invalid_timing_rejected_before_access(self):
        with patch.object(ad.sw, "cmd_wait") as wait, contextlib.redirect_stderr(io.StringIO()):
            for value in ("0", "-1", "nan", "inf"):
                with self.assertRaises(SystemExit) as error:
                    ad.main(self.args + ["--poll", value])
                self.assertEqual(error.exception.code, 2)
            wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
