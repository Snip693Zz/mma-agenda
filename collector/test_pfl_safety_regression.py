"""Regression PFL sans dependance de test externe ni connexion reseau."""
import unittest
from pfl_reconciliation import extract_fights, reconcile_event, build_report

BANNER = '<div>PATRICK vs OMAR FACEOFF - PFL DUBAI - CO-MAIN EVENT</div>'
VALID = '<div>Boris Atangana vs. Bryan Battle</div>'
EVENT = {'id': 'pfl-test', 'title': 'PFL Test', 'url': 'https://pflmma.com/event/test', 'official': True}


class PFLSafetyTests(unittest.TestCase):
    def test_faceoff_is_not_a_fight(self):
        self.assertEqual(extract_fights(BANNER), [])

    def test_face_off_is_not_a_fight(self):
        self.assertEqual(extract_fights('<div>PATRICK vs OMAR FACE-OFF</div>'), [])

    def test_valid_pair_is_preserved(self):
        fights = extract_fights(VALID)
        self.assertEqual(len(fights), 1)
        self.assertEqual(fights[0]['fighter_a'], 'Boris Atangana')
        self.assertEqual(fights[0]['fighter_b'], 'Bryan Battle')

    def test_banner_cannot_create_add_fight(self):
        report = reconcile_event(EVENT, [], BANNER)
        self.assertEqual(report['summary']['add_fight'], 0)
        self.assertEqual(report['summary']['auto_publishable'], 0)

    def test_missing_existing_fight_remains_blocked(self):
        existing = [{'fighter_a': 'Old A', 'fighter_b': 'Old B'}]
        report = reconcile_event(EVENT, existing, VALID)
        self.assertEqual(report['summary']['blocked'], 1)
        self.assertEqual(existing, [{'fighter_a': 'Old A', 'fighter_b': 'Old B'}])

    def test_report_never_enables_automatic_publication(self):
        report = build_report([EVENT], {}, fetcher=lambda url: VALID)
        self.assertIs(report['automatic_publication'], False)


if __name__ == '__main__':
    unittest.main()
