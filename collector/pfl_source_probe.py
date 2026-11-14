"""Diagnostic PFL hors ligne : aucun reseau, aucune publication."""
import argparse
import hashlib
import json
import re
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
        self.jsonld, self.script_parts = [], None

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
            if attrs.get('type', '').lower().strip() == 'application/ld+json':
                self.script_parts = []

    def handle_data(self, data):
        if self.script_parts is not None:
            self.script_parts.append(data)
        elif self.heading:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.script_parts is not None:
            raw = ''.join(self.script_parts)
            self.jsonld.append({'text': raw[:3500], 'truncated': len(raw) > 3500})
            self.script_parts = None
        if tag == self.heading:
            self.headings.append({'tag': tag, 'text': ' '.join(' '.join(self.parts).split())})
            self.heading, self.parts = None, []


def inspect_html(html, address):
    official_url(address)
    probe = Probe(address)
    probe.feed(html)
    probe.close()
    is_event = urlsplit(address).path.startswith('/event/')
    samples = []
    if is_event:
        patterns = (r'<[^>]*(?:fighter|bout|fight[-_]card)[^>]*>',
                    r'<[^>]*(?:datetime|og:title|canonical|event[-_]date)[^>]*>')
        offsets = set()
        for pattern in patterns:
            for match in re.finditer(pattern, html, re.IGNORECASE):
                if any(abs(match.start() - previous) < 500 for previous in offsets):
                    continue
                offsets.add(match.start())
                samples.append({'offset': match.start(), 'html': html[max(0, match.start()-100):match.start()+900]})
                if len(samples) == 6:
                    break
            if len(samples) == 6:
                break
    return {'schema_version': 2, 'mode': 'diagnostic_only',
            'database_writes': False, 'automatic_publication': False,
            'source_url': address, 'source_sha256': hashlib.sha256(html.encode('utf-8')).hexdigest(),
            'heading_count': len(probe.headings), 'event_link_count': len(probe.links),
            'headings': [{'tag': h['tag'], 'text': h['text'][:250]} for h in probe.headings[:20]],
            'event_links': sorted(probe.links)[:40], 'scripts': probe.scripts[:20],
            'jsonld_samples': probe.jsonld[:2] if is_event else [],
            'html_samples': samples, 'status': 'unvalidated',
            'warning': 'Extraits bornes, potentiellement incomplets : aucune identite, date ou carte validee.'}


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
