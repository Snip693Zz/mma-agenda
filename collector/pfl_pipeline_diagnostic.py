"""Inspect browser captures without database access or publication."""
import argparse
import json
from pathlib import Path
from pfl_card_structure import Tree, extract_pairs, extract_structured_fights, _readable_name
from pfl_primary_identity import primary_identity_matches, _og_title

EXPECTED = {
    'https://pflmma.com/event/pfl-lyon-2026': 'PFL Lyon — Lapilus vs McKee',
    'https://pflmma.com/event/pfl-returns-to-dubai': 'PFL Dubaï — Nemkov vs Bilostenniy',
}


def inspect(item):
    url = item.get('source_url', '')
    page = item.get('page_html') or ''
    card = item.get('card_html') or ''
    tree = Tree(page)
    headings = [
        {'tag': node.tag, 'text': _readable_name(node)[:200]}
        for node in tree.root.walk() if node.tag in ('h1', 'h2')
    ][:30]
    pairs = extract_pairs(card, url, allow_fragment=True)
    fights = extract_structured_fights(card, url, allow_fragment=True)
    card_tree = Tree(card)
    rows = [node for node in card_tree.root.walk()
            if 'matchupRow' in node.attrs.get('class', '').split()]
    row_diagnostics = []
    for index, row in enumerate(rows):
        links = [node for node in row.walk()
                 if node.tag == 'a' and '/fighter/' in node.attrs.get('href', '')]
        row_diagnostics.append({
            'row': index, 'fighter_links': len(links),
            'nonempty_link_names': sum(bool(_readable_name(node)) for node in links),
        })
    return {
        'source_url': url, 'expected_title': EXPECTED[url],
        'browser_title': item.get('title'), 'date': item.get('date'),
        'date_source': item.get('date_source'),
        'boxemag_date': item.get('boxemag_date'),
        'boxemag_url': item.get('boxemag_url'),
        'page_html_length': len(page), 'card_html_length': len(card),
        'page_malformed': tree.malformed, 'page_unclosed': len(tree.stack) - 1,
        'og_title': _og_title(page), 'headings': headings,
        'identity_matches': primary_identity_matches(page, {'title': EXPECTED[url]}),
        'pair_status': pairs['status'], 'pair_reason': pairs['reason'],
        'pair_count': len(pairs['pairs']), 'row_count': pairs['row_count'],
        'structured_fight_count': len(fights), 'rows': row_diagnostics,
        'browser_error': item.get('error'),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    parser.add_argument('--output', default='reports/pfl-pipeline-diagnostic.json')
    args = parser.parse_args()
    source = json.loads(Path(args.report).read_text(encoding='utf-8'))
    if source.get('mode') != 'pfl_browser_discovery':
        raise ValueError('Unexpected browser report mode')
    selected = [item for item in source.get('candidates', []) if item.get('source_url') in EXPECTED]
    report = {'mode': 'diagnostic_only', 'database_writes': False,
              'automatic_publication': False,
              'missing_urls': sorted(set(EXPECTED) - {item['source_url'] for item in selected}),
              'events': [inspect(item) for item in selected]}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not report['missing_urls'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
