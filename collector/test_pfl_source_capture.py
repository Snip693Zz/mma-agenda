"""Tests de capture sans reseau."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from email.message import Message
from pfl_source_capture import fetch, run, validate_url, NoRedirect


class PFLCaptureTests(unittest.TestCase):
    def test_url_allowlist(self):
        self.assertEqual(validate_url('https://pflmma.com/events'), 'https://pflmma.com/events')
        for url in ('http://pflmma.com/events', 'https://evil.example/events',
                    'https://user@pflmma.com/events', 'https://pflmma.com/event/../news',
                    'https://pflmma.com/events?q=x'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_redirect_is_refused(self):
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.example')

    def test_fetch_rejects_non_html_and_empty_body(self):
        for kind, body in (('application/json', b'{}'), ('text/html', b'')):
            response = Mock(status=200)
            response.geturl.return_value = 'https://pflmma.com/events'
            response.headers = Message()
            response.headers['Content-Type'] = kind
            response.read.return_value = body
            opener = Mock()
            opener.open.return_value.__enter__ = Mock(return_value=response)
            opener.open.return_value.__exit__ = Mock(return_value=False)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                fetch('https://pflmma.com/events', opener)

    def test_capture_preserves_bytes_and_never_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = b'<h1>Example</h1>'
            self.assertEqual(run(tmp, lambda url: (raw, raw.decode()), lambda seconds: None), 0)
            manifest = json.loads(Path(tmp, 'manifest.json').read_text())
            self.assertFalse(manifest['automatic_publication'])
            for item in manifest['reports']:
                self.assertEqual(item['status'], 'captured_unvalidated')
                self.assertEqual(Path(tmp, item['source_file']).read_bytes(), raw)
                self.assertEqual(item['diagnostic']['status'], 'unvalidated')

    def test_failure_is_recorded(self):
        def fail(url):
            raise ValueError('unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run(tmp, fail, lambda seconds: None), 2)
            manifest = json.loads(Path(tmp, 'manifest.json').read_text())
            self.assertTrue(all(x['status'] == 'capture_failed' for x in manifest['reports']))
