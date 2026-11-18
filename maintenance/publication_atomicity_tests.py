"""Real PostgreSQL concurrency/rollback checks. Disposable CI database only."""
import concurrent.futures
import datetime as dt
import hashlib
import os
import time
import uuid
import psycopg
from psycopg.types.json import Jsonb


def connect(name):
    return psycopg.connect('', autocommit=True, application_name=name,
                           options='-c statement_timeout=10000')


def seed(conn):
    event_id = 'ci-' + uuid.uuid4().hex
    run_id, proposal_id = uuid.uuid4(), uuid.uuid4()
    source = 'https://pflmma.com/event/' + event_id
    fight = {'fighter_a': 'Alpha Test', 'fighter_b': 'Beta Test', 'position': 4}
    report = {'mode': 'pfl_reconciliation_report', 'errors': [], 'automatic_publication': False,
              'generated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'reports': [{'event_id': event_id, 'source_url': source,
                           'source_validation': {'can_reconcile': True}, 'observed_fights': [fight]}]}
    with conn.transaction():
        conn.execute("update public.publication_policy set enabled=true where org='PFL'")
        conn.execute("insert into public.events(id,org,event_date,url,updated_at) values(%s,'PFL',current_date+30,%s,now()-interval '1 hour')", (event_id, source))
        conn.execute("insert into public.event_cards(event_id,position,name,level) values(%s,0,'Main Card','official')", (event_id,))
        conn.execute("insert into public.ingest_runs(id,status,source_report,source_sha256,extra) values(%s,'success','pfl_reconciliation_journal_v2',encode(sha256(convert_to((%s::jsonb)::text,'UTF8')),'hex'),jsonb_build_object('report',%s::jsonb))", (run_id, Jsonb(report), Jsonb(report)))
        conn.execute("insert into public.proposals(id,ingest_run_id,event_id,kind,status,source_kind,source_url,payload,journal_key) values(%s,%s,%s,'add_fight','pending','official',%s,%s,%s)", (proposal_id, run_id, event_id, source, Jsonb(dict(fight, card_position=0)), hashlib.sha256(str(proposal_id).encode()).hexdigest()))
    return event_id, run_id, proposal_id


def state(conn, event_id, proposal_id):
    return conn.execute("""select jsonb_build_object(
      'proposal', (select to_jsonb(p) from public.proposals p where id=%s),
      'cards', (select jsonb_agg(to_jsonb(c) order by position) from public.event_cards c where event_id=%s),
      'fights', (select coalesce(jsonb_agg(to_jsonb(f) order by card_position,position),'[]') from public.fights f where event_id=%s),
      'decisions', (select count(*) from public.proposal_decisions where proposal_id=%s),
      'logs', (select count(*) from public.publication_log where proposal_id=%s))""", (proposal_id, event_id, event_id, proposal_id, proposal_id)).fetchone()[0]


def publish(conn, run_id, event_id):
    return conn.execute('select public.publish_event_additions_v1(%s,%s,true)', (run_id, event_id)).fetchone()[0]


def check_rollback(conn):
    event_id, run_id, proposal_id = seed(conn)
    conn.execute("""create or replace function public.ci_fail_audit() returns trigger
      language plpgsql as $$ begin
        if current_setting('mma_test.fail_audit',true)='on' and new.target_table='fights' then
          raise exception 'forced audit failure';
        end if;
        return new;
      end $$""")
    conn.execute('create trigger ci_fail_audit before insert on public.publication_log for each row execute function public.ci_fail_audit()')
    before = state(conn, event_id, proposal_id)
    conn.execute("set mma_test.fail_audit='on'")
    failed = False
    try:
        try:
            publish(conn, run_id, event_id)
        except psycopg.errors.RaiseException as error:
            if 'forced audit failure' not in str(error):
                raise
            failed = True
    finally:
        conn.execute("set mma_test.fail_audit='off'")
        conn.execute('drop trigger ci_fail_audit on public.publication_log')
        conn.execute('drop function public.ci_fail_audit()')
    assert failed, 'Forced audit failure was not reached'
    assert state(conn, event_id, proposal_id) == before, 'Partial writes survived rollback'
    receipt = publish(conn, run_id, event_id)
    assert receipt['status'] == 'published', receipt
    after = state(conn, event_id, proposal_id)
    assert len(after['cards']) == 2 and len(after['fights']) == 1
    assert after['decisions'] == 1 and after['logs'] == 2
    assert publish(conn, run_id, event_id)['status'] == 'already_present'
    assert state(conn, event_id, proposal_id) == after, 'Replay changed committed state'


def check_concurrency(conn):
    event_id, run_id, proposal_id = seed(conn)
    names = ['ci-publish-' + uuid.uuid4().hex for _ in range(2)]
    with connect(names[0]) as first, connect(names[1]) as second, connect('ci-lock-holder') as blocker:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            with blocker.transaction():
                blocker.execute('lock table public.events in share row exclusive mode')
                futures = [pool.submit(publish, client, run_id, event_id) for client in (first, second)]
                deadline = time.monotonic() + 1.5
                waiting = 0
                while time.monotonic() < deadline:
                    waiting = conn.execute("select count(*) from pg_stat_activity where application_name=any(%s) and wait_event_type='Lock'", (names,)).fetchone()[0]
                    if waiting == 2:
                        break
                    time.sleep(0.02)
                # Exiting this transaction releases the lock for both waiting calls.
            assert waiting == 2, 'Test did not establish concurrent waiting calls'
            receipts = [future.result(timeout=12) for future in futures]
    assert sorted(r['status'] for r in receipts) == ['already_present', 'published'], receipts
    after = state(conn, event_id, proposal_id)
    assert len(after['cards']) == 2 and len(after['fights']) == 1
    assert after['proposal']['status'] == 'published'
    assert after['decisions'] == 1 and after['logs'] == 2
    assert sum(r.get('agenda_writes') is True for r in receipts) == 1
    assert publish(conn, run_id, event_id)['status'] == 'already_present'
    assert state(conn, event_id, proposal_id) == after


def main():
    if os.environ.get('PUBLICATION_TEST_DATABASE') != '1' or os.environ.get('PGDATABASE') != 'publication_test':
        raise RuntimeError('Refusing to run outside the explicitly disposable test database')
    if os.environ.get('PGHOST') not in ('localhost', '127.0.0.1'):
        raise RuntimeError('Only the local CI PostgreSQL service is allowed')
    with connect('ci-publication-checks') as conn:
        if conn.execute('select current_database()').fetchone()[0] != 'publication_test':
            raise RuntimeError('Wrong connected database')
        check_rollback(conn)
        print('PASS: forced audit failure rolls back the complete transaction; retry and replay succeed')
        check_concurrency(conn)
        print('PASS: two concurrent waiting calls produce one publication and one no-op')


if __name__ == '__main__':
    main()
