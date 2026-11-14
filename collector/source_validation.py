"""Validation conservative de sources ; aucune lecture reseau ni ecriture."""
from datetime import date


def assess_source(expected_date, observed_date, *, identity_verified=False, structured_card=False, fight_count=0):
    result = {'status': 'review_required', 'reason': '', 'can_reconcile': False,
              'empty_card_confirmed': False, 'auto_publishable': False}
    try:
        expected = date.fromisoformat(expected_date)
        observed = date.fromisoformat(observed_date)
    except (ValueError, TypeError):
        result['reason'] = 'missing_or_invalid_date'
        return result
    if expected != observed:
        result['reason'] = 'event_date_mismatch'
    elif identity_verified is not True:
        result['reason'] = 'event_identity_unverified'
    elif structured_card is not True:
        result['reason'] = 'card_structure_unverified'
    elif type(fight_count) is not int or fight_count < 0:
        result['reason'] = 'invalid_fight_count'
    elif fight_count == 0:
        result['reason'] = 'no_exploitable_fights'
    else:
        result.update(status='parsed_candidate', reason='dated_identified_structured_source', can_reconcile=True)
    return result
