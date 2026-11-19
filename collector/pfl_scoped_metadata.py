"""Extraction PFL ciblée, avec repli strict sans année implicite."""
from __future__ import annotations

import datetime as dt
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

MONTHS = {name: index for index, name in enumerate(
    ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'), 1
)}
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class EventBlocks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = {'event-info-title': [], 'event-sticky-title': []}
        self.scoped_present = False
        self.active = None
        self.depth = 0
        self.parts = []
        self.og_titles = []
        self.h1_titles = []
        self.times = []
        self.in_h1 = False
        self.h1_parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get('class') or '').split())
        if classes & self.blocks.keys():
            self.scoped_present = True
        if tag == 'meta' and (attrs.get('property') or '').lower() == 'og:title':
            title = (attrs.get('content') or '').strip()
            if title:
                self.og_titles.append(title)
        if tag == 'time':
            self.times.append((attrs.get('datetime') or '').strip())
        if tag == 'h1':
            self.in_h1, self.h1_parts = True, []
        elif self.in_h1:
            self.h1_parts.append(' ')
        if self.active is not None:
            if tag not in VOID_TAGS:
                self.depth += 1
            self.parts.append(' ')
            return
        for key in self.blocks:
            if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6') and key in classes:
                self.active, self.depth, self.parts = key, 1, []
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in VOID_TAGS:
            return
        if tag == 'h1' and self.in_h1:
            title = ' '.join(''.join(self.h1_parts).split())
            if title:
                self.h1_titles.append(title)
            self.in_h1 = False
        elif self.in_h1:
            self.h1_parts.append(' ')
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
        if self.in_h1:
            self.h1_parts.append(data)


def _strict_fallback(parser, expected):
    result = {'status': 'needs_review', 'url': expected}
    titles = set(parser.og_titles or parser.h1_titles)
    if len(titles) != 1:
        return {**result, 'reason': 'fallback_title_missing_or_ambiguous'}
    title = next(iter(titles))
    times = set(parser.times)
    if len(times) != 1 or not next(iter(times), ''):
        return {**result, 'title': title, 'reason': 'fallback_datetime_missing_or_ambiguous'}
    raw = next(iter(times))
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            date = dt.date.fromisoformat(raw)
            start_at = ''
        elif re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?', raw):
            parsed = dt.datetime.fromisoformat(raw.replace('Z', '+00:00'))
            date = parsed.date()
            start_at = raw if parsed.utcoffset() is not None else ''
        else:
            raise ValueError('ISO datetime required')
    except ValueError:
        return {**result, 'title': title, 'reason': 'fallback_datetime_invalid'}
    return {
        'status': 'metadata_found', 'title': title, 'date': date.isoformat(),
        'start_at': start_at, 'place': '', 'url': expected,
        'date_source': 'html_time_datetime',
    }


def extract_scoped_metadata(event_html: str, expected: str) -> dict:
    parser = EventBlocks()
    parser.feed(event_html or '')
    parser.close()
    if not parser.scoped_present:
        return _strict_fallback(parser, expected)
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
