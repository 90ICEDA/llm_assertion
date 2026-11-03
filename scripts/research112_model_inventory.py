"""Read-only model inventory. No generation, RTL upload, redirects or retries."""
import argparse
import json
import time
import urllib.request
from pathlib import Path
from research20_remote import _NoRedirect, safe_error

ROOT = Path(__file__).resolve().parents[1]
REMOTE = 'https://api.highwayapi.ai/openai/models'
LOCAL = 'http://127.0.0.1:11434/api/tags'


def inventory(out):
    out.mkdir(parents=True, exist_ok=False)
    report = dict(generation_calls=0, project_content_sent=False, retries=0, queries=[])
    for kind, url in [('remote', REMOTE), ('local', LOCAL)]:
        started = time.time()
        item = dict(kind=kind, endpoint=url, started=started, http_requests=0)
        secret = ''
        try:
            headers = {'Accept': 'application/json'}
            if kind == 'remote':
                secret = (ROOT / '.secrets/qwen_api_key.txt').read_text(encoding='utf-8-sig').strip()
                if not secret:
                    raise ValueError('missing credential')
                headers['Authorization'] = 'Bearer ' + secret
            request = urllib.request.Request(url, headers=headers, method='GET')
            item['http_requests'] = 1
            with urllib.request.build_opener(_NoRedirect()).open(request, timeout=45 if kind == 'remote' else 5) as response:
                data = json.load(response)
            entries = data.get('data' if kind == 'remote' else 'models', [])
            allowed = ('id', 'owned_by', 'context_length', 'max_context_length', 'max_tokens') if kind == 'remote' else ('name', 'model', 'size')
            models = [{k: v for k, v in e.items() if k in allowed and isinstance(v, (str, int, float))}
                      for e in entries if isinstance(e, dict)]
            # Never archive raw response bodies or any echoed credential.
            clean = json.dumps(models, ensure_ascii=False)
            if secret:
                clean = clean.replace(secret, '[REDACTED]')
            item.update(status='completed', models=json.loads(clean), entry_count=len(models))
        except Exception as exc:
            item.update(status='failed', error=safe_error(exc))
        item['wall_seconds'] = time.time() - started
        report['queries'].append(item)
    (out / 'inventory.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    inventory(ap.parse_args().out.resolve())
