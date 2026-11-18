-- Integration tests; temporary database only. Everything below is rolled back.
begin;
do $$
declare rid uuid:=gen_random_uuid(); pid uuid:=gen_random_uuid(); r jsonb; receipt jsonb;
        f jsonb:='{"fighter_a":"Alpha Test","fighter_b":"Beta Test","position":5}';
        eid text:='integration-event'; source text:='https://pflmma.com/event/integration-event';
        before_count int;
begin
  insert into public.events(id,org,event_date,url,updated_at)
    values(eid,'PFL',current_date+30,source,now()-interval '1 hour');
  insert into public.event_cards(event_id,position,name,level,extra) values
    (eid,2,'Unassigned','official','{"allocation":"unassigned"}');
  r:=jsonb_build_object('mode','pfl_reconciliation_report','errors','[]'::jsonb,'automatic_publication',false,
      'generated_at',clock_timestamp(),'reports',jsonb_build_array(jsonb_build_object('event_id',eid,'source_url',source,
      'source_validation',jsonb_build_object('can_reconcile',true),'observed_fights',jsonb_build_array(f))));
  insert into public.ingest_runs(id,status,source_report,source_sha256,extra)
    values(rid,'success','pfl_reconciliation_journal_v2',encode(sha256(convert_to(r::text,'UTF8')),'hex'),jsonb_build_object('report',r));
  insert into public.proposals(id,ingest_run_id,event_id,kind,status,source_kind,source_url,payload,journal_key)
    values(pid,rid,eid,'add_fight','pending','official',source,f||'{"card_position":0}',repeat('a',64));
  receipt:=public.publish_event_additions_v1(rid,eid,false);
  if receipt->>'status'<>'preview' or (select count(*) from public.fights)<>0 then raise exception 'Preview failed'; end if;
  receipt:=public.publish_event_additions_v1(rid,eid,true);
  if receipt->>'status'<>'disabled' or (select count(*) from public.fights)<>0 then raise exception 'Disabled policy failed'; end if;
  update public.publication_policy set enabled=true where org='PFL';
  update public.proposals set status='rejected' where id=pid;
  receipt:=public.publish_event_additions_v1(rid,eid,true);
  if receipt->>'status'<>'review_required' then raise exception 'Rejected proposal bypassed'; end if;
  update public.proposals set status='pending' where id=pid;
  insert into public.proposal_decisions(proposal_id,decision) values(pid,'blocked');
  receipt:=public.publish_event_additions_v1(rid,eid,true);
  if receipt->>'status'<>'review_required' then raise exception 'Decision bypassed'; end if;
  delete from public.proposal_decisions where proposal_id=pid;
  receipt:=public.publish_event_additions_v1(rid,eid,true);
  if receipt->>'status'<>'published' or (select count(*) from public.fights)<>1 then raise exception 'Publication failed'; end if;
  if not exists(select 1 from public.fights where event_id=eid and card_position=2 and position=0) then raise exception 'Wrong allocation'; end if;
  if (select status from public.proposals where id=pid)<>'published' then raise exception 'Missing status'; end if;
  if (select count(*) from public.publication_log)<>1 then raise exception 'Missing audit'; end if;
  receipt:=public.publish_event_additions_v1(rid,eid,true);
  if receipt->>'status'<>'already_present' or (select count(*) from public.fights)<>1
     or (select status from public.proposals where id=pid)<>'published' then raise exception 'Repeat failed'; end if;
  -- A missing active fight is a discrepancy, never an automatic deletion.
  insert into public.fights values(eid,2,1,'Missing A','Missing B');
  receipt:=public.publish_event_additions_v1(rid,eid,true);
  if receipt->>'status'<>'review_required' or (select count(*) from public.fights)<>2 then raise exception 'Discrepancy guard failed'; end if;
  -- Existing UFC functions are not replaced or invoked by this migration.
  if has_function_privilege('anon','public.publish_event_additions_v1(uuid,text,boolean)','EXECUTE') then
    raise exception 'Anonymous publication permission';
  end if;
  if has_table_privilege('anon','public.publication_policy','UPDATE') then raise exception 'Anonymous policy update'; end if;
end $$;
rollback;
