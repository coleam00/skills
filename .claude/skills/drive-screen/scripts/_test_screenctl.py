#!/usr/bin/env python3
"""Isolated controller regressions. All OS input and clipboard calls are mocked."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import pathlib
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import screenctl as sc


def make_png(path, solid):
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF))
    rows = bytearray()
    for y in range(120):
        rows.append(0)
        for x in range(200):
            v = 128 if solid else (x * 7 + y * 13) % 251
            rows.extend((v, v * 3 % 256, v * 5 % 256))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR', struct.pack('>IIBBBBB', 200, 120, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix='agent-work.', dir='/tmp')
        self.addCleanup(self.scratch.cleanup)
        self.enterContext(patch.object(sc, 'LOG', str(pathlib.Path(self.scratch.name) / 'actions.log')))
        self.enterContext(patch.object(sc.time, 'sleep'))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        # Any unmocked attempt to call an OS command fails the test, not the UI.
        self.enterContext(patch.object(sc.subprocess, 'run', side_effect=AssertionError('unmocked OS call')))
        self.win = sc.Win('1', 'Editor', 0, 0, 200, 100)
        self.args = types.SimpleNamespace(title='Editor', id='1', file=None,
                                          text='payload\n\n', keep_clipboard=False)

    def test_png(self):
        for solid in (False, True):
            path = pathlib.Path(self.scratch.name) / f'{solid}.png'
            make_png(path, solid)
            self.assertEqual(sc.png_size(str(path)), (200, 120))
            self.assertEqual(sc.looks_blank(str(path)), solid)

    def test_ambiguous_title_and_duplicate_fingerprint_refuse(self):
        with patch.object(sc, 'list_windows', return_value=[self.win, self.win]):
            for kwargs in ({'title': 'Editor'}, {'title': '', 'wid': '1'}):
                with self.assertRaises(SystemExit):
                    sc.resolve(**kwargs)

    def test_focus_refreshes_by_proven_id_after_title_change(self):
        renamed = sc.Win('1', 'New title', 20, 30, 200, 100)
        with patch.object(sc, 'resolve', side_effect=[self.win, renamed]) as resolve, \
                patch.object(sc, 'raise_window'), patch.object(sc, 'same_window', return_value=True):
            self.assertIs(sc.focus('Editor'), renamed)
            self.assertEqual(resolve.call_args.args, ('', '1'))

    def test_type_checks_focus_before_first_chunk(self):
        self.args.text = 'hello'
        with patch.object(sc, 'focus', return_value=self.win), \
                patch.object(sc, 'same_window', return_value=False), \
                patch.object(sc, '_die_focus_lost', side_effect=SystemExit(1)), \
                patch.object(sc, 'type_text') as send:
            with self.assertRaises(SystemExit):
                sc.act_type(self.args)
            send.assert_not_called()

    def test_paste_focus_refusal_leaves_clipboard_untouched(self):
        with patch.object(sc, 'focus', side_effect=SystemExit(1)), \
                patch.object(sc, 'set_clipboard') as put:
            with self.assertRaises(SystemExit):
                sc.act_paste(self.args)
            put.assert_not_called()

    def test_paste_restores_on_mismatch_focus_loss_and_send_error(self):
        for fault in ('mismatch', 'focus', 'send', 'none'):
            with self.subTest(fault=fault), patch.object(sc, 'focus', return_value=self.win), \
                    patch.object(sc, 'get_clipboard', side_effect=['original',
                                 'payload\n' if fault == 'mismatch' else self.args.text]), \
                    patch.object(sc, 'set_clipboard') as put, \
                    patch.object(sc, 'same_window', return_value=fault != 'focus'), \
                    patch.object(sc, 'send_chord', side_effect=SystemExit(1) if fault == 'send' else None) as send:
                if fault == 'none':
                    sc.act_paste(self.args)
                else:
                    with self.assertRaises(SystemExit):
                        sc.act_paste(self.args)
                self.assertEqual([c.args[0] for c in put.call_args_list], [self.args.text, 'original'])
                if fault in ('focus', 'mismatch'):
                    send.assert_not_called()

    def test_unreadable_clipboard_is_not_overwritten(self):
        with patch.object(sc, 'focus', return_value=self.win), \
                patch.object(sc, 'get_clipboard', side_effect=OSError('read refused')), \
                patch.object(sc, 'set_clipboard') as put:
            with self.assertRaises(SystemExit):
                sc.act_paste(self.args)
            put.assert_not_called()

    def mac_backend(self):
        # Execute only macOS definitions on every host; no discovery or GUI calls.
        tree = ast.parse(pathlib.Path(sc.__file__).read_text())
        branch = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                      and ast.unparse(n.test) == "OS == 'Darwin'")
        ns = dict(vars(sc))
        exec(compile(ast.Module(body=branch.body, type_ignores=[]), '<mac-backend>', 'exec'), ns)
        return ns

    def test_doctor_restores_clipboard_when_probe_read_fails(self):
        calls = []
        with patch.object(sc, "get_clipboard", side_effect=["original", OSError("read refused")]), \
                patch.object(sc, "set_clipboard", side_effect=lambda value: calls.append(value)), \
                patch.object(sc, "list_windows", return_value=[self.win]), patch.object(sc.platform, "platform", return_value="test"), patch.object(sc.shutil, "which", return_value="tool"):
            args = types.SimpleNamespace(out=None, max_width=1280)
            with patch.object(sc, "sys") as fake_sys:
                fake_sys.version = "test"
                fake_sys.stdout = sys.stdout
                fake_sys.stderr = sys.stderr
                fake_sys.exit = lambda code: (_ for _ in ()).throw(SystemExit(code))
                with self.assertRaises(SystemExit):
                    sc.act_doctor(args)
        self.assertEqual(calls, ["screenctl-doctor café ★ 日本語 🚀", "original"])

    def test_mac_ids_survive_reordering_and_delimiter_titles(self):
        ns = self.mac_backend()
        rows = [[321, 'A\n#|\"', 0, 0, 200, 100], [321, 'B', 100, 0, 200, 100]]
        ns['_osa'] = Mock(side_effect=[subprocess.CompletedProcess([], 0, json.dumps(rows), ''),
                                       subprocess.CompletedProcess([], 0, json.dumps(rows[::-1]), '')])
        first, second = ns['list_windows'](), ns['list_windows']()
        self.assertEqual(first[0].id, second[1].id)
        self.assertEqual(first[0].title, rows[0][1])

    def test_mac_wrong_window_same_process_and_duplicates_refuse(self):
        ns = self.mac_backend()
        win = sc.Win(ns['_mac_id'](321, 'A'), 'A', 0, 0, 200, 100)
        ns['foreground_id'] = lambda: ns['_mac_id'](321, 'B')
        ns['list_windows'] = lambda: [win]
        self.assertFalse(ns['same_window'](win))
        ns['foreground_id'] = lambda: win.id
        self.assertTrue(ns['same_window'](win))
        ns['list_windows'] = lambda: [win, win]
        self.assertFalse(ns['same_window'](win))

    def test_mac_special_keys_use_codes_and_unknown_names_refuse(self):
        ns = self.mac_backend()
        osa = ns['_osa'] = Mock(return_value=subprocess.CompletedProcess([], 0, '', ''))
        ns['send_chord']('ctrl+enter')
        self.assertIn('key code 36 using {control down}', osa.call_args.args[0])
        ns['send_chord']('cmd+v')
        self.assertIn('keystroke "v" using {command down}', osa.call_args.args[0])
        osa.reset_mock()
        with self.assertRaises(SystemExit):
            ns['send_chord']('definitely-not-a-key')
        osa.assert_not_called()

    def test_mac_backend_errors_never_report_success(self):
        ns = self.mac_backend()
        ns['_osa'] = Mock(return_value=subprocess.CompletedProcess([], 1, '', 'permission refused'))
        for call in (lambda: ns['type_text']('test'), lambda: ns['send_chord']('enter'),
                     lambda: ns['list_windows'](), lambda: ns['foreground_id'](),
                     lambda: ns['raise_window'](sc.Win('321:QQ==', 'A', 0, 0, 200, 100))):
            with self.assertRaises(SystemExit):
                call()


if __name__ == '__main__':
    unittest.main()
