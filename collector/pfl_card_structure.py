"""PFL card extraction without network access or publication."""
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, unquote, quote

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}
LABEL_PATTERN = re.compile(r'\b(?:MORE\s+INFO|VIEW\s+FIGHTER\s+PROFILE|VIEW\s+PROFILE|FIGHTER\s+PROFILE|MORE|INFO|VIEW|PROFILE)\b', re.IGNORECASE)


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children, self.closed, self.text = tag, dict(attrs), [], False, ''
        self.content = []

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
        parent = self.stack[-1]
        parent.children.append(node)
        parent.content.append(('node', node))
        if tag in VOID:
            node.closed = True
        else:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, attrs)
        node.closed = True
        parent = self.stack[-1]
        parent.children.append(node)
        parent.content.append(('node', node))

    def handle_endtag(self, tag):
        if len(self.stack) > 1 and self.stack[-1].tag == tag:
            self.stack.pop().closed = True
        elif tag not in VOID:
            self.malformed = True

    def handle_data(self, data):
        parent = self.stack[-1]
        parent.text += data
        parent.content.append(('text', data))


def _readable_name(node):
    parts = []
    def visit(current):
        for kind, value in current.content:
            if kind == 'text':
                parts.append(value)
            else:
                visit(value)
    visit(node)
    return ' '.join(filter(None, (' '.join(LABEL_PATTERN.sub(' ', part).split()) for part in parts)))


def _fighter_url(href, source_url):
    url = urlsplit(urljoin(source_url, href or ''))
    path = unicodedata.normalize('NFC', unquote(url.path, errors='strict'))
    if not path.startswith('/fighter/'):
        return None
    slug = path[len('/fighter/'):].removesuffix('/')
    if (url.scheme != 'https' or url.netloc not in ('pflmma.com', 'www.pflmma.com')
            or url.query or url.fragment or not slug
            or not all(c.isalnum() or c == '-' for c in slug)):
        raise ValueError('Invalid fighter URL')
    return 'https://pflmma.com/fighter/' + quote(slug, safe='-')


def extract_pairs(html, source_url, allow_fragment=False):
    source = urlsplit(source_url)
    if (source.scheme != 'https' or source.netloc not in ('pflmma.com', 'www.pflmma.com')
            or source.query or (not allow_fragment and source.fragment)
            or not re.fullmatch(r'/event/[a-zA-Z0-9-]+/?', source.path)):
        raise ValueError('Fiche PFL officielle requise')
    result = {'status': 'review_required', 'reason': '', 'pairs': [], 'row_count': 0,
              'duplicate_rows': 0, 'automatic_publication': False, 'database_writes': False,
              'source_url': source_url, 'event_identity_validated': False}
    tree = Tree(html)
    components = [n for n in tree.root.walk() if n.attrs.get('id') == 'fight_card_component']
    if tree.malformed or not components or not components[0].closed:
        result['reason'] = 'missing_ambiguous_or_incomplete_component'
        return result
    component = components[0]
    if any(n is not component and n.attrs.get('id') == 'fight_card_component' for n in component.walk()):
        result['reason'] = 'nested_card_component'
        return result
    if len(components) != 1:
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
        fighters, count = [], 0
        for node in row.walk():
            if node is not row and 'matchupRow' in (node.attrs.get('class') or '').split():
                result['reason'] = 'nested_rows'
                return result
            if node.tag != 'a':
                continue
            try:
                canonical = _fighter_url(node.attrs.get('href'), source_url)
            except ValueError:
                result['reason'] = 'invalid_fighter_url'
                return result
            if canonical is None:
                continue
            count += 1
            if canonical not in fighters:
                fighters.append(canonical)
        if len(fighters) == 1 and count > 1:
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


def _row_names(row, source_url):
    previous = {}
    for parent in row.walk():
        for index, child in enumerate(parent.children):
            if index:
                previous[child] = parent.children[index - 1]
    direct, headings = {}, {}
    for node in row.walk():
        if node.tag != 'a':
            continue
        canonical = _fighter_url(node.attrs.get('href'), source_url)
        if canonical is None:
            continue
        name = _readable_name(node)
        if name:
            direct.setdefault(canonical, set()).add(name)
        else:
            sibling = previous.get(node)
            if sibling is not None and sibling.tag == 'h4' and sibling.closed:
                name = _readable_name(sibling)
                if name:
                    headings.setdefault(canonical, set()).add(name)
    fighters = {}
    for canonical in direct.keys() | headings.keys():
        explicit = direct.get(canonical, set())
        if len(explicit) > 1:
            return {}
        options = explicit | headings.get(canonical, set())
        full = max(options, key=len)
        if any(full.casefold() != name.casefold() and not full.casefold().endswith(' ' + name.casefold()) for name in options):
            return {}
        fighters[canonical] = full
    return fighters


def extract_structured_fights(html, source_url, allow_fragment=False):
    """Only return complete cards; never infer names from fighter slugs."""
    try:
        validation = extract_pairs(html, source_url, allow_fragment=allow_fragment)
        if validation.get('status') != 'candidate_pairs' or not validation.get('pairs'):
            return []
        tree = Tree(html)
        component = next(n for n in tree.root.walk() if n.attrs.get('id') == 'fight_card_component')
        fights, seen = [], set()
        for row in [n for n in component.walk() if 'matchupRow' in (n.attrs.get('class') or '').split()]:
            fighters = _row_names(row, source_url)
            if len(fighters) != 2:
                return []
            pair = []
            for node in row.walk():
                if node.tag == 'a':
                    canonical = _fighter_url(node.attrs.get('href'), source_url)
                    if canonical and canonical not in pair:
                        pair.append(canonical)
            if len(pair) != 2 or set(pair) != set(fighters):
                return []
            key = tuple(sorted(pair))
            if key in seen:
                continue
            seen.add(key)
            a, b = pair
            if fighters[a].casefold() == fighters[b].casefold():
                return []
            fights.append({'fighter_a': fighters[a], 'fighter_b': fighters[b],
                           'fighter_a_url': a, 'fighter_b_url': b,
                           'card_position': 0, 'position': len(fights), 'card_source': source_url})
        return fights
    except (TypeError, ValueError, StopIteration):
        return []
