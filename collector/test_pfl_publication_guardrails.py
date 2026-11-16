"""Tests hors ligne des garde-fous de publication PFL."""
import unittest
from pfl_publication_guardrails import build_proposals

EVENT_URL = 'https://pflmma.com/event/pfl-lyon'
TODAY = '2026-11-16'


def discovery(url=EVENT_URL, upcoming=True, status='metadata_found', title='PFL Lyon', date='2026-12-11'):
    return {
        'candidates': [{
            'source_url': url,
            'upcoming': upcoming,
            'metadata': {'status': status, 'title': title, 'date': date, 'place': 'Lyon, France'},
        }],
    }


class PublicationGuardrailsTests(unittest.TestCase):
    def test_valid_upcoming_event_is_proposed_without_auto_publication(self):
        report = build_proposals(discovery(), [], today=TODAY)
        proposal = report['proposals'][0]
        self.assertEqual(proposal['proposal'], 'create_event')
        self.assertFalse(proposal['auto_publishable'])
        self.assertTrue(proposal['requires_manual_approval'])
        self.assertFalse(proposal['database_writes'])
        self.assertFalse(report['automatic_publication'])
        self.assertFalse(report['database_writes'])

    def test_existing_event_is_not_proposed_for_creation(self):
        existing = [{'id': 'pfl-1', 'url': 'https://www.pflmma.com/event/pfl-lyon/'}]
        report = build_proposals(discovery(), existing, today=TODAY)
        proposal = report['proposals'][0]
        self.assertEqual(proposal['proposal'], 'review_required')
        self.assertEqual(report['summary']['create_event'], 0)

    def test_past_event_is_not_proposed_for_creation(self):
        report = build_proposals(discovery(date='2026-11-15'), [], today=TODAY)
        proposal = report['proposals'][0]
        self.assertEqual(proposal['proposal'], 'review_required')

    def test_incomplete_metadata_requires_review(self):
        report = build_proposals(discovery(title=''), [], today=TODAY)
        proposal = report['proposals'][0]
        self.assertEqual(proposal['proposal'], 'review_required')

    def test_invalid_date_requires_review(self):
        report = build_proposals(discovery(date='not-a-date'), [], today=TODAY)
        proposal = report['proposals'][0]
        self.assertEqual(proposal['proposal'], 'review_required')

    def test_summary_counts_are_consistent(self):
        report = build_proposals(discovery(), [], today=TODAY)
        self.assertEqual(report['summary']['candidates'], 1)
        self.assertEqual(report['summary']['create_event'], 1)
        self.assertEqual(report['summary']['review_required'], 0)
        self.assertEqual(report['summary']['auto_publishable'], 0)


if __name__ == '__main__':
    unittest.main()
