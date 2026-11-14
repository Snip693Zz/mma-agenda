"""Diagnostic PFL hors ligne : aucun reseau, aucune publication."""
import argparse
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit


def official_url(value):
    p = urlsplit(value)
    if (p.scheme != 'https' or p.hostname not in ('pflmma.com', 'www.pflmma.com')
            or p.username or p.password or p.port not in (None, 443)
            or p.query or p.fragment
            or not (p.path == '/events' or p.path.startswith('/event/'))):
        raise ValueError('URL de calendrier ou fiche PFL officielle attendue')
    return value


class Probe(HTMLParser):
    def __init__(self, address):
        super().__init__(convert_charrefs=True)
        self.address, self.links, self.headings, self.scripts = address, set(), [], []
        self.heading, self.parts = None, []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a':
            candidate = urljoin(self.address, attrs.get('href', ''))
            try:
                official_url(candidate)
                if urlsplit(candidate).path.startswith('/event/'):
                    self.links.add(candidate)
            except ValueError:
                pass
        if tag in ('h1', 'h2', 'h3', 'h4'):
            self.heading, self.parts = tag, []
        if tag == 'script':
            self.scripts.append({k: attrs[k] for k in ('type', 'src', 'id') if k in attrs})

    def handle_data(self, data):
        if self.heading:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == self.heading:
            self.headings.append({'tag': tag, 'text': ' '.join(' '.join(self.parts).split())})
            self.heading, self.parts = None, []


def inspect_html(html, address):
    official_url(address)
    probe = Probe(address)
    probe.feed(html)
    probe.close()
    return {'schema_version': 1, 'mode': 'diagnostic_only',
            'database_writes': False, 'automatic_publication': False,
            'source_url': address, 'source_sha256': hashlib.sha256(html.encode('utf-8')).hexdigest(),
            'headings': probe.headings, 'event_links': sorted(probe.links),
            'scripts': probe.scripts, 'status': 'unvalidated',
            'warning': 'Signaux bruts uniquement : aucune identite, date ou carte validee.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', default='reports/pfl-source-probe.json')
    args = parser.parse_args()
    html = Path(args.html).read_text(encoding='utf-8')
    report = inspect_html(html, args.url)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
