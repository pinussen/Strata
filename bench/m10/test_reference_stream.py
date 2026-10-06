"""Protocol checks for llama.cpp's separate finish and usage SSE chunks."""
import json
import unittest
from unittest.mock import patch
from run_reference_benchmark import request


class Stream:
    def __init__(self, chunks, done=True):
        self.lines = [b': keepalive', b''] + [b'data: ' + json.dumps(x).encode() for x in chunks]
        if done:
            self.lines.append(b'data: [DONE]')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_lines(self, **kwargs):
        return iter(self.lines)


class ReferenceStreamTests(unittest.TestCase):
    def chunks(self):
        return [
            {'choices': [{'delta': {'content': '323'}, 'finish_reason': None}]},
            {'choices': [{'delta': {}, 'finish_reason': 'stop'}]},
            {'choices': [], 'usage': {'completion_tokens': 1},
             'timings': {'predicted_per_second': 4.2}},
        ]

    def test_separate_finish_and_usage(self):
        with patch('run_reference_benchmark.requests.post', return_value=Stream(self.chunks())):
            row = request('http://localhost', {})
        self.assertEqual(row['content'], '323')
        self.assertEqual(row['finish_reason'], 'stop')
        self.assertEqual(row['final']['choices'], [])
        self.assertEqual(row['raw_chunks'], self.chunks())
        self.assertIsNotNone(row['first_token_s'])

    def test_length_is_recorded_without_claiming_complete(self):
        chunks = self.chunks()
        chunks[1]['choices'][0]['finish_reason'] = 'length'
        with patch('run_reference_benchmark.requests.post', return_value=Stream(chunks)):
            self.assertEqual(request('http://localhost', {})['finish_reason'], 'length')

    def test_truncated_stream_rejected(self):
        with patch('run_reference_benchmark.requests.post', return_value=Stream(self.chunks(), done=False)):
            with self.assertRaisesRegex(RuntimeError, 'Incomplete stream'):
                request('http://localhost', {})

    def test_engine_error_rejected(self):
        with patch('run_reference_benchmark.requests.post', return_value=Stream([{'error': 'engine failed'}])):
            with self.assertRaisesRegex(RuntimeError, 'engine failed'):
                request('http://localhost', {})


if __name__ == '__main__':
    unittest.main()
