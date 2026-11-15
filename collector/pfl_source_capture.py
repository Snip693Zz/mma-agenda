"""Capture PFL de diagnostic : pas de base de donnees ni publication."""
import datetime as dt
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

URLS = ('https://pflmma.com/events', 'https://pflmma.com/event/pfl-lyon',
        'https://pflmma.com/event/2026-chicago2')
MAX_BYTES = 5_000_000


def validate_url(url):
    p = urlsplit(url)
    if (p.scheme != 'https' or p.netloc not in ('pflmma.com', 'www.pflmma.com')
            or p.query or p.fragment
            or not re.fullmatch(r'/events/?|/event/[A-Za-z0-9-]+/?', p.path)):
        raise ValueError('URL PFL non autorisee')
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirection refusee : validation manuelle requise')


def fetch(url, opener=None):
    validate_url(url)
    opener = opener or build_opener(NoRedirect())
    request = Request(url, headers={'User-Agent': 'mma-agenda-source-diagnostic/1.0',
                                   'Accept': 'text/html', 'Accept-Encoding': 'identity'})
    with opener.open(request, timeout=20) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('Reponse HTTP inattendue')
        if response.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('Contenu non HTML')
        raw = response.read(MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES:
            raise ValueError('Taille de source invalide')
        charset = response.headers.get_content_charset() or 'utf-8'
        return raw, raw.decode(charset)


def run(output='reports/pfl-source-capture', fetcher=fetch, pause=time.sleep):
    try:
        from .pfl_source_probe import inspect_html
    except ImportError:
        from pfl_source_probe import inspect_html
    target = Path(output)
    target.mkdir(parents=True, exist_ok=True)
    reports = []
    for index, url in enumerate(URLS):
        if index:
            pause(2)
        item = {'source_url': url, 'collected_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'database_writes': False, 'automatic_publication': False}
        try:
            raw, html = fetcher(url)
            digest = hashlib.sha256(raw).hexdigest()
            filename = digest + '.html'
            target.joinpath(filename).write_bytes(raw)
            item.update(status='captured_unvalidated', raw_sha256=digest,
                        source_file=filename, byte_count=len(raw), diagnostic=inspect_html(html, url))
        except Exception as error:
            item.update(status='capture_failed', error_type=type(error).__name__, error=str(error)[:500])
        reports.append(item)
    target.joinpath('manifest.json').write_text(json.dumps({
        'schema_version': 1, 'mode': 'diagnostic_only', 'reports': reports,
        'database_writes': False, 'automatic_publication': False},
        ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if all(r['status'] == 'captured_unvalidated' for r in reports) else 2


if __name__ == '__main__':
    raise SystemExit(run())
