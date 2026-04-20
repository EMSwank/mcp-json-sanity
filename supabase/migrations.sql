-- Run this once in your Supabase SQL editor to create the logging table.

create table if not exists sanitize_logs (
    id          bigint generated always as identity primary key,
    created_at  timestamptz default now() not null,
    input_length    int     not null,
    repair_performed boolean not null,
    api_key_id  text
);

-- Index for per-key metrics queries
create index if not exists sanitize_logs_api_key_id_idx
    on sanitize_logs (api_key_id);

-- Convenience view: crashes prevented per API key
create or replace view crashes_prevented_by_key as
select
    api_key_id,
    count(*)                                        as total_calls,
    count(*) filter (where repair_performed = true) as crashes_prevented
from sanitize_logs
group by api_key_id
order by crashes_prevented desc;
