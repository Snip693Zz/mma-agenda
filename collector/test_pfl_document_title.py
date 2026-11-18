"""Document-title corroboration; compatible with unittest and pytest."""
import unittest
from pfl_primary_identity import primary_identity_matches

EVENT = {'title': 'PFL Lyon — Lapilus vs McKee'}


def page(title='PFL Lyon | Professional Fighters League', og='', body='<h2>PFL Lyon</h2>'):
    meta = '' if og is None else '<meta property="og:title" content="' + og + '">'
    return '<html><head><title>' + title + '</title>' + meta + '</head><body>' + body + '</body></html>'


class DocumentTitleTests(unittest.TestCase):
    def test_empty_og_uses_document_title(self):
        self.assertTrue(primary_identity_matches(page(), EVENT))

    def test_missing_og_uses_document_title(self):
        self.assertTrue(primary_identity_matches(page(og=None), EVENT))

    def test_conflicting_og_is_not_bypassed(self):
        self.assertFalse(primary_identity_matches(page(og='PFL Dubai'), EVENT))

    def test_conflicting_document_title_is_rejected(self):
        self.assertFalse(primary_identity_matches(page(title='PFL Dubai'), EVENT))

    def test_duplicate_matching_headings_are_rejected(self):
        self.assertFalse(primary_identity_matches(page(body='<h2>PFL Lyon</h2><h2>PFL Lyon</h2>'), EVENT))

    def test_document_title_alone_is_not_new_evidence(self):
        self.assertFalse(primary_identity_matches(page(body=''), EVENT))

    def test_duplicate_document_titles_are_rejected(self):
        html = page().replace('</head>', '<title>PFL Lyon</title></head>')
        self.assertFalse(primary_identity_matches(html, EVENT))

    def test_conflicting_h1_is_not_bypassed(self):
        self.assertFalse(primary_identity_matches(page(body='<h1>PFL Dubai</h1><h2>PFL Lyon</h2>'), EVENT))

    def test_navigation_heading_is_not_used(self):
        self.assertFalse(primary_identity_matches(page(body='<nav><h2>PFL Lyon</h2></nav>'), EVENT))

    def test_malformed_html_is_rejected(self):
        self.assertFalse(primary_identity_matches(page() + '</section>', EVENT))

    def test_dubai_og_path_is_preserved(self):
        html = page(title='PFL Dubai', og='PFL Dubai', body='<h2>PFL Dubai</h2>')
        self.assertTrue(primary_identity_matches(html, {'title': 'PFL Dubai — Nemkov vs Bilostenniy'}))
