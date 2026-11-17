from collector.pfl_card_structure import extract_pairs, extract_structured_fights

URL = 'https://pflmma.com/event/pfl-lyon-2026'


def rows_html(*rows):
    return ''.join(
        f'<div class="matchupRow"><a href="{a}"><span>{a_name}</span></a>'
        f'<a href="{b}"><span>{b_name}</span></a></div>'
        for a, a_name, b, b_name in rows
    )


def test_official_fragment_without_wrapper_is_extracted():
    html = rows_html((
        '/fighter/taylor-lapilus', 'Taylor Lapilus',
        '/fighter/mitch-mckee', 'Mitch McKee',
    ))
    result = extract_pairs(html, URL, allow_fragment=True)
    assert result['status'] == 'candidate_pairs'
    assert result['row_count'] == 1
    assert result['pairs'][0]['fighter_a_url'] == 'https://pflmma.com/fighter/taylor-lapilus'
    fights = extract_structured_fights(html, URL, allow_fragment=True)
    assert fights[0]['fighter_a'] == 'Taylor Lapilus'
    assert fights[0]['fighter_b'] == 'Mitch McKee'


def test_fragment_is_refused_without_explicit_permission():
    html = rows_html((
        '/fighter/taylor-lapilus', 'Taylor Lapilus',
        '/fighter/mitch-mckee', 'Mitch McKee',
    ))
    result = extract_pairs(html, URL)
    assert result['status'] == 'review_required'
    assert result['reason'] == 'missing_ambiguous_or_incomplete_component'


def test_official_fragment_safety_rules_remain_enforced():
    html = rows_html((
        '/fighter/taylor-lapilus', 'Taylor Lapilus',
        '/fighter/taylor-lapilus', 'Taylor Lapilus',
    ))
    result = extract_pairs(html, URL, allow_fragment=True)
    assert result['status'] == 'review_required'
    assert result['reason'] == 'duplicate_fighter_in_row'
    assert result['offending_row_index'] == 0


def test_wrapped_card_remains_supported():
    html = '<div id="fight_card_component">' + rows_html((
        '/fighter/taylor-lapilus', 'Taylor Lapilus',
        '/fighter/mitch-mckee', 'Mitch McKee',
    )) + '</div>'
    result = extract_pairs(html, URL)
    assert result['status'] == 'candidate_pairs'
    assert result['row_count'] == 1
