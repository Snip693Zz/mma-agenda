-- Destructive only to the disposable CI database. Never run against production.
create role anon;
create role authenticated;
create role service_role;
create table public.events(id text primary key,org text not null,title text not null default '',event_date date not null,
 url text not null,official_card_url text,updated_at timestamptz not null default now());
create table public.event_cards(event_id text references events(id),position int,name text not null,
 start_at timestamptz,level text not null default 'secondary',source text not null default '',
 extra jsonb not null default '{}',is_active boolean not null default true,primary key(event_id,position));
create table public.fights(event_id text,card_position int,position int,fighter_a text not null,fighter_b text not null,
 primary key(event_id,card_position,position),foreign key(event_id,card_position) references event_cards(event_id,position));
create table public.ingest_runs(id uuid primary key default gen_random_uuid(),started_at timestamptz default now(),
 status text not null,source_report text not null,source_sha256 text not null,extra jsonb not null default '{}');
create table public.proposals(id uuid primary key default gen_random_uuid(),ingest_run_id uuid references ingest_runs(id),
 event_id text,kind text,status text,source_kind text,source_url text,payload jsonb,evidence jsonb not null default '{}',
 auto_publishable boolean not null default false,updated_at timestamptz default now(),journal_key text,
 check(journal_key is null or auto_publishable=false));
create table public.proposal_decisions(id uuid primary key default gen_random_uuid(),proposal_id uuid references proposals(id),
 decision text,decided_by text,reason text,evidence jsonb,created_at timestamptz default now());
create table public.publication_log(id uuid primary key default gen_random_uuid(),proposal_id uuid references proposals(id),
 target_table text,target_key text,operation text,payload jsonb,source_sha256 text not null);
