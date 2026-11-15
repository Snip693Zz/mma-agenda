"""Identite, noms et sections PFL hors ligne ; aucune publication ni resolution automatique."""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children, self.closed = tag, dict(attrs), [], False

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()


class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack, self.malformed = [self.root], False
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag in VOID:
            node.closed = True
        else:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, attrs)
        node.closed = True
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        if len(self.stack) > 1 and self.stack[-1].tag == tag:
            self.stack.pop().closed = True
        elif tag not in VOID:
            self.malformed = True


def _official_event_url(source_url):
    source = urlsplit(source_url)
    if (source.scheme != 'https' or source.netloc not in ('pflmma.com', 'www.pflmma.com')
            or source.query or source.fragment or not re.fullmatch(r'/event/[a-zA-Z0-9-]+/?', source.path)):
        raise ValueError('Fiche PFL officielle requise')
    return source


def _text(node):
    return ' '.join(n for n in node.children if isinstance(n, str)).strip()


def _jsonld_events(tree):
    events = []
    for node in tree.root.walk():
        if node.tag != 'script' or node.attrs.get('type') != 'application/ld+json':
            continue
        try:
            data = json.loads(_text(node))
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict):
            for item in data.get('@graph', []):
                if item.get('@type') == 'SportsEvent':
                    events.append(item)
    return events


def _fighter_names(row, source_url):
    names, links = [], []
    for node in row.walk():
        if node.tag != 'a':
            continue
        url = urlsplit(urljoin(source_url, node.attrs.get('href') or ''))
        if not re.fullmatch(r'/fighter/[a-zA-Z0-9-]+/?', url.path):
            continue
        if url.scheme != 'https' or url.netloc not in ('pflmma.com', 'www.pflmma.com') or url.query or url.fragment:
            return [], []
        canonical = 'https://pflmma.com' + url.path.rstrip('/')
        if canonical not in links:
            links.append(canonical)
        text = _text(node)
        if text and text.upper() != 'MORE INFO':
            names.append(text)
    return names, links


def extract_event(html, source_url):
    source = _official_event_url(source_url)
    result = {'status': 'review_required', 'reason': '', 'source_url': source_url,
              'event_identity': {'status': 'review_required', 'reason': '', 'event_url': source_url,
                                 'title': '', 'date': '', 'jsonld_url': '', 'jsonld_start_date': ''},
              'sections': [], 'pairs': [], 'row_count': 0, 'duplicate_rows': 0,
              'automatic_publication': False, 'database_writes': False,
              'event_identity_validated': False, 'names_resolved': False}
    tree = Tree(html)
    if tree.malformed:
        result['reason'] = 'malformed_html'
        return result
    matching = [e for e in _jsonld_events(tree) if e.get('url') in (source_url, source_url.rstrip('/') + '/')]
    if len(matching) != 1:
        result['event_identity']['reason'] = 'missing_or_ambiguous_jsonld_event'
        return result
    event = matching[0]
    title, date = event.get('name') or '', event.get('startDate') or ''
    if not title or not date:
        result['event_identity']['reason'] = 'incomplete_jsonld_event'
        return result
    result['event_identity'].update(status='candidate_identity', title=title, date=date,
                                    jsonld_url=event.get('url') or '', jsonld_start_date=date)
    components = [n for n in tree.root.walk() if n.attrs.get('id') == 'fight_card_component']
    if len(components) != 1 or not components[0].closed:
        result['reason'] = 'missing_ambiguous_or_incomplete_component'
        return result
    current = 'unassigned'
    for heading in [n for n in components[0].walk() if n.tag == 'h2' and _text(n)]:
        text = _text(heading)
        if re.search(r'\bmain card\b', text, re.I):
            current = 'main_card'
        elif re.search(r'\bearly card\b|\bpreliminary\b|\bprelims\b', text, re.I):
            current = 'early_card'
        else:
            current = 'unassigned'
        result['sections'].append({'heading': text, 'section': current})
    rows = [n for n in components[0].walk() if 'matchupRow' in (n.attrs.get('class') or '').split()]
    result['row_count'] = len(rows)
    if not rows:
        result['reason'] = 'no_structured_rows'
        return result
    pairs, seen = [], set()
    for row in rows:
        if not row.closed:
            result['reason'] = 'incomplete_row'
            return result
        for node in row.walk():
            if node is not row and 'matchupRow' in (node.attrs.get('class') or '').split():
                result['reason'] = 'nested_rows'
                return result
        names, links = _fighter_names(row, source_url)
        if len(links) != 2 or len(names) < 2:
            result['reason'] = 'ambiguous_fighter_pair'
            return result
        key = tuple(sorted(links))
        if key in seen:
            result['duplicate_rows'] += 1
            continue
        seen.add(key)
        pairs.append({'fighter_a_url': links[0], 'fighter_b_url': links[1],
                      'fighter_a_display_name': names[0], 'fighter_b_display_name': names[1],
                      'section': current})
    result.update(status='candidate_event', reason='card_sections_not_validated', pairs=pairs)
    return result
