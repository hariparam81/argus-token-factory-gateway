-- D4: every call from D1-D3 (window 2026-10-29T00:22:33Z to 2026-10-29T00:57:32Z), grouped by tenant, identity mode, subject, actor.
-- Audit intent rows joined to LiteLLM spend logs on the response id; calls rejected before or by LiteLLM have no spend row.
select a.tenant, a.identity_mode, a.subject, coalesce(a.actor,'-') as actor,
       count(*) as calls,
       count(*) filter (where a.http_status = 200) as ok,
       count(*) filter (where a.http_status <> 200 or a.rejected) as not_ok,
       coalesce(sum(s.prompt_tokens),0) as prompt_tokens,
       coalesce(sum(s.completion_tokens),0) as completion_tokens,
       coalesce(sum(s.total_tokens),0) as total_tokens,
       round(coalesce(sum(s.spend),0)::numeric, 6) as cost_usd
from argus.audit_intent a
left join "LiteLLM_SpendLogs" s on s.request_id = a.litellm_call_id
where a.ts >= '2026-10-29T00:22:33Z' and a.ts <= '2026-10-29T00:57:32Z'
group by 1,2,3,4
order by 1,2,3,4;

-- window totals
select count(*) as calls, round(coalesce(sum(s.spend),0)::numeric,6) as cost_usd, coalesce(sum(s.total_tokens),0) as total_tokens
from argus.audit_intent a left join "LiteLLM_SpendLogs" s on s.request_id = a.litellm_call_id
where a.ts >= '2026-10-29T00:22:33Z' and a.ts <= '2026-10-29T00:57:32Z';

-- non-200 outcomes inside the window
select a.tenant, a.identity_mode, a.http_status, a.rejected, coalesce(a.reject_reason,'(from LiteLLM)') as reason, count(*)
from argus.audit_intent a where a.ts >= '2026-10-29T00:22:33Z' and a.ts <= '2026-10-29T00:57:32Z' and (a.http_status <> 200 or a.rejected) group by 1,2,3,4,5 order by 1,2,3;

-- rejected calls from the Phase 2 negative tests, listed separately (before the demo window)
select to_char(ts,'MM-DD HH24:MI:SS') as at, coalesce(reject_reason,'') as reason, http_status
from argus.audit_intent where rejected and ts < '2026-10-29T00:22:33Z' and ts >= '2026-10-29 00:00:00' order by ts;
