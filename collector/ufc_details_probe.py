"""Diagnostic UFC sans publication ni accès Supabase."""
import datetime as dt
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

URL = 'https://www.ufc.com/event/ufc-fight-night-november-21-2026'

class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []
    def nodes(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.nodes()
    def text(self):
        if self.tag in ('script', 'style'):
            return ''
        return ' '.join(' '.join(c.text() if isinstance(c, Node) else c for c in self.children).split())

class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in ('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'):
            self.stack.append(node)
    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, attrs))
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, text):
        self.stack[-1].children.append(text)

def inspect_html(html, address=URL):
    p = urlsplit(address)
    if p.scheme != 'https' or p.hostname not in ('www.ufc.com','ufc.com') or p.username or p.password or p.port not in (None,443) or not re.fullmatch(r'/event/[a-zA-Z0-9-]+/?', p.path) or p.query or p.fragment:
        raise ValueError('Fiche officielle UFC attendue')
    root = Tree(html).root
    nodes = list(root.nodes())
    signals = []
    for node in nodes:
        attrs = node.attrs
        identity = attrs.get('id','') + ' ' + attrs.get('class','')
        if 'data-timestamp' in attrs or re.search(r'card|prelim|hero|venue|location', identity, re.I):
            signals.append({'tag':node.tag,'id':attrs.get('id'),'class':attrs.get('class'),'timestamp':attrs.get('data-timestamp'),'text':node.text()[:2000]})
    return {'schema_version':1,'mode':'diagnostic_only','database_writes':False,'automatic_publication':False,'source_url':address,'source_sha256':hashlib.sha256(html.encode('utf-8')).hexdigest(),'headings':[{'tag':n.tag,'text':n.text()} for n in nodes if n.tag in ('h1','h2','h3')],'signals':signals,'fight_rows':sum('c-listing-fight' in n.attrs.get('class','').split() for n in nodes),'warning':'Signaux bruts : aucune affectation de carte ou horaire validée.'}

def main():
    try:
        from .discover import Client
    except ImportError:
        from discover import Client
    target = Path('reports/ufc-details-probe')
    target.mkdir(parents=True, exist_ok=True)
    try:
        html = Client('https://www.ufc.com/events').get(URL)
        report = inspect_html(html)
        report['collected_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        target.joinpath('source.html').write_text(html, encoding='utf-8')
        report['status'] = 'captured' if report['fight_rows'] else 'needs_review'
        code = 0 if report['fight_rows'] else 2
    except Exception as error:
        report = {'status':'failed','database_writes':False,'automatic_publication':False,'source_url':URL,'error_type':type(error).__name__}
        code = 2
    target.joinpath('report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return code

if __name__ == '__main__':
    raise SystemExit(main())
