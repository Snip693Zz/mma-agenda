"""Conservative primary-heading check, not full event validation."""
try:
    from .pfl_section_candidates import TextTree, heading_text
except ImportError:
    from pfl_section_candidates import TextTree, heading_text


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
    if len(headings) != 1:
        return False
    normalize = lambda text: ' '.join(text.split()).casefold()
    heading_norm = normalize(heading_text(headings[0]))
    title_norm = normalize(title)
    return heading_norm == title_norm or (len(heading_norm) >= 3 and title_norm.startswith(heading_norm))