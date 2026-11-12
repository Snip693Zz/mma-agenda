import unittest
from collector.discover import full_date, parse_page, compare

class DiscoveryTests(unittest.TestCase):
    def test_no_year_guess(self):
        self.assertIsNone(full_date('08/01/27'))
        self.assertIsNone(full_date('Sat, Jan 16'))
        self.assertIsNone(full_date('2027-02-30'))
    def test_full_dates(self):
        self.assertEqual(full_date('15/01/2027'), '2027-01-15')
        self.assertEqual(full_date('2028-06-01T19:00:00+02:00'), '2028-06-01')
    def test_ares_future_and_past(self):
        html = '<div>20/11/2026</div><h3>ARES 45</h3><div>15/01/2027</div><h3>ARES Marseille, janvier 2027</h3>'
        found, _, _ = parse_page(html, 'ARES', 'official', 'https://www.aresfighting.com/fr/events/', '2026-12-01')
        self.assertEqual([e['date'] for e in found], ['2027-01-15'])
    def test_hexagone_ambiguous_date(self):
        html = '<h2>HEXAGONE MMA</h2><p>08/01/27 – PARIS</p><h2>HEXAGONE MMA</h2><p>15/01/2027 – MONTPELLIER</p>'
        found, review, _ = parse_page(html, 'HEXAGONE', 'official', 'https://hexagonemma.fr/evenements/', '2026-11-12')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['date'], '2027-01-15')
        self.assertEqual(len(review), 1)
    def test_json_ld_and_domain(self):
        html = '<script type="application/ld+json">{"@graph":[{"@type":"SportsEvent","name":"UFC Test","startDate":"2028-06-01","url":"https://evil.example/event/a"}]}</script><a href="/event/ufc-test">Carte</a><a href="https://evil.example/event/b">Lien</a>'
        found, _, links = parse_page(html, 'UFC', 'official', 'https://www.ufc.com/events', '2026-11-12')
        self.assertEqual(found[0]['date'], '2028-06-01')
        self.assertIsNone(found[0]['event_url'])
        self.assertEqual(links, ['https://www.ufc.com/event/ufc-test'])
    def test_comparison_does_not_write_or_remove(self):
        baseline = [{'id':'ares45','org':'ARES','date':'2026-11-20','title':'ARES 45','url':'https://example.com/event/45'}]
        candidate = {'org':'ARES','date':'2026-11-21','title':'ARES 45','place':None,'event_url':'https://example.com/event/45'}
        result = compare(candidate, baseline)
        self.assertEqual(result['proposal'], 'possible_update')
        self.assertEqual(result['differences']['date']['before'], '2026-11-20')
        self.assertEqual(baseline[0]['date'], '2026-11-20')
    def test_unreadable_page_is_not_cancellation(self):
        found, _, _ = parse_page('<html>Page vide</html>', 'UFC', 'official', 'https://www.ufc.com/events', '2026-11-12')
        self.assertEqual(found, [])

if __name__ == '__main__': unittest.main()
