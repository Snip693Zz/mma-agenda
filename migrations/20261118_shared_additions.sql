-- Install only after isolated PostgreSQL tests. All publication policies start disabled.
create table if not exists public.publication_policy (
  org text primary key, enabled boolean not null default false,
  report_source text not null, report_mode text not null,
  official_url_pattern text not null,
  allow_url_year_alias boolean not null default false,
  max_age_seconds integer not null check (max_age_seconds between 1 and 86400)
);
alter table public.publication_policy enable row level security;
revoke all on public.publication_policy from public, anon, authenticated;
insert into public.publication_policy(org,report_source,report_mode,official_url_pattern,allow_url_year_alias,max_age_seconds)
values ('PFL','pfl_reconciliation_journal_v2','pfl_reconciliation_report',
        '^https://(www[.])?pflmma[.]com/event/[A-Za-z0-9-]+/?$',true,86400)
on conflict (org) do nothing;

create or replace function public.publication_pair_v1(p jsonb) returns jsonb
language plpgsql immutable set search_path=pg_catalog,public as $$
declare a text; b text;
begin
  if jsonb_typeof(p->'fighter_a') is distinct from 'string' or jsonb_typeof(p->'fighter_b') is distinct from 'string' then
    raise exception 'Invalid fighter names';
  end if;
  a:=lower(normalize(regexp_replace(btrim(p->>'fighter_a'),'[[:space:]]+',' ','g'),NFC));
  b:=lower(normalize(regexp_replace(btrim(p->>'fighter_b'),'[[:space:]]+',' ','g'),NFC));
  if a='' or b='' or a=b then raise exception 'Invalid fighter pair'; end if;
  return jsonb_build_array(least(a collate "C",b collate "C"),greatest(a collate "C",b collate "C"));
end $$;

create or replace function public.publication_url_v1(u text, year_alias boolean) returns text
language sql immutable set search_path=pg_catalog,public as $$
  select case when year_alias then regexp_replace(rtrim(regexp_replace(u,'^https://www[.]','https://'),'/'),'-20[0-9]{2}$','')
         else rtrim(regexp_replace(u,'^https://www[.]','https://'),'/') end;
$$;

create or replace function public.publish_event_additions_v1(p_run_id uuid,p_event_id text,p_apply boolean default false)
returns jsonb language plpgsql security definer
set search_path=pg_catalog,public set lock_timeout='3s' set timezone='UTC' as $$
declare
  ev public.events%rowtype; run public.ingest_runs%rowtype; pol public.publication_policy%rowtype;
  prop public.proposals%rowtype; report jsonb; entry jsonb; f jsonb; token jsonb;
  observed jsonb[]:=array[]::jsonb[]; current_pairs jsonb[]:=array[]::jsonb[];
  candidates jsonb:='[]'; inserted jsonb:='[]'; n int; distinct_n int;
  card int; pos int; card_count int; create_card boolean; seen timestamptz;
  source text; observed_names text[]:=array[]::text[]; t text; v_now timestamptz:=clock_timestamp();
begin
  if p_apply is null or p_run_id is null or p_event_id is null then raise exception 'Missing arguments'; end if;
  -- Same order as the existing UFC writer; no external IO while holding locks.
  lock table public.events,public.event_cards,public.fights in share row exclusive mode;
  lock table public.proposals,public.proposal_decisions in share row exclusive mode;
  select * into strict ev from public.events where id=p_event_id for update;
  select * into pol from public.publication_policy where org=ev.org for share;
  if not found then return jsonb_build_object('status','review_required','reason','organization_not_configured','agenda_writes',false); end if;
  select * into strict run from public.ingest_runs where id=p_run_id for share;
  report:=run.extra->'report';
  if run.status<>'success' or run.source_report<>pol.report_source or report->>'mode' is distinct from pol.report_mode
     or report->'errors' is distinct from '[]'::jsonb or report->'automatic_publication' is distinct from 'false'::jsonb
     or encode(sha256(convert_to(report::text,'UTF8')),'hex') is distinct from run.source_sha256 then
    raise exception 'Invalid report provenance';
  end if;
  seen:=(report->>'generated_at')::timestamptz;
  if seen is null or seen<v_now-make_interval(secs=>pol.max_age_seconds) or seen>v_now+interval '5 minutes'
     or ev.updated_at>seen or ev.event_date<(v_now at time zone 'UTC')::date then
    return jsonb_build_object('status','review_required','reason','stale_report_or_changed_event','agenda_writes',false);
  end if;
  select count(*) into n from jsonb_array_elements(report->'reports') e where e->>'event_id'=ev.id;
  if n<>1 then raise exception 'Ambiguous report event'; end if;
  select e into entry from jsonb_array_elements(report->'reports') e where e->>'event_id'=ev.id;
  if entry#>'{source_validation,can_reconcile}' is distinct from 'true'::jsonb then
    return jsonb_build_object('status','review_required','reason','unvalidated_source','agenda_writes',false);
  end if;
  source:=entry->>'source_url';
  if source is null or source!~pol.official_url_pattern then raise exception 'Source not allowed'; end if;
  select count(*) into n from public.events e where
    public.publication_url_v1(e.url,pol.allow_url_year_alias)=public.publication_url_v1(source,pol.allow_url_year_alias)
    or public.publication_url_v1(e.official_card_url,pol.allow_url_year_alias)=public.publication_url_v1(source,pol.allow_url_year_alias);
  if n<>1 or not (public.publication_url_v1(ev.url,pol.allow_url_year_alias)=public.publication_url_v1(source,pol.allow_url_year_alias)
        or coalesce(public.publication_url_v1(ev.official_card_url,pol.allow_url_year_alias)=public.publication_url_v1(source,pol.allow_url_year_alias),false)) then
    raise exception 'Source/event mismatch';
  end if;
  if exists(select 1 from public.ingest_runs r where r.source_report=pol.report_source and r.started_at>run.started_at
            and exists(select 1 from jsonb_array_elements(coalesce(r.extra->'report'->'reports','[]')) e where e->>'event_id'=ev.id)) then
    return jsonb_build_object('status','review_required','reason','newer_report_available','agenda_writes',false);
  end if;
  if jsonb_typeof(entry->'observed_fights') is distinct from 'array' then raise exception 'Missing observed fights'; end if;
  if jsonb_array_length(entry->'observed_fights') not between 1 and 100 then raise exception 'Invalid card size'; end if;
  for f in select value from jsonb_array_elements(entry->'observed_fights') loop
    token:=public.publication_pair_v1(f);
    if token=any(observed) then raise exception 'Duplicate observed fight'; end if;
    foreach t in array array[token->>0,token->>1] loop
      if t=any(observed_names) then raise exception 'Fighter observed twice'; end if;
      observed_names:=array_append(observed_names,t);
    end loop;
    observed:=array_append(observed,token);
  end loop;
  if not exists(select 1 from public.event_cards where event_id=ev.id and is_active) then raise exception 'No active cards'; end if;
  for f in select to_jsonb(x) from public.fights x join public.event_cards c on c.event_id=x.event_id and c.position=x.card_position
           where x.event_id=ev.id and c.is_active loop
    token:=public.publication_pair_v1(f);
    if token=any(current_pairs) or not(token=any(observed)) then
      return jsonb_build_object('status','review_required','reason','active_card_discrepancy','agenda_writes',false);
    end if;
    current_pairs:=array_append(current_pairs,token);
  end loop;
  for f in select value from jsonb_array_elements(entry->'observed_fights') loop
    token:=public.publication_pair_v1(f);
    if token=any(current_pairs) then continue; end if;
    select count(*) into n from public.proposals p where p.event_id=ev.id and p.kind='add_fight'
      and public.publication_pair_v1(p.payload)=token;
    if n<>1 then return jsonb_build_object('status','review_required','reason','missing_or_ambiguous_proposal','agenda_writes',false); end if;
    select * into strict prop from public.proposals p where p.event_id=ev.id and p.kind='add_fight'
      and public.publication_pair_v1(p.payload)=token for update;
    if prop.status<>'pending' or prop.source_kind<>'official'
       or public.publication_url_v1(prop.source_url,pol.allow_url_year_alias) is distinct from public.publication_url_v1(source,pol.allow_url_year_alias)
       or exists(select 1 from public.proposal_decisions where proposal_id=prop.id and decision in ('blocked','rejected')) then
      return jsonb_build_object('status','review_required','reason','proposal_not_admissible','agenda_writes',false);
    end if;
    candidates:=candidates||jsonb_build_array(jsonb_build_object('proposal_id',prop.id,'fight',f));
  end loop;
  if jsonb_array_length(candidates)=0 then return jsonb_build_object('status','already_present','event_id',ev.id,'agenda_writes',false,'inserted_fights','[]'::jsonb); end if;
  select count(*),min(position) into card_count,card from public.event_cards
    where event_id=ev.id and is_active and extra->>'allocation'='unassigned' and start_at is null;
  if card_count>1 then raise exception 'Ambiguous unassigned card'; end if;
  create_card:=card_count=0;
  if create_card then select coalesce(max(position),-1)+1 into card from public.event_cards where event_id=ev.id; end if;
  if not p_apply then return jsonb_build_object('status','preview','event_id',ev.id,'run_id',run.id,'policy_enabled',pol.enabled,
    'card_position',card,'create_card',create_card,'candidates',candidates,'agenda_writes',false); end if;
  if not pol.enabled then return jsonb_build_object('status','disabled','event_id',ev.id,'agenda_writes',false); end if;
  if create_card then
    insert into public.event_cards(event_id,position,name,start_at,level,source,extra)
    values(ev.id,card,'Combats officiels — répartition à confirmer',null,'official',source,
      jsonb_build_object('allocation','unassigned','source_url',source,'order_note','Ordre de source, sans horaire individuel déduit'));
    insert into public.publication_log(proposal_id,target_table,target_key,operation,payload,source_sha256)
    values((candidates->0->>'proposal_id')::uuid,'event_cards',jsonb_build_array(ev.id,card)::text,'insert',
      jsonb_build_object('allocation','unassigned','source_url',source,'run_id',run.id),run.source_sha256);
  end if;
  select coalesce(max(position),-1)+1 into pos from public.fights where event_id=ev.id and card_position=card;
  for f in select value from jsonb_array_elements(candidates) loop
    select * into strict prop from public.proposals where id=(f->>'proposal_id')::uuid;
    insert into public.fights(event_id,card_position,position,fighter_a,fighter_b)
    values(ev.id,card,pos,f#>>'{fight,fighter_a}',f#>>'{fight,fighter_b}');
    update public.proposals set status='published',auto_publishable=false,updated_at=clock_timestamp(),
      payload=(f->'fight')||jsonb_build_object('card_position',card,'position',pos,'allocation','unassigned'),
      evidence=evidence||jsonb_build_object('publication_run_id',run.id,'publication_report_sha256',run.source_sha256,
        'prepublication_state',jsonb_build_object('payload',prop.payload,'ingest_run_id',prop.ingest_run_id,'evidence',prop.evidence))
    where id=prop.id;
    insert into public.proposal_decisions(proposal_id,decision,decided_by,reason,evidence)
    values(prop.id,'published','shared-additions-v1','Ajout revalidé dans la transaction',jsonb_build_object('run_id',run.id,'report_sha256',run.source_sha256));
    insert into public.publication_log(proposal_id,target_table,target_key,operation,payload,source_sha256)
    values(prop.id,'fights',jsonb_build_array(ev.id,card,pos)::text,'insert',
      jsonb_build_object('fighter_a',f#>>'{fight,fighter_a}','fighter_b',f#>>'{fight,fighter_b}','source_url',source,'run_id',run.id),run.source_sha256);
    inserted:=inserted||jsonb_build_array(jsonb_build_object('fighter_a',f#>>'{fight,fighter_a}','fighter_b',f#>>'{fight,fighter_b}','position',pos));
    pos:=pos+1;
  end loop;
  return jsonb_build_object('status','published','event_id',ev.id,'run_id',run.id,'card_position',card,
                           'inserted_fights',inserted,'agenda_writes',true,'journal_writes',true);
end $$;
revoke all on function public.publication_pair_v1(jsonb) from public,anon,authenticated;
revoke all on function public.publication_url_v1(text,boolean) from public,anon,authenticated;
revoke all on function public.publish_event_additions_v1(uuid,text,boolean) from public,anon,authenticated;
grant execute on function public.publish_event_additions_v1(uuid,text,boolean) to service_role;
