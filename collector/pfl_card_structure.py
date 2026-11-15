"""Paires PFL structurelles hors ligne ; aucune publication ni resolution de noms."""
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


def extract_pairs(html, source_url):
    source = urlsplit(source_url)
    if (source.scheme != 'https' or source.netloc not in ('pflmma.com', 'www.pflmma.com')
            or source.query or source.fragment or not re.fullmatch(r'/event/[a-zA-Z0-9-]+/?', source.path)):
        raise ValueError('Fiche PFL officielle requise')
    result = {'status': 'review_required', 'reason': '', 'pairs': [], 'row_count': 0,
              'duplicate_rows': 0, 'automatic_publication': False, 'database_writes': False,
              'source_url': source_url, 'event_identity_validated': False}
    tree = Tree(html)
    components = [n for n in tree.root.walk() if n.attrs.get('id') == 'fight_card_component']
    if tree.malformed or len(components) != 1 or not components[0].closed:
        result['reason'] = 'missing_ambiguous_or_incomplete_component'
        return result
    rows = [n for n in components[0].walk() if 'matchupRow' in (n.attrs.get('class') or '').split()]
    result['row_count'] = len(rows)
    if not rows:
        result['reason'] = 'no_structured_rows'
        return result
    pairs, seen = [], set()
    for row in rows:
        fighters = []
        if not row.closed:
            result['reason'] = 'incomplete_row'
            return result
        for node in row.walk():
            if node is not row and 'matchupRow' in (node.attrs.get('class') or '').split():
                result['reason'] = 'nested_rows'
                return result
            if node.tag != 'a':
                continue
            url = urlsplit(urljoin(source_url, node.attrs.get('href') or ''))
            if not re.fullmatch(r'/fighter/[a-zA-Z0-9-]+/?', url.path):
                continue
            if url.scheme != 'https' or url.netloc not in ('pflmma.com', 'www.pflmma.com') or url.query or url.fragment:
                result['reason'] = 'invalid_fighter_url'
                return result
            canonical = 'https://pflmma.com' + url.path.rstrip('/')
            if canonical not in fighters:
                fighters.append(canonical)
        if len(fighters) != 2:
            result['reason'] = 'ambiguous_fighter_pair'
            return result
        key = tuple(sorted(fighters))
        if key in seen:
            result['duplicate_rows'] += 1
            continue
        seen.add(key)
        pairs.append({'fighter_a_url': fighters[0], 'fighter_b_url': fighters[1]})
    result.update(status='candidate_pairs', reason='identity_names_and_card_sections_not_validated', pairs=pairs)
    return result
