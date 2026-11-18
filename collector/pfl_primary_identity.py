"""Conservative primary-heading check, not full event validation."""
import re
import unicodedata
from html import unescape
try:
    from .pfl_section_candidates import TextTree, heading_text
except ImportError:
    from pfl_section_candidates import TextTree, heading_text


def _og_title(html):
    match = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html or '', re.IGNORECASE)
    if not match:
        match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', html or '', re.IGNORECASE)
    return match.group(1).strip() if match else ''


def _normalize(value):
    value = unescape(value or '')
    value = re.sub(r'\s*\|\s*Professional Fighters League\s*$', '', value, flags=re.IGNORECASE)
    value = ''.join(c for c in unicodedata.normalize('NFD', value) if not unicodedata.combining(c))
    return ' '.join(value.split()).casefold()


def _matches(observed, expected):
    return bool(observed) and (observed == expected or (len(observed) >= 3 and expected.startswith(observed + ' ')))


def primary_identity_matches(html, event):
    if not isinstance(html, str) or not isinstance(event, dict):
        return False
    title = event.get('title')
    if not isinstance(title, str) or len(title.strip()) < 3:
        return False
    tree = TextTree(html)
    if tree.malformed or len(tree.stack) != 1:
        return False
    excluded = {'header', 'nav', 'footer', 'aside', 'script', 'style', 'template'}
    def visible(node):
        if node.tag in excluded:
            return
        yield node
        for child in node.children:
            yield from visible(child)
    mains = [n for n in visible(tree.root) if n.tag == 'main']
    if len(mains) > 1:
        return False
    scope = mains[0] if mains else tree.root
    nodes = list(visible(scope))
    headings = [n for n in nodes if n.tag == 'h1']
    title_norm = _normalize(title)
    if len(headings) == 1:
        return _matches(_normalize(heading_text(headings[0])), title_norm)
    if headings:
        return False
    og_norm = _normalize(_og_title(html))
    secondary = [_normalize(heading_text(n)) for n in nodes if n.tag == 'h2']
    if secondary:
        matching = [value for value in secondary if _matches(value, title_norm)]
        if len(matching) != 1 or len(matching[0].split()) < 2:
            return False
        if og_norm:
            return matching[0] == og_norm
        # Only an absent/empty OG title permits this corroborating fallback.
        titles = [n for n in visible(tree.root) if n.tag == 'title']
        if len(titles) != 1:
            return False
        return matching[0] == _normalize(heading_text(titles[0]))
    return _matches(og_norm, title_norm)
