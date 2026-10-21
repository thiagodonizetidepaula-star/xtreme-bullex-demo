-- Mesa Trader DEMO · Aprendizado de padrões · Supabase Postgres
-- Migration idempotent; service_role only; NEVER accessible from anon browser.
-- 7-day rolling retention. Full long-term archive requires separate storage approval.
CREATE TABLE IF NOT EXISTS public.mesa_pattern_candles (
 asset text NOT NULL CHECK (char_length(asset) BETWEEN 3 AND 64),
 timeframe smallint NOT NULL CHECK (timeframe IN (1,5)),
 candle_time timestamptz NOT NULL,
 o double precision NOT NULL, h double precision NOT NULL,
 l double precision NOT NULL, c double precision NOT NULL,
 volume double precision,
 recorded_at timestamptz NOT NULL DEFAULT now(),
 CONSTRAINT pk_mesa_pattern_candles PRIMARY KEY(asset,timeframe,candle_time),
 CONSTRAINT mesa_pattern_ohlc CHECK(o>0 AND c>0 AND l>0 AND h>0
  AND o<1e12 AND c<1e12 AND h<1e12 AND l<=least(o,c) AND h>=greatest(o,c)
  AND (volume IS NULL OR volume>=0))
);
CREATE INDEX IF NOT EXISTS mesa_pattern_candles_time_idx
 ON public.mesa_pattern_candles(timeframe,candle_time);
CREATE TABLE IF NOT EXISTS public.mesa_pattern_payouts (
 asset text NOT NULL CHECK(char_length(asset) BETWEEN 3 AND 64),
 hour_utc timestamptz NOT NULL,
 payout numeric(5,2) NOT NULL CHECK(payout>=0 AND payout<=100),
 observed_at timestamptz NOT NULL,
 CONSTRAINT pk_mesa_pattern_payouts PRIMARY KEY(asset,hour_utc)
);
CREATE INDEX IF NOT EXISTS mesa_pattern_payouts_time_idx
 ON public.mesa_pattern_payouts(hour_utc);
CREATE TABLE IF NOT EXISTS public.mesa_patterns (
 pattern_id text PRIMARY KEY CHECK(char_length(pattern_id) BETWEEN 5 AND 100),
 source_model text NOT NULL CHECK(source_model IN ('shallow_tree','baseline_5of6')),
 direction text NOT NULL CHECK(direction IN ('CALL','PUT')),
 expiration_m1 smallint NOT NULL CHECK(expiration_m1 IN (1,5)),
 rule jsonb NOT NULL CHECK(jsonb_typeof(rule)='array'),
 trained_until timestamptz NOT NULL,oos_start timestamptz NOT NULL,oos_end timestamptz NOT NULL,
 oos_occurrences integer NOT NULL CHECK(oos_occurrences>=0),
 oos_wins integer NOT NULL CHECK(oos_wins>=0),
 oos_lower_95 double precision NOT NULL,equilibrium_rate double precision NOT NULL,
 expectancy_per_stake double precision NOT NULL,stable_folds integer NOT NULL DEFAULT 0,
 approved boolean NOT NULL DEFAULT false,active boolean NOT NULL DEFAULT false,
 disabled_reason text,generated_at timestamptz NOT NULL DEFAULT now(),
 CHECK(oos_wins<=oos_occurrences),
 CHECK(oos_lower_95 BETWEEN 0 AND 1),CHECK(equilibrium_rate BETWEEN 0 AND 1),
 CHECK(NOT approved OR (oos_occurrences>=300 AND oos_lower_95>equilibrium_rate AND stable_folds>=2)),
 CHECK(NOT active OR approved)
);
CREATE TABLE IF NOT EXISTS public.mesa_pattern_runs (
 run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 started_at timestamptz NOT NULL DEFAULT now(),finished_at timestamptz,
 dataset_first timestamptz,dataset_last timestamptz,candles_used integer NOT NULL DEFAULT 0,
 folds_checked integer NOT NULL DEFAULT 0,approved_count integer NOT NULL DEFAULT 0,
 outcome text NOT NULL DEFAULT 'IN_PROGRESS',notes text
);
ALTER TABLE public.mesa_pattern_candles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mesa_pattern_payouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mesa_patterns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mesa_pattern_runs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.mesa_pattern_candles,public.mesa_pattern_payouts,
 public.mesa_patterns,public.mesa_pattern_runs FROM anon,authenticated;

CREATE OR REPLACE FUNCTION public.mesa_pattern_housekeeping()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE n1 integer; n2 integer; b bigint;
BEGIN
 DELETE FROM public.mesa_pattern_candles WHERE candle_time<now()-interval '7 days';
 GET DIAGNOSTICS n1=ROW_COUNT;
 DELETE FROM public.mesa_pattern_payouts WHERE hour_utc<now()-interval '7 days';
 GET DIAGNOSTICS n2=ROW_COUNT;
 b=pg_database_size(current_database());
 RETURN jsonb_build_object('deleted_candles',n1,'deleted_payouts',n2,
   'database_bytes',b,'limit_bytes',367001600);
END $$;
REVOKE ALL ON FUNCTION public.mesa_pattern_housekeeping() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.mesa_pattern_housekeeping() TO service_role;
CREATE OR REPLACE FUNCTION public.mesa_pattern_storage()
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
 SELECT jsonb_build_object('database_bytes',pg_database_size(current_database()),
  'limit_bytes',367001600,
  'candles',(SELECT count(*) FROM public.mesa_pattern_candles),
  'oldest',(SELECT min(candle_time) FROM public.mesa_pattern_candles),
  'newest',(SELECT max(candle_time) FROM public.mesa_pattern_candles));
$$;
REVOKE ALL ON FUNCTION public.mesa_pattern_storage() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.mesa_pattern_storage() TO service_role;

-- One transaction re-evaluates all active patterns; empty batch deactivates all.
CREATE OR REPLACE FUNCTION public.mesa_activate_validated_patterns(raw jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE r jsonb;n integer:=0;
BEGIN
 IF jsonb_typeof(raw)<>'array' OR jsonb_array_length(raw)>100
 THEN RAISE EXCEPTION 'Invalid pattern batch';END IF;
 UPDATE public.mesa_patterns SET active=false,disabled_reason='Substituído na revisão semanal'
 WHERE active=true;
 FOR r IN SELECT value FROM jsonb_array_elements(raw) LOOP
 IF coalesce((r->>'oos_occurrences')::integer,0)<300
  OR coalesce((r->>'stable_folds')::integer,0)<2
  OR coalesce((r->>'oos_lower_95')::double precision,0)
    <=coalesce((r->>'equilibrium_rate')::double precision,1)
  OR (r->>'approved')::boolean IS DISTINCT FROM true
  OR (r->>'active')::boolean IS DISTINCT FROM true
  OR jsonb_typeof(r->'rule')<>'array'
 THEN RAISE EXCEPTION 'Pattern not validated';END IF;
 INSERT INTO public.mesa_patterns(pattern_id,source_model,direction,expiration_m1,rule,
  trained_until,oos_start,oos_end,oos_occurrences,oos_wins,oos_lower_95,
  equilibrium_rate,expectancy_per_stake,stable_folds,approved,active,disabled_reason)
 VALUES(r->>'pattern_id',r->>'source_model',r->>'direction',
  (r->>'expiration_m1')::smallint,r->'rule',(r->>'trained_until')::timestamptz,
  (r->>'oos_start')::timestamptz,(r->>'oos_end')::timestamptz,
  (r->>'oos_occurrences')::integer,(r->>'oos_wins')::integer,
  (r->>'oos_lower_95')::double precision,(r->>'equilibrium_rate')::double precision,
  (r->>'expectancy_per_stake')::double precision,(r->>'stable_folds')::integer,
  true,true,null)
 ON CONFLICT(pattern_id) DO UPDATE SET rule=excluded.rule,trained_until=excluded.trained_until,
  oos_start=excluded.oos_start,oos_end=excluded.oos_end,
  oos_occurrences=excluded.oos_occurrences,oos_wins=excluded.oos_wins,
  oos_lower_95=excluded.oos_lower_95,equilibrium_rate=excluded.equilibrium_rate,
  expectancy_per_stake=excluded.expectancy_per_stake,stable_folds=excluded.stable_folds,
  approved=true,active=true,disabled_reason=null,generated_at=now();
 n=n+1;
 END LOOP;
 RETURN jsonb_build_object('activated',n);
END $$;
REVOKE ALL ON FUNCTION public.mesa_activate_validated_patterns(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.mesa_activate_validated_patterns(jsonb) TO service_role;

-- Disable approved pattern when LAST 50 ACTUAL PRACTICE trades drop below break-even.
CREATE OR REPLACE FUNCTION public.mesa_guard_patterns()
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=public AS $$
DECLARE changed integer:=0;
BEGIN
 WITH per_pattern AS (
 SELECT p.pattern_id,p.equilibrium_rate,
  (SELECT count(*) FROM
    (SELECT t.payload->>'status' AS status FROM public.mesa_trade_history t
     WHERE t.payload->>'pattern_id'=p.pattern_id AND t.status IN ('WIN','LOSS')
     ORDER BY t.created_at DESC LIMIT 50) x) AS n,
  (SELECT count(*) FROM
    (SELECT t.status FROM public.mesa_trade_history t
     WHERE t.payload->>'pattern_id'=p.pattern_id AND t.status IN ('WIN','LOSS')
     ORDER BY t.created_at DESC LIMIT 50) x WHERE x.status='WIN') AS wins
 FROM public.mesa_patterns p WHERE p.active=true
 )
 UPDATE public.mesa_patterns p
 SET active=false,disabled_reason='Últimas 50 operações abaixo do equilíbrio'
 FROM per_pattern q WHERE p.pattern_id=q.pattern_id
 AND q.n=50 AND q.wins::double precision/50<q.equilibrium_rate;
 GET DIAGNOSTICS changed=ROW_COUNT;
 RETURN jsonb_build_object('disabled_last_50',changed);
END $$;
REVOKE ALL ON FUNCTION public.mesa_guard_patterns() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.mesa_guard_patterns() TO service_role;
