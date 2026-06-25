-- Analyse-Ergebnisse
create table if not exists analyses (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  website_url text not null,
  industry text,
  benefits jsonb default '[]',
  vibe text,
  jobs jsonb default '[]',
  analyzed_at timestamptz default now(),
  created_at timestamptz default now()
);

create table if not exists analysis_jobs (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  website_url text not null,
  status text not null default 'queued',
  progress text,
  analysis_id uuid references analyses(id),
  error_message text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists encrypted_secrets (
  id uuid primary key default gen_random_uuid(),
  secret_name text not null unique,
  provider text not null,
  ciphertext bytea not null,
  nonce bytea not null,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Job-Recovery und Admin-Abfragen
create index if not exists idx_analysis_jobs_status on analysis_jobs (status);
create index if not exists idx_analysis_jobs_created_at on analysis_jobs (created_at);
create index if not exists idx_analyses_created_at on analyses (created_at desc);

-- RLS: öffentlicher Zugriff blockieren (service_role der Flask-App umgeht RLS)
alter table analyses enable row level security;
alter table analysis_jobs enable row level security;
alter table encrypted_secrets enable row level security;
