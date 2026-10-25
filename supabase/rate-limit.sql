begin;
create table if not exists public.review_attempts (
  fingerprint text primary key,
  attempted_at timestamptz not null default now()
);
alter table public.review_attempts enable row level security;
revoke all on public.review_attempts from anon, authenticated;
create or replace function public.claim_review_attempt(fingerprint text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare accepted boolean;
begin
  delete from public.review_attempts where attempted_at < now() - interval '1 day';
  insert into public.review_attempts as attempts (fingerprint, attempted_at)
  values (claim_review_attempt.fingerprint, now())
  on conflict on constraint review_attempts_pkey do update set attempted_at = now()
  where attempts.attempted_at <= now() - interval '30 seconds'
  returning true into accepted;
  return coalesce(accepted, false);
end;
$$;
revoke all on function public.claim_review_attempt(text) from public, anon, authenticated;
grant execute on function public.claim_review_attempt(text) to service_role;
commit;
