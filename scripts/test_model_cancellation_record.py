"""Transport bookkeeping tests only; fixtures are never SVA experiment data."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from obligation_continuation_interface import stream_call


class InterruptedResponse:
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def __iter__(self):
        yield b'{"message":{"content":"partial"},"done":false}\n'
        raise KeyboardInterrupt


class CancellationRecord(unittest.TestCase):
    def test_partial_response_preserved_without_inventing_final_usage(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/'call'
            tags=io.BytesIO(b'{"models":[{"name":"fixture-only","digest":"unit-digest"}]}')
            def dump(path,value):path.write_text(json.dumps(value))
            with patch('obligation_continuation_interface.urllib.request.urlopen',
                       side_effect=[tags,InterruptedResponse()]):
                with self.assertRaises(KeyboardInterrupt):
                    stream_call({'model':'fixture-only'},folder,dump,'unit-digest')
            result=json.loads((folder/'transport_result.json').read_text())
            raw=json.loads((folder/'response.raw.json').read_text())
            self.assertEqual(result['status'],'cancelled_by_operator')
            self.assertIsNone(result['prompt_tokens'])
            self.assertIsNone(result['completion_tokens'])
            self.assertIsNone(raw['service_done'])
            self.assertEqual(raw['message']['content'],'partial')
            self.assertTrue((folder/'response.stream.jsonl').exists())


if __name__=='__main__':unittest.main()
