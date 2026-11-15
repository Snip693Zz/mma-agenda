"""Offline section candidates only; never validates an event or publishes data."""
import re
from collections import Counter
from pfl_card_structure import Tree, extract_pairs


class TextTree(Tree):
    def handle_data(self, data):
        node = self.stack[-1]
        node.text = getattr(node, 'text', '') + data


def heading_text(node):
    if node.tag in ('a', 'script', 'style'):
        return ''
    return ' '.join([getattr(node, 'text', '')] + [heading_text(c) for c in node.children])


def diagnose_sections(html, source_url):
    structural = extract_pairs(html, source_url)
    result = dict(status='review_required', diagnostic_only=True,
                  automatic_publication=False, database_writes=False,
                  event_identity_validated=False, source_url=source_url, rows=[])
    if structural['status'] != 'candidate_pairs':
        result['reason'] = structural['reason']
        return result
    tree = TextTree(html)
    component = next(n for n in tree.root.walk() if n.attrs.get('id') == 'fight_card_component')
    ids = Counter(n.attrs['id'] for n in component.walk() if n.attrs.get('id'))

    def visit(parent):
        current, evidence = 'unassigned', None
        for node in parent.children:
            classes = (node.attrs.get('class') or '').split()
            if 'matchupRow' in classes:
                result['rows'].append(dict(row_id=node.attrs.get('id'), section=current, evidence=evidence))
                continue
            if re.fullmatch(r'h[1-6]', node.tag):
                text = ' '.join(heading_text(node).split())
                main = bool(re.search(r'\bmain\s+card\b', text, re.I))
                early = bool(re.search(r'\b(?:early\s+card|prelims?|preliminary\s+card)\b', text, re.I))
                identifier = node.attrs.get('id')
                conflict = ((identifier == 'main-tab' and early) or
                            (identifier == 'prelim-tab' and main) or
                            (identifier and ids[identifier] > 1))
                current = ('main_card' if main else 'early_card') if main != early and not conflict else 'unassigned'
                evidence = dict(id=identifier, text=text) if current != 'unassigned' else None
            else:
                visit(node)

    visit(component)
    result['counts'] = dict(Counter(row['section'] for row in result['rows']))
    result['reason'] = 'candidate_sections_only_identity_not_validated'
    return result
