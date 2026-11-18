"""Thin runner for the shared transactional writer. Preview unless --publish is explicit."""
import argparse
import json
import os
from pathlib import Path

SUCCESS = {'preview', 'published', 'already_present', 'review_required', 'disabled'}


def run(client, report, org, publish=False, event_id=None):
    if report.get('errors') != [] or report.get('automatic_publication') is not False:
        raise ValueError('Invalid reconciliation report')
    run_id = report.get('saved', {}).get('ingest_run_id')
    if not isinstance(run_id, str) or not run_id:
        raise ValueError('A journal receipt is required; no implicit journal write is performed')
    entries = report.get('reports')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Empty event report')
    ids = [entry['event_id'] for entry in entries if event_id is None or entry['event_id'] == event_id]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('Missing or duplicate event identity')
    events = client.table('events').select('id,org').in_('id', ids).execute().data
    if not isinstance(events, list) or {e['id'] for e in events if e['org'] == org} != set(ids):
        raise ValueError('Organization mismatch')
    results = []
    for id_ in ids:
        try:
            data = client.rpc('publish_event_additions_v1', {
                'p_run_id': run_id, 'p_event_id': id_, 'p_apply': bool(publish),
            }).execute().data
            if not isinstance(data, dict) or data.get('status') not in SUCCESS:
                raise ValueError('Invalid publication receipt')
            if not publish and data.get('agenda_writes') is not False:
                raise ValueError('Preview returned unexpected write status')
            results.append(dict(data, event_id=id_))
        except Exception as error:
            results.append({'event_id': id_, 'status': 'failed', 'exception_type': type(error).__name__,
                            'write_outcome': 'unknown' if publish else 'none_requested'})
    return {'mode': 'shared_publication', 'publish_requested': bool(publish), 'run_id': run_id,
            'results': results, 'failed_count': sum(r['status'] == 'failed' for r in results),
            'published_count': sum(r['status'] == 'published' for r in results)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    parser.add_argument('--org', required=True)
    parser.add_argument('--event-id')
    parser.add_argument('--output', required=True)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from supabase import create_client
        report = json.loads(Path(args.report).read_text(encoding='utf-8'))
        client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
        result = run(client, report, args.org, args.publish, args.event_id)
    except Exception as error:
        result = {'mode': 'shared_publication', 'failed_count': 1,
                  'exception_type': type(error).__name__, 'results': []}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result['failed_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
