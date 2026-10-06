"""Exercise resumable downloads without a network or model files."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import download_manifest


class Response(io.BytesIO):
    def __init__(self, body, start=0, status=206, fail_after_read=False):
        super().__init__(body)
        self.status = status
        self.headers = {'Content-Range': f'bytes {start}-{start+len(body)-1}/*'}
        self.fail_after_read = fail_after_read

    def read(self, size=-1):
        if self.fail_after_read and self.tell():
            raise ConnectionResetError('injected disconnect')
        return super().read(size)


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.body = bytes(range(256)) * 64
        self.name = 'test.gguf'
        self.final = self.root/self.name
        self.partial = self.root/(self.name+'.part')
        self.marker = self.root/(self.name+'.sha256')
        self.state = self.root/'state.json'
        self.sha = hashlib.sha256(self.body).hexdigest()
        manifest = dict(repo='test/repo', revision='pinned', files=[dict(
            rfilename='Q8_0/'+self.name, size=len(self.body), lfs={'sha256': self.sha})])
        self.manifest = self.root/'manifest.json'
        self.manifest.write_text(json.dumps(manifest))

    def run_download(self, responses):
        args = ['download_manifest.py', '--manifest', str(self.manifest), '--variant', 'Q8_0',
                '--dest', str(self.root), '--state', str(self.state)]
        with patch('sys.argv', args), patch.object(download_manifest.urllib.request, 'urlopen',
                side_effect=responses) as fetch, patch.object(download_manifest.time, 'sleep'), \
                contextlib.redirect_stdout(io.StringIO()):
            download_manifest.main()
        return fetch

    def test_resume_and_verified_skip(self):
        self.partial.write_bytes(self.body[:101])
        fetch = self.run_download([Response(self.body[101:], start=101)])
        self.assertEqual(fetch.call_args.args[0].get_header('Range'), 'bytes=101-')
        self.assertEqual(self.final.read_bytes(), self.body)
        self.assertEqual(self.marker.read_text().strip(), self.sha)
        self.assertFalse(self.partial.exists())
        self.assertEqual(json.loads(self.state.read_text())['stage'], 'complete')
        self.assertEqual(self.run_download([]).call_count, 0)

    def test_disconnect_resumes_new_range(self):
        fetch = self.run_download([Response(self.body[:500], fail_after_read=True),
                                   Response(self.body[500:], start=500)])
        self.assertEqual([c.args[0].get_header('Range') for c in fetch.call_args_list],
                         ['bytes=0-', 'bytes=500-'])
        self.assertEqual(self.final.read_bytes(), self.body)

    def test_ignored_range_preserves_partial(self):
        self.partial.write_bytes(self.body[:101])
        with self.assertRaisesRegex(RuntimeError, 'ignored resume range'):
            self.run_download([Response(self.body, status=200)])
        self.assertEqual(self.partial.read_bytes(), self.body[:101])
        self.assertFalse(self.final.exists())
        self.assertEqual(json.loads(self.state.read_text())['stage'], 'failed')

    def test_hash_mismatch_never_marks_complete(self):
        with self.assertRaisesRegex(RuntimeError, 'SHA256 mismatch'):
            self.run_download([Response(b'X'+self.body[1:])])
        self.assertTrue(self.partial.exists())
        self.assertFalse(self.final.exists())
        self.assertFalse(self.marker.exists())
        self.assertEqual(json.loads(self.state.read_text())['stage'], 'failed')


if __name__ == '__main__':
    unittest.main()
