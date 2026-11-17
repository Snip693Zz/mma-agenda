import unittest

from pfl_card_structure import extract_pairs, extract_structured_fights


SOURCE_URL = 'https://pflmma.com/event/example-event/'


def card(rows):
    return "<!doctype html><html><body><div id='fight_card_component'>" + ''.join(rows) + '</div></body></html>'


def anchor(href, inner):
    return f"<a href='{href}'>{inner}</a>"


def row(a_href, a_inner, b_href, b_inner):
    return f"<div class='matchupRow'>{anchor(a_href, a_inner)}{anchor(b_href, b_inner)}</div>"


class FighterNameTests(unittest.TestCase):
    def test_simple_names(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan Bader', '/fighter/antonio-carlos-junior/', 'Antonio Carlos Junior')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['fighter_a'], 'Ryan Bader')
        self.assertEqual(fights[0]['fighter_b'], 'Antonio Carlos Junior')

    def test_card_source_preserved(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan Bader', '/fighter/antonio-carlos-junior/', 'Antonio Carlos Junior')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['card_source'], SOURCE_URL)

    def test_fragment_allowed_when_enabled(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan Bader', '/fighter/antonio-carlos-junior/', 'Antonio Carlos Junior')
        ]), SOURCE_URL + '#fight-card', allow_fragment=True)
        self.assertEqual(fights[0]['card_source'], SOURCE_URL + '#fight-card')

    def test_fragment_rejected_by_default(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan Bader', '/fighter/antonio-carlos-junior/', 'Antonio Carlos Junior')
        ]), SOURCE_URL + '#fight-card')
        self.assertEqual(fights, [])

    def test_nested_name_order(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', '<span>Ryan</span> <b>Bader</b>',
                '/fighter/antonio-carlos-junior/', '<i>Antonio</i> <span>Carlos Junior</span>')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['fighter_a'], 'Ryan Bader')
        self.assertEqual(fights[0]['fighter_b'], 'Antonio Carlos Junior')

    def test_word_separation_across_nodes(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', '<span>Ryan</span><span>Bader</span>',
                '/fighter/antonio-carlos-junior/', '<span>Antonio</span><span>Carlos Junior</span>')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['fighter_a'], 'Ryan Bader')

    def test_ignores_more_info_label(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan Bader <span>MORE INFO</span>',
                '/fighter/antonio-carlos-junior/', 'Antonio Carlos Junior')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['fighter_a'], 'Ryan Bader')

    def test_ignores_view_profile_label(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan Bader <span>VIEW PROFILE</span>',
                '/fighter/antonio-carlos-junior/', 'Antonio Carlos Junior')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['fighter_a'], 'Ryan Bader')

    def test_ignores_labels_case_insensitive(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan Bader <span>more info</span>',
                '/fighter/antonio-carlos-junior/', 'Antonio Carlos Junior')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['fighter_a'], 'Ryan Bader')

    def test_ignores_multiple_labels(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'MORE INFO Ryan Bader VIEW PROFILE',
                '/fighter/antonio-carlos-junior/', 'Antonio Carlos Junior')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['fighter_a'], 'Ryan Bader')

    def test_no_name_does_not_use_slug(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', '', '/fighter/antonio-carlos-junior/', 'Antonio Carlos Junior')
        ]), SOURCE_URL)
        self.assertEqual(fights, [])

    def test_whitespace_normalized(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', '  Ryan   Bader  ',
                '/fighter/antonio-carlos-junior/', '  Antonio   Carlos   Junior  ')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['fighter_a'], 'Ryan Bader')
        self.assertEqual(fights[0]['fighter_b'], 'Antonio Carlos Junior')

    def test_name_with_punctuation(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan Bader',
                '/fighter/antonio-carlos-junior/', 'Antonio Carlos Jr.')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['fighter_b'], 'Antonio Carlos Jr.')

    def test_text_between_children_order(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan <span>Bader</span>',
                '/fighter/antonio-carlos-junior/', 'Antonio <span>Carlos Junior</span>')
        ]), SOURCE_URL)
        self.assertEqual(fights[0]['fighter_a'], 'Ryan Bader')

    def test_two_fighters_positions(self):
        fights = extract_structured_fights(card([
            row('/fighter/a/', 'Fighter A', '/fighter/b/', 'Fighter B'),
            row('/fighter/c/', 'Fighter C', '/fighter/d/', 'Fighter D'),
        ]), SOURCE_URL)
        self.assertEqual([fight['position'] for fight in fights], [0, 1])
        self.assertEqual([fight['card_position'] for fight in fights], [0, 0])

    def test_duplicate_rows_skipped(self):
        duplicated = row('/fighter/a/', 'Fighter A', '/fighter/b/', 'Fighter B')
        fights = extract_structured_fights(card([duplicated, duplicated]), SOURCE_URL)
        self.assertEqual(len(fights), 1)

    def test_invalid_url_returns_empty(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan Bader', 'https://example.com/fighter/x/', 'X')
        ]), SOURCE_URL)
        self.assertEqual(fights, [])

    def test_missing_component_returns_empty(self):
        self.assertEqual(extract_structured_fights('<html><body></body></html>', SOURCE_URL), [])


class RepeatedLinkTests(unittest.TestCase):
    def test_duplicate_fighter_in_row_refused(self):
        result = extract_pairs(card([
            row('/fighter/ryan-bader/', 'Ryan Bader', '/fighter/ryan-bader/', 'Ryan Bader')
        ]), SOURCE_URL)
        self.assertEqual(result['reason'], 'duplicate_fighter_in_row')

    def test_structured_fights_empty_for_repeated_single_fighter(self):
        fights = extract_structured_fights(card([
            row('/fighter/ryan-bader/', 'Ryan Bader', '/fighter/ryan-bader/', 'Ryan Bader')
        ]), SOURCE_URL)
        self.assertEqual(fights, [])

    def test_duplicate_link_with_same_name_is_tolerated(self):
        html = card([
            "<div class='matchupRow'>"
            + anchor('/fighter/ryan-bader/', 'Ryan Bader')
            + anchor('/fighter/ryan-bader/', 'Ryan Bader')
            + anchor('/fighter/antonio-carlos-junior/', 'Antonio Carlos Junior')
            + '</div>'
        ])
        result = extract_pairs(html, SOURCE_URL)
        self.assertEqual(result['reason'], 'identity_names_and_card_sections_not_validated')
        fights = extract_structured_fights(html, SOURCE_URL)
        self.assertEqual(fights[0]['fighter_a'], 'Ryan Bader')
        self.assertEqual(fights[0]['fighter_b'], 'Antonio Carlos Junior')


if __name__ == '__main__':
    unittest.main()
