"""Paires PFL structurelles hors ligne ; aucune publication ni resolution de noms."""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children, self.closed, self.text = tag, dict(attrs), [], False, ''

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

    def handle_data(self, data):
        self.stack[-1].text += data


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
    if tree.malformed:
        result['reason'] = 'missing_ambiguous_or_incomplete_component'
        return result
    if not components:
        result['reason'] = 'missing_ambiguous_or_incomplete_component'
        return result
    component = components[0]
    if not component.closed:
        result['reason'] = 'missing_ambiguous_or_incomplete_component'
        return result
    nested_components = [n for n in component.walk() if n is not component and n.attrs.get('id') == 'fight_card_component']
    if nested_components:
        result['reason'] = 'nested_card_component'
        return result
    if len(components) > 1:
        result['reason'] = 'missing_ambiguous_or_incomplete_component'
        return result
    rows = [n for n in component.walk() if 'matchupRow' in (n.attrs.get('class') or '').split()]
    result['row_count'] = len(rows)
    if not rows:
        result['reason'] = 'no_structured_rows'
        return result
    pairs, seen = [], set()
    for row in rows:
        if not row.closed:
            result['reason'] = 'incomplete_row'
            return result
        fighters = []
        fighter_link_count = 0
        for node in row.walk():
            if node is not row and 'matchupRow' in (node.attrs.get('class') or '').split():
                result['reason'] = 'nested_rows'
                return result
            if node.tag != 'a':
                continue
            url = urlsplit(urljoin(source_url, node.attrs.get('href') or ''))
            if not re.fullmatch(r'/fighter/[a-zA-Z0-9-]+/?', url.path):
                continue
            if (url.scheme != 'https' or url.netloc not in ('pflmma.com', 'www.pflmma.com')
                    or url.query or url.fragment):
                result['reason'] = 'invalid_fighter_url'
                return result
            fighter_link_count += 1
            canonical = 'https://pflmma.com' + url.path.rstrip('/')
            if canonical not in fighters:
                fighters.append(canonical)
        if len(fighters) == 1 and fighter_link_count > 1:
            result['reason'] = 'duplicate_fighter_in_row'
            return result
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


def extract_structured_fights(html, source_url):
    """Retourne uniquement les combats issus d'une carte structurellement valide."""
    try:
        validation = extract_pairs(html, source_url)
    except (TypeError, ValueError):
        return []
    if validation.get('status') != 'candidate_pairs' or not validation.get('pairs'):
        return []
    tree = Tree(html)
    components = [n for n in tree.root.walk() if n.attrs.get('id') == 'fight_card_component']
    if len(components) != 1:
        return []
    fights, seen = [], set()
    for row in [n for n in components[0].walk() if 'matchupRow' in (n.attrs.get('class') or '').split()]:
        fighters = {}
        for node in row.walk():
            if node.tag != 'a':
                continue
            url = urlsplit(urljoin(source_url, node.attrs.get('href') or ''))
            if not re.fullmatch(r'/fighter/[a-zA-Z0-9-]+/?', url.path):
                continue
            if (url.scheme != 'https' or url.netloc not in ('pflmma.com', 'www.pflmma.com')
                    or url.query or url.fragment):
                return []
            canonical = 'https://pflmma.com' + url.path.rstrip('/')
            name = re.sub(r'\s+', ' ', (node.text or '')).strip()
            if canonical not in fighters and name:
                fighters[canonical] = name
        if len(fighters) != 2:
            return []
        fighter_a_url, fighter_b_url = list(fighters)
        key = tuple(sorted((fighter_a_url, fighter_b_url)))
        if key in seen:
            continue
        seen.add(key)
        fights.append({
            'fighter_a': fighters[fighter_a_url],
            'fighter_b': fighters[fighter_b_url],
            'fighter_a_url': fighter_a_url,
            'fighter_b_url': fighter_b_url,
            'card_position': 0,
            'position': len(fights),
        })
    return fights
