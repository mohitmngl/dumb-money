"""Detect and repair stock-split corruption in stored daily bars.

Problem: US bars are downloaded from Alpaca with adjustment="split" and India
bars from Yahoo raw quote OHLC. Bars downloaded BEFORE a split keep the old
price basis; incremental refresh only appends new bars, so history is price-
inconsistent across split dates (e.g. HON 2:1 on 2026-06-29 stored as a -50%
day). This corrupts ath/atl/change_pct/new_ath/new_atl for affected symbols.

Phases (run stepwise):
  python _fix_splits.py detect     # heuristic scan -> _split_candidates.json
  python _fix_splits.py india      # verify India candidates via Yahoo split events -> _india_repair.json
  python _fix_splits.py us         # re-download full adjusted history (Alpaca) for US candidates
  python _fix_splits.py splice     # apply split splice to India bars locally
  python _fix_splits.py rebuild    # force-rebuild hist + stats for all affected symbols
  python _fix_splits.py verify     # HON + spot checks

US repair = authoritative re-download (split-adjusted), false positives are
harmless no-ops. India repair = local multiplicative splice at Yahoo-confirmed
split dates only, keeping the raw-price basis so future incremental appends
stay consistent.
"""
import json
import os
import sys
import time
from datetime import datetime as dt
from statistics import median

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dumbmoney.db import get_db

CAND_FILE = "_split_candidates.json"
INDIA_FILE = "_india_repair.json"

# Common split ratios (share multiplier). Reciprocals cover reverse splits.
FACTORS = []
for f in (1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20, 25, 30, 40, 50, 75, 100):
    FACTORS.append(f)
    FACTORS.append(round(1.0 / f, 8))
GAP_TOL = 0.05      # gap ratio within +/-5% of a clean factor
LEVEL_TOL = 0.08    # median level shift within +/-8% of same factor
PRE_N, POST_N, POST_MIN = 15, 15, 8


def _match_factor(r):
    for f in FACTORS:
        if abs(r - f) / f <= GAP_TOL:
            return f
    return None


def detect():
    """Flag symbols whose bars show a clean-factor overnight gap that PERSISTS
    (median of PRE_N closes before / POST_N closes after matches the same
    factor). Oscillating penny stocks fail the persistence test."""
    out = {}
    for market, dbkey in (("US", "US"), ("INDIA", "INDIA")):
        conn = get_db(dbkey)
        sym = None
        dates, opens, closes = [], [], []
        hits = {}

        def flush(sym, dates, opens, closes):
            n = len(closes)
            ev = []
            for i in range(1, n):
                if not opens[i] or opens[i] <= 0 or closes[i - 1] <= 0:
                    continue
                f = _match_factor(closes[i - 1] / opens[i])
                if f is None:
                    continue
                lo = max(0, i - PRE_N)
                hi = min(n, i + POST_N)
                if i - lo < 3 or hi - i < POST_MIN:
                    continue
                prev_med = median(closes[lo:i])
                post_med = median(closes[i:hi])
                if prev_med <= 0 or post_med <= 0:
                    continue
                shift = prev_med / post_med
                if abs(shift - f) / f <= LEVEL_TOL:
                    ev.append((dates[i], f))
            return ev

        t0 = time.time()
        rows = conn.execute(
            "SELECT symbol, date, open, close FROM bars WHERE timeframe='1Day' ORDER BY symbol, date"
        )
        nsym = 0
        for s, d, o, c in rows:
            if s != sym:
                if sym is not None:
                    ev = flush(sym, dates, opens, closes)
                    if ev:
                        hits[sym] = ev
                        nsym += 1
                sym, dates, opens, closes = s, [], [], []
            dates.append(d)
            opens.append(o)
            closes.append(c)
        if sym is not None:
            ev = flush(sym, dates, opens, closes)
            if ev:
                hits[sym] = ev
                nsym += 1
        out[market] = hits
        ngaps = sum(len(v) for v in hits.values())
        print(f"{market}: {nsym} symbols with split-like persistent gaps "
              f"({ngaps} events) in {time.time()-t0:.0f}s", flush=True)
        conn.close()

    with open(CAND_FILE, "w") as fp:
        json.dump(out, fp)
    print(f"wrote {CAND_FILE}")


# ---------------------------------------------------------------- India ----

def _yahoo_splits(sym, session, crumb):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{sym}"
    p2 = int(dt.now().timestamp())
    params = {"period1": 0, "period2": p2, "interval": "1mo",
              "events": "splits", "crumb": crumb}
    r = session.get(url, params=params, timeout=10)
    if r.status_code != 200:
        return None
    try:
        res = r.json()["chart"]["result"][0]
    except Exception:
        return None
    ev = res.get("events", {}).get("splits", {})
    out = {}
    for k, v in ev.items():
        d = dt.utcfromtimestamp(int(v.get("date", k))).strftime("%Y-%m-%d")
        num = float(v.get("numerator", 0))
        den = float(v.get("denominator", 0))
        if num > 0 and den > 0:
            out[d] = num / den  # share multiplier: prices before ex-date divide by this
    return out


def india_verify():
    """For each India candidate, fetch real split events from Yahoo. A symbol
    needs repair iff it has a split strictly between first and last bar."""
    from dumbmoney.data_india import _init_yf_sessions, _get_yf_session
    cands = json.load(open(CAND_FILE))["INDIA"]
    _init_yf_sessions()
    repair = {}
    t0 = time.time()
    for i, sym in enumerate(sorted(cands)):
        session, crumb = _get_yf_session()
        sp = _yahoo_splits(sym, session, crumb)
        if sp is None:
            print(f"  ? {sym}: no split info returned", flush=True)
            continue
        if not sp:
            continue
        row = get_db("INDIA").execute(
            "SELECT MIN(date), MAX(date) FROM bars WHERE symbol=?", (sym,)
        ).fetchone()
        dmin, dmax = row[0], row[1]
        inside = {d: pf for d, pf in sorted(sp.items()) if dmin < d <= dmax}
        if inside:
            repair[sym] = inside
            print(f"  {sym}: splits {inside}", flush=True)
        if (i + 1) % 50 == 0:
            print(f"  ...{i+1}/{len(cands)} checked ({len(repair)} need repair)", flush=True)
        time.sleep(0.15)
    with open(INDIA_FILE, "w") as fp:
        json.dump(repair, fp)
    print(f"INDIA: {len(repair)} symbols to splice (of {len(cands)} candidates) "
          f"in {time.time()-t0:.0f}s -> {INDIA_FILE}", flush=True)


def india_splice():
    """Yahoo's chart API returns split-adjusted OHLC, but deep/old boundaries
    sometimes leak through unadjusted (e.g. TRENT 2005 5:1 stored as -90%).
    For each known split ex-date, divide all earlier bars by the share
    multiplier ONLY IF the stored series still shows the 1/pf discontinuity
    at that date (gated — double-adjustment is worse than none).
    Run AFTER 'india-refresh' restored pristine Yahoo data."""
    repair = json.load(open(INDIA_FILE))
    conn = get_db("INDIA")
    total_rows = fixed_events = 0
    t0 = time.time()
    for sym, splits in sorted(repair.items()):
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM bars "
            "WHERE symbol=? AND timeframe='1Day' ORDER BY date", (sym,)
        ).fetchall()
        dates = [r[0] for r in rows]
        idx = {d: i for i, d in enumerate(dates)}
        fixes = []  # (row index of ex-date, pf)
        for sd, pf in sorted(splits.items()):
            i = idx.get(sd)
            if not i or not rows[i][1] or rows[i - 1][4] <= 0:
                continue
            r = rows[i - 1][4] / rows[i][1]   # prev close / ex-date open
            expect = 1.0 / pf
            if abs(r - expect) / expect <= 0.10:
                fixes.append((i, pf))
        if not fixes:
            continue
        fixes.sort()
        updates = []
        m = 1.0
        fi = 0
        for j, (d, o, h, l, c, v) in enumerate(rows):
            while fi < len(fixes) and fixes[fi][0] == j:
                m *= fixes[fi][1]  # stops applying from ex-date onward
                fi += 1
            if m == 1.0:
                continue
            updates.append((round(o / m, 4), round(h / m, 4), round(l / m, 4),
                            round(c / m, 4), int(round(v * m)), sym, d))
        if updates:
            conn.executemany(
                "UPDATE bars SET open=?, high=?, low=?, close=?, volume=? "
                "WHERE symbol=? AND date=? AND timeframe='1Day'", updates)
            conn.commit()
            total_rows += len(updates)
            fixed_events += len(fixes)
            print(f"  {sym}: {len(updates)} bars spliced at {len(fixes)}/{len(splits)} splits",
                  flush=True)
    print(f"INDIA gated splice done: {total_rows} bars, {fixed_events} events "
          f"across {len(repair)} symbols in {time.time()-t0:.0f}s", flush=True)


def india_refresh():
    """Overwrite full history for repair-list symbols straight from Yahoo
    (period1=0), restoring the source's own consistent adjusted basis."""
    import json as _json
    from dumbmoney.data_india import _init_yf_sessions, _download_one
    syms = sorted(_json.load(open(INDIA_FILE)))
    _init_yf_sessions()
    conn = get_db("INDIA")
    done = empty = 0
    t0 = time.time()
    for sym in syms:
        _, bars = _download_one(sym, None)
        if bars:
            conn.executemany(
                "INSERT OR REPLACE INTO bars (symbol,timeframe,date,open,high,low,close,volume) "
                "VALUES (?, '1Day', ?, ?, ?, ?, ?, ?)", bars)
            conn.commit()
            done += 1
        else:
            empty += 1
            print(f"  EMPTY: {sym}", flush=True)
        time.sleep(0.1)
    print(f"INDIA refresh: {done} refreshed, {empty} empty in {time.time()-t0:.0f}s", flush=True)


# ------------------------------------------------------------------- US ----

def us_redownload():
    cands = sorted(json.load(open(CAND_FILE))["US"])
    print(f"US: re-downloading full adjusted history for {len(cands)} symbols...", flush=True)
    from dumbmoney.data_us import download_bars
    n = download_bars(cands, start_date="1970-01-01")
    print(f"US re-download wrote {n} bars", flush=True)


RAW_FILE = "_us_raw_syms.json"


def classify():
    """Split-adjustment inflates pre-event history across reverse splits while
    concurrent spin-offs halve real value -> fake crash day. Symbols whose
    corporate-actions show a reverse split within +/-3 days of a spin-off are
    stored RAW instead (as-traded truth). Scans every US symbol in bars."""
    from dumbmoney.data_us import _api_get, ALPACA_DATA_URL
    conn = get_db("US")
    syms = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM bars WHERE timeframe='1Day' ORDER BY symbol")]
    rev, spino = {}, {}
    B = 100
    for i in range(0, len(syms), B):
        chunk = syms[i:i + B]
        token = None
        for _ in range(10):  # page through
            params = {"symbols": ",".join(chunk), "start": "1990-01-01",
                      "end": dt.now().strftime("%Y-%m-%d"), "limit": 1000,
                      "types": "reverse_split,forward_split,spin_off"}
            if token:
                params["page_token"] = token
            d = _api_get(f"{ALPACA_DATA_URL}/v1/corporate-actions", params=params)
            if not d:
                break
            ca = d.get("corporate_actions", {})
            for x in ca.get("reverse_splits", []):
                rev.setdefault(x.get("symbol"), []).append(x["ex_date"])
            for x in ca.get("spin_offs", []):
                spino.setdefault(x.get("source_symbol") or x.get("symbol"), []).append(x["ex_date"])
            token = d.get("next_page_token")
            if not token:
                break
        if (i // B) % 10 == 0:
            print(f"  ...{i + B}/{len(syms)} symbols", flush=True)
    raw_syms = []
    for s, rdates in rev.items():
        sdates = spino.get(s, [])
        if sdates and any(min(abs(_d(x) - _d(y)) for y in sdates) <= 3 for x in rdates):
            raw_syms.append(s)
    raw_syms.sort()
    with open(RAW_FILE, "w") as fp:
        json.dump(raw_syms, fp)
    print(f"US: {len(rev)} symbols with reverse splits, {len(raw_syms)} reverse+spinoff "
          f"-> raw basis: {raw_syms[:25]}{'...' if len(raw_syms) > 25 else ''}", flush=True)


def _d(s):
    return dt.strptime(s, "%Y-%m-%d").toordinal()


def us_raw_redownload():
    syms = json.load(open(RAW_FILE))
    # keep only symbols that actually have stored bars
    conn = get_db("US")
    have = {r[0] for r in conn.execute(
        f"SELECT DISTINCT symbol FROM bars WHERE timeframe='1Day' AND symbol IN ({','.join('?' * len(syms))})", syms)}
    syms = sorted(have)
    print(f"US: re-downloading RAW full history for {len(syms)} reverse+spinoff symbols...", flush=True)
    from dumbmoney.data_us import download_bars
    n = download_bars(syms, start_date="1970-01-01", adjustment="raw")
    print(f"US raw re-download wrote {n} bars", flush=True)


# --------------------------------------------------------------- rebuild ---

def rebuild():
    cands = json.load(open(CAND_FILE))
    raw = []
    if os.path.exists(RAW_FILE):
        raw = json.load(open(RAW_FILE))
    us_syms = sorted(set(cands["US"]) | set(raw))
    from dumbmoney.engine import update_historical_screener, vectorized_stats_pass
    for market, syms in (("US", us_syms), ("INDIA", sorted(json.load(open(INDIA_FILE))))):
        if not syms:
            print(f"{market}: nothing to rebuild")
            continue
        syms = sorted(syms)
        print(f"{market}: rebuilding hist for {len(syms)} symbols...", flush=True)
        update_historical_screener(market, only_symbols=syms, force_rebuild=True,
                                   parallel=8)
        print(f"{market}: stats pass for {len(syms)} symbols...", flush=True)
        vectorized_stats_pass(market, only_symbols=syms)
        print(f"{market} done", flush=True)


# --------------------------------------------------------------- verify ----

def verify():
    conn = get_db("US")
    print("HON boundary (2026-06-26..29):")
    for r in conn.execute(
        "SELECT date, open, high, low, close, volume FROM bars "
        "WHERE symbol='HON' AND timeframe='1Day' AND date BETWEEN '2026-06-25' AND '2026-06-30' ORDER BY date"):
        print("  ", tuple(r))
    print("HON earliest bars:")
    for r in conn.execute(
        "SELECT date, open, close FROM bars WHERE symbol='HON' AND timeframe='1Day' ORDER BY date LIMIT 3"):
        print("  ", tuple(r))
    print("HON hist around Feb 2026 (ath/atl/new flags):")
    for r in conn.execute(
        "SELECT date, round(low,2), round(ath,2), round(atl,2), change_pct, new_ath, new_atl "
        "FROM historical_screener WHERE symbol='HON' AND date LIKE '2026-02%' ORDER BY date LIMIT 25"):
        print("  ", tuple(r))
    print("HON fake-crash check (hist change_pct < -25% since Jun 2026):")
    for r in conn.execute(
        "SELECT date, change_pct FROM historical_screener WHERE symbol='HON' AND date>='2026-06-01' "
        "AND ABS(change_pct)>25 ORDER BY date"):
        print("  ", tuple(r))

    conn = get_db("INDIA")
    print("INDIA spot checks (first/last spliced symbols):")
    repair = json.load(open(INDIA_FILE))
    for sym in list(sorted(repair))[:3]:
        gaps = conn.execute(
            """SELECT COUNT(*) FROM (
                 SELECT date, LAG(close) OVER (ORDER BY date) pc, open o
                 FROM bars WHERE symbol=? AND timeframe='1Day')
               WHERE pc IS NOT NULL AND o>0 AND ABS(pc/o - ?)/? <= 0.05""",
            (sym, 2.0, 2.0)).fetchone()[0]
        print(f"  {sym}: residual 2x-factor gaps after splice: {gaps}")


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    fn = {"detect": detect, "india": india_verify, "us": us_redownload,
          "classify": classify, "us-raw": us_raw_redownload,
          "splice": india_splice, "india-refresh": india_refresh,
          "rebuild": rebuild, "verify": verify}.get(phase)
    if not fn:
        sys.exit("usage: python _fix_splits.py [detect|india|us|classify|us-raw|india-refresh|splice|rebuild|verify]")
    fn()
    print("DONE")
