#!/usr/bin/env python3
"""Isolated parser/watcher regression tests; never reads real user sessions."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import session_watch as sw

PROMPT = {"type": "user", "message": {"content": "do the task"}}
END = {"type": "system", "subtype": "turn_duration"}
TOOL = {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {"command": "npm test"}}]}}
RESULT = {"type": "user", "message": {"content": [
    {"type": "tool_result", "tool_use_id": "tool-1"}]}}


def write(path, recs):
    path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agent-work-", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "selected.jsonl"
        self.old_pin = sw.PIN
        self.addCleanup(setattr, sw, "PIN", self.old_pin)
        self.output = io.StringIO()
        self.redirect = contextlib.redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)

    def wait(self, initial, later=None):
        write(self.path, initial)
        clock = [0.0]
        def sleep(seconds):
            clock[0] += seconds
            if later is not None:
                write(self.path, later)
        args = SimpleNamespace(repo="unused", timeout=3, idle=1, poll=0.5)
        with patch.object(sw, "latest", return_value=self.path) as latest, \
             patch.object(sw.time, "monotonic", side_effect=lambda: clock[0]), \
             patch.object(sw.time, "sleep", side_effect=sleep):
            result = sw.cmd_wait(args)
            latest.assert_called_once_with("unused")
            return result

    def test_empty_unknown_and_codex_are_not_complete(self):
        for recs in ([], [{"type": "turn.completed"}], [{"type": "event_msg", "payload": {"type": "task_complete"}}], [{"unknown": True}], [END]):
            with self.subTest(recs=recs):
                self.assertEqual(self.wait(recs), 2)
                self.assertTrue(sw.turn_in_flight(recs))

    def test_old_completed_turn_does_not_satisfy_new_wait(self):
        self.assertEqual(self.wait([PROMPT, END]), 2)

    def test_new_completion_requires_marker_and_prompt(self):
        self.assertEqual(self.wait([PROMPT], [PROMPT, END]), 0)
        self.assertEqual(self.wait([], [END]), 2)

    def test_quiet_final_text_is_not_completion(self):
        text = {"type": "assistant", "message": {"content": [{"type": "text", "text": "done"}]}}
        self.assertEqual(self.wait([PROMPT, text]), 2)

    def test_pending_tool_new_prompt_and_trailing_unknown_block_completion(self):
        for recs in ([PROMPT, TOOL, END], [PROMPT, END, PROMPT], [PROMPT, END, {"type": "future"}]):
            self.assertFalse(sw.completed_turn(recs))
        self.assertTrue(sw.completed_turn([PROMPT, TOOL, RESULT, END]))

    def test_replaced_transcript_fails(self):
        self.assertEqual(self.wait([PROMPT], [END]), 1)
        self.assertIn("TRANSCRIPT_REPLACED", self.output.getvalue())

    def test_deleted_transcript_raises_io_error(self):
        with self.assertRaises(OSError):
            sw.records(self.path)

    def test_json_shapes_and_partial_tail_are_defensive(self):
        self.path.write_text('null\n[]\n42\n"text"\n{broken}\n' + json.dumps(PROMPT) + '\n{"type":', encoding="utf-8")
        recs = sw.records(self.path)
        self.assertEqual(len(recs), 7)
        self.assertFalse(sw.completed_turn(recs))
        malformed = [
            {"type": "assistant", "message": "bad"},
            {"type": "assistant", "message": {"content": [{"type": "text", "text": 1}, None,
                {"type": "tool_use", "id": [], "input": "bad"}]}}]
        self.assertEqual(sw.assistant_texts(malformed), [])
        self.assertEqual(sw.pending_tool_details(malformed), [])
        self.assertEqual(sw.tool_reads(malformed, 0), [])

    def test_partial_next_prompt_cannot_certify_previous_turn(self):
        write(self.path, [PROMPT, END])
        with self.path.open("a") as handle:
            handle.write('{"type":"user"')
        self.assertFalse(sw.completed_turn(sw.records(self.path)))

    def test_unknown_record_within_turn_prevents_completion(self):
        self.assertFalse(sw.completed_turn([PROMPT, {"type": "turn.completed"}, END]))

    def test_tool_result_does_not_create_prompt(self):
        self.assertEqual(sw.prompt_indices([RESULT]), [])
        self.assertEqual(sw.pending_tool_details([TOOL]), [("Bash", "npm test")])
        self.assertEqual(sw.pending_tool_details([TOOL, RESULT]), [])

    def test_unique_prefix_and_subagent_scope(self):
        for name in ("abc-1", "abc-2"):
            write(self.root / (name + ".jsonl"), [PROMPT])
            sub = self.root / name / "subagents"
            sub.mkdir(parents=True)
            write(sub / "agent-x.jsonl", [PROMPT])
        with patch.object(sw, "session_dir", return_value=self.root):
            sw.PIN = "abc"
            with self.assertRaises(SystemExit) as error:
                sw.latest("unused")
            self.assertEqual(error.exception.code, 1)
            with self.assertRaises(SystemExit):
                sw.transcripts("unused")
            sw.PIN = "abc-1"
            paths = sw.transcripts("unused")
            self.assertEqual(paths, [self.root / "abc-1.jsonl", self.root / "abc-1/subagents/agent-x.jsonl"])
            sw.PIN = "*"
            with self.assertRaises(SystemExit):
                sw.latest("unused")

    def test_latest_does_not_skip_empty_new_session(self):
        write(self.path, [PROMPT, END])
        newer = self.root / "newer.jsonl"
        newer.touch()
        import os
        os.utime(newer, (2000000000, 2000000000))
        with patch.object(sw, "session_dir", return_value=self.root):
            sw.PIN = None
            self.assertEqual(sw.latest("unused"), newer)


if __name__ == "__main__":
    unittest.main()
