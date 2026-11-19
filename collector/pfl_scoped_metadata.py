"""Métadonnées PFL issues des blocs propres à la fiche, sans année implicite."""
from __future__ import annotations

import datetime as dt
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

MONTHS = {name: index for index, name in enumerate(
    ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'), 1
)}


class EventBlocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = {'event-info-title': [], 'event-sticky-title': []}
        self.active = None
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if self.active is not None:
            if tag not in ('br', 'hr', 'img', 'input', 'meta', 'link', 'wbr'):
                self.depth += 1
            self.parts.append(' ')
            return
        classes = set((dict(attrs).get('class') or '').split())
        for key in self.blocks:
            if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') and key in classes:
                self.active, self.depth, self.parts = key, 1, []
                break

    def handle_startendtag(self, tag, attrs):
        if self.active is not None:
            self.parts.append(' ')

    def handle_endtag(self, tag):
        if self.active is None:
            return
        self.depth -= 1
        if self.depth == 0:
            text = ' '.join(''.join(self.parts).split())
            if text and text not in self.blocks[self.active]:
                self.blocks[self.active].append(text)
            self.active, self.parts = None, []

    def handle_data(self, data):
        if self.active is not None:
            self.parts.append(data)


def extract_scoped_metadata(event_html: str, expected: str) -> dict:
    parser = EventBlocks()
    parser.feed(event_html or '')
    parser.close()
    titles = parser.blocks['event-info-title']
    result = {'status': 'needs_review', 'url': expected}
    if len(titles) != 1:
        return {**result, 'reason': 'event_title_missing_or_ambiguous'}
    title = titles[0]
    result['title'] = title
    normalize = lambda value: ' '.join(value.split()).casefold()
    dates = []
    for text in parser.blocks['event-sticky-title']:
        prefix, separator, date_text = text.partition('|')
        if separator and normalize(prefix) == normalize(title):
            if date_text.strip() not in dates:
                dates.append(date_text.strip())
    if len(dates) != 1:
        return {**result, 'reason': 'event_date_missing_or_ambiguous'}
    date_text = dates[0]
    match = re.fullmatch(
        r'(?:(MON|TUE|WED|THU|FRI|SAT|SUN),?\s+)?'
        r'([A-Z]{3})\s+(\d{1,2})(?:,?\s+(20\d{2}))?',
        date_text, re.IGNORECASE,
    )
    if not match or match.group(2).upper() not in MONTHS:
        return {**result, 'reason': 'event_date_format_unrecognized'}
    path_years = set(re.findall(r'(?<![A-Za-z0-9])(20\d{2})(?![A-Za-z0-9])', urlsplit(expected).path))
    explicit_year = match.group(4)
    years = path_years | ({explicit_year} if explicit_year else set())
    if len(years) != 1:
        return {**result, 'reason': 'event_year_missing_or_ambiguous', 'observed_date': date_text}
    try:
        date = dt.date(int(next(iter(years))), MONTHS[match.group(2).upper()], int(match.group(3)))
    except ValueError:
        return {**result, 'reason': 'event_date_invalid'}
    weekdays = ('MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN')
    if match.group(1) and weekdays[date.weekday()] != match.group(1).upper():
        return {**result, 'reason': 'event_weekday_mismatch'}
    return {
        'status': 'metadata_found', 'title': title, 'date': date.isoformat(),
        'start_at': '', 'place': '', 'url': expected,
        'date_source': 'scoped_html_explicit_year' if explicit_year else 'scoped_html_url_year',
    }
