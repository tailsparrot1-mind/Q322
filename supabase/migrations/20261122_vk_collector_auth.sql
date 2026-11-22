-- Vkus VK collector authentication and source registration.
-- Apply after the Vkus demand-engine schema has created private.demand_sources
-- and public.external_demand. No service-role key is stored in the desktop app.

create table if not exists private.collector_tokens (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references private.demand_sources(id) on delete cascade,
  token_hash text not null unique,
  label text not null default 'VK desktop collector',
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at timestamptz
);

grant usage on schema private to service_role;
revoke all on private.collector_tokens from public, anon, authenticated;
grant all on private.collector_tokens to service_role;

create or replace function public.verify_vkus_collector_token(p_token_hash text)
returns uuid
language plpgsql
security definer
set search_path = public, private, pg_temp
as $$
declare
  v_source_id uuid;
begin
  update private.collector_tokens t
     set last_used_at = now()
    from private.demand_sources s
   where t.source_id = s.id
     and t.token_hash = p_token_hash
     and t.enabled = true
     and t.revoked_at is null
     and s.enabled = true
     and s.terms_reviewed_at is not null
  returning t.source_id into v_source_id;

  return v_source_id;
end;
$$;

revoke all on function public.verify_vkus_collector_token(text) from public, anon, authenticated;
grant execute on function public.verify_vkus_collector_token(text) to service_role;

create or replace function public.issue_vkus_collector_token(
  p_source_id uuid,
  p_label text default 'VK desktop collector'
)
returns text
language plpgsql
security definer
set search_path = public, private, extensions, pg_temp
as $$
declare
  v_token text;
begin
  if not exists (
    select 1 from private.demand_sources
    where id = p_source_id
      and enabled = true
      and terms_reviewed_at is not null
  ) then
    raise exception 'Source must be enabled and terms-reviewed before issuing a collector token';
  end if;

  v_token := encode(gen_random_bytes(32), 'hex');

  insert into private.collector_tokens(source_id, token_hash, label)
  values (
    p_source_id,
    encode(digest(v_token, 'sha256'), 'hex'),
    left(coalesce(nullif(btrim(p_label), ''), 'VK desktop collector'), 120)
  );

  return v_token;
end;
$$;

revoke all on function public.issue_vkus_collector_token(uuid, text) from public, anon, authenticated;
grant execute on function public.issue_vkus_collector_token(uuid, text) to service_role;

insert into private.demand_sources
  (id, platform, source_key, source_url, source_kind, access_mode, enabled, terms_reviewed_at, config)
values
  ('4a2731fe-c51c-4ceb-867e-402542881e31', 'vk', 'public-post-search',
   'https://vk.com/search', 'search_query', 'browser_session', false, null,
   '{"scope":"public_posts_only","collection_mode":"visible_browser_session","manual_login":true,"private_content":false,"messaging":false,"review_required":true}'::jsonb)
on conflict (platform, source_key) do nothing;
