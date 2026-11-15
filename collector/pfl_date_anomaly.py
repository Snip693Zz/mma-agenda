"""Offline date anomaly diagnosis; never repairs or publishes source dates."""
from datetime import datetime


def classify(event):
    result = {'status': 'review_required', 'classification': 'not_applicable',
              'automatic_publication': False, 'database_writes': False,
              'date_repair_performed': False}
    start = event.get('startDate')
    end = event.get('endDate')
    if not isinstance(start, str) or not isinstance(end, str):
        result['reason'] = 'missing_dates'
        return result
    try:
        start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
    except ValueError:
        result['reason'] = 'invalid_dates'
        return result
    result.update(startDate=start, endDate=end,
                  start_offset=start_dt.utcoffset().total_seconds(),
                  end_offset=end_dt.utcoffset().total_seconds())
    if end_dt > start_dt:
        result['classification'] = 'valid_range'
        result['reason'] = 'end_after_start'
        return result
    same_local_day = (start_dt.date() == end_dt.date())
    same_offset = result['start_offset'] == result['end_offset']
    midnight = end_dt.time().isoformat() == '00:00:00'
    if same_local_day and same_offset and midnight:
        result['classification'] = 'same_day_midnight_end'
        result['reason'] = 'end_not_after_start_source_declares_midnight_end'
    else:
        result['classification'] = 'other_non_increasing_range'
        result['reason'] = 'end_not_after_start'
    return result
