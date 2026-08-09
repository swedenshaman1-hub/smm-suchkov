-- Editorial draft state machine for /post. Apply once before deploying code.
create table if not exists public.editorial_drafts (
  draft_id text primary key check (draft_id <> '' and position(':' in draft_id) = 0 and octet_length(draft_id) <= 32),
  chat_id bigint not null,
  user_id bigint,
  status text not null check (status in ('generated','accepted','rejected','revised')),
  topic text not null,
  text text not null,
  planned_profile jsonb not null,
  actual_fingerprint jsonb not null,
  warnings jsonb not null default '[]'::jsonb check (jsonb_typeof(warnings) = 'array'),
  revision_context jsonb,
  revision_of text references public.editorial_drafts(draft_id) on delete restrict,
  revision_count integer not null default 0 check (revision_count in (0,1)),
  created_at timestamptz not null default now(),
  decided_at timestamptz,
  check (status = 'generated' or revision_context is null),
  check ((revision_count = 0 and revision_of is null) or
         (revision_count = 1 and revision_of is not null)),
  check ((status = 'generated' and decided_at is null) or
         (status <> 'generated' and decided_at is not null))
);

create index if not exists editorial_drafts_accepted_decided_idx
  on public.editorial_drafts (decided_at desc) where status = 'accepted';
create index if not exists editorial_drafts_chat_status_created_idx
  on public.editorial_drafts (chat_id, status, created_at desc);
create index if not exists editorial_drafts_revision_of_idx
  on public.editorial_drafts (revision_of);

alter table public.editorial_drafts enable row level security;
revoke all on table public.editorial_drafts from public, anon, authenticated;

create or replace function public.revise_editorial_draft(
  p_old_draft_id text,
  p_chat_id bigint,
  p_new_draft_id text,
  p_new_text text,
  p_planned_profile jsonb,
  p_actual_fingerprint jsonb,
  p_warnings jsonb,
  p_revision_context jsonb
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  changed_count integer;
  current_row public.editorial_drafts%rowtype;
begin
  if coalesce(p_old_draft_id, '') = '' or position(':' in p_old_draft_id) > 0 or
     coalesce(p_new_draft_id, '') = '' or position(':' in p_new_draft_id) > 0 or
     p_chat_id is null or coalesce(p_new_text, '') = '' or
     jsonb_typeof(coalesce(p_warnings, '[]'::jsonb)) <> 'array' then
    raise exception using errcode = '22023', message = 'invalid_input';
  end if;

  update public.editorial_drafts
     set status = 'revised', decided_at = now(), revision_context = null
   where draft_id = p_old_draft_id
     and chat_id = p_chat_id
     and status = 'generated'
     and revision_count = 0;
  get diagnostics changed_count = row_count;

  if changed_count <> 1 then
    select * into current_row from public.editorial_drafts where draft_id = p_old_draft_id;
    if not found then
      raise exception using errcode = 'P0001', message = 'not_found';
    elsif current_row.chat_id <> p_chat_id then
      raise exception using errcode = 'P0001', message = 'wrong_chat';
    elsif current_row.revision_count = 1 then
      raise exception using errcode = 'P0001', message = 'revision_limit';
    else
      raise exception using errcode = 'P0001', message = 'wrong_status:' || current_row.status;
    end if;
  end if;

  begin
    insert into public.editorial_drafts (
      draft_id, chat_id, status, topic, text, planned_profile,
      actual_fingerprint, warnings, revision_context, revision_of,
      revision_count, decided_at
    ) select
      p_new_draft_id, p_chat_id, 'generated', old.topic, p_new_text,
      p_planned_profile, p_actual_fingerprint, coalesce(p_warnings, '[]'::jsonb),
      p_revision_context, old.draft_id, 1, null
    from public.editorial_drafts old where old.draft_id = p_old_draft_id;
  exception when unique_violation then
    raise exception using errcode = 'P0001', message = 'insert_conflict';
  end;

  return jsonb_build_object('draft_id', p_new_draft_id, 'status', 'generated');
end;
$$;

revoke all on function public.revise_editorial_draft(text,bigint,text,text,jsonb,jsonb,jsonb,jsonb)
  from public, anon, authenticated;
grant execute on function public.revise_editorial_draft(text,bigint,text,text,jsonb,jsonb,jsonb,jsonb)
  to service_role;
