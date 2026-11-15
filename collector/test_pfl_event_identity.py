import unittest

from pfl_event_identity import extract_event

URL = "https://pflmma.com/event/pfl-lyon"

JSONLD = '''<script type="application/ld+json">
{"@graph":[{"@type":"SportsEvent","name":"PFL Lyon","startDate":"2025-12-13","url":"%s"}]}
</script>''' % URL


def row(a: str, b: str) -> str:
    return (
        '<div class="matchupRow">'
        f'<a href="/fighter/{a}">{a}</a>'
        f'<a href="/fighter/{b}">{b}</a>'
        '</div>'
    )


def component(body: str) -> str:
    return f'<div id="fight_card_component">{body}</div>'


class PFLIdentityTests(unittest.TestCase):
    def test_identity_names_and_unassigned_section(self):
        result = extract_event(JSONLD + component(row('a', 'b')), URL)
        self.assertEqual(result['status'], 'candidate_event')
        self.assertEqual(result['pairs'][0]['section'], 'unassigned')

    def test_ambiguous_names_are_rejected(self):
        html = JSONLD + component(row('a', 'b') + '<div class="matchupRow"><a href="/fighter/x">X</a></div>')
        result = extract_event(html, URL)
        self.assertEqual(result['reason'], 'ambiguous_fighter_pair')

    def test_external_fighter_is_rejected(self):
        html = JSONLD + component(row('a', 'b').replace('href="/fighter/a"', 'href="https://evil.example/fighter/a"'))
        self.assertEqual(extract_event(html, URL)['reason'], 'ambiguous_fighter_pair')

    def test_sections_are_labeled_without_assuming_main(self):
        html = JSONLD + component('<h2>MAIN CARD</h2>' + row('a', 'b') + '<h2>Early Card</h2>' + row('c', 'd'))
        result = extract_event(html, URL)
        self.assertEqual([p['section'] for p in result['pairs']], ['main_card', 'early_card'])

    def test_incomplete_jsonld_is_rejected(self):
        bad = '<script type="application/ld+json">{"@graph":[{"@type":"SportsEvent","url":"%s"}]}</script>' % URL
        result = extract_event(bad + component(row('a', 'b')), URL)
        self.assertEqual(result['event_identity']['reason'], 'incomplete_jsonld_event')

    def test_malformed_html_is_rejected(self):
        result = extract_event(JSONLD + component(row('a', 'b'))[:-6], URL)
        self.assertEqual(result['reason'], 'malformed_html')


if __name__ == '__main__':
    unittest.main()
