"""Conservative primary-heading check, not full event validation."""
import re
try:
    from .pfl_section_candidates import TextTree, heading_text
except ImportError:
    from pfl_section_candidates import TextTree, heading_text


def _og_title(html):
    match = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html or '', re.IGNORECASE)
    if not match:
        match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']', html or '', re.IGNORECASE)
    return match.group(1).strip() if match else ''


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
    headings = [n for n in visible(scope) if n.tag == 'h1']
    normalize = lambda text: ' '.join(text.split()).casefold()
    title_norm = normalize(title)
    if len(headings) == 1:
        heading_norm = normalize(heading_text(headings[0]))
        return heading_norm == title_norm or (len(heading_norm) >= 3 and title_norm.startswith(heading_norm))
    if len(headings) == 0:
        og_norm = normalize(_og_title(html))
        return bool(og_norm) and (og_norm == title_norm or (len(og_norm) >= 3 and title_norm.startswith(og_norm)))
    return False
