from collector.pfl_card_structure import extract_pairs, extract_structured_fights

URL = 'https://pflmma.com/event/pfl-lyon-2026'


def card(*rows):
    rows_html = ''.join(
        f'<div class="matchupRow"><a href="{a}"><span>{a_name}</span></a>'
        f'<a href="{b}"><span>{b_name}</span></a></div>'
        for a, a_name, b, b_name in rows
    )
    return f'<div id="fight_card_component">{rows_html}</div>'


def test_nested_names_are_extracted():
    html = card((
        '/fighter/taylor-lapilus', 'Taylor Lapilus',
        '/fighter/mitch-mckee', 'Mitch McKee',
    ))
    result = extract_pairs(html, URL)
    assert result['status'] == 'candidate_pairs'
    assert result['pairs'] == [{
        'fighter_a_url': 'https://pflmma.com/fighter/taylor-lapilus',
        'fighter_b_url': 'https://pflmma.com/fighter/mitch-mckee',
    }]
    fights = extract_structured_fights(html, URL)
    assert fights[0]['fighter_a'] == 'Taylor Lapilus'
    assert fights[0]['fighter_b'] == 'Mitch McKee'


def test_duplicate_row_reports_offending_row():
    html = card((
        '/fighter/taylor-lapilus', 'Taylor Lapilus',
        '/fighter/mitch-mckee', 'Mitch McKee',
    )) + '<div class="matchupRow"><a href="/fighter/taylor-lapilus">Taylor</a><a href="/fighter/taylor-lapilus">Taylor</a></div>'
    result = extract_pairs(html, URL)
    assert result['status'] == 'review_required'
    assert result['reason'] == 'duplicate_fighter_in_row'
    assert result['offending_row_index'] == 1
    assert len(result['offending_row_links']) == 2


def test_ambiguous_row_reports_offending_row():
    html = '<div id="fight_card_component"><div class="matchupRow"><a href="/fighter/taylor-lapilus">Taylor</a></div></div>'
    result = extract_pairs(html, URL)
    assert result['status'] == 'review_required'
    assert result['reason'] == 'ambiguous_fighter_pair'
    assert result['offending_row_index'] == 0
    assert result['offending_row_links'][0]['text'] == 'Taylor'
