import requests

checks = []
base = 'http://localhost:8474'

def check(name, url, validator=None):
    try:
        r = requests.get(f'{base}{url}', timeout=60)
        data = r.json()
        rows = data.get('data', data.get('rows', []))
        if validator:
            ok = validator(data, rows)
        else:
            ok = r.status_code == 200 and len(rows) > 0
        checks.append((name, ok, ''))
    except Exception as e:
        checks.append((name, False, str(e)[:80]))

def has_rows(d, r):
    return len(r) > 0

def has_real_pst(d, r):
    vals = [row.get('prob_up_st_cross') for row in r if row.get('prob_up_st_cross') is not None]
    return len(vals) > 0 and any(v != 50.0 for v in vals)

# Stock screener
check('US stock current', '/api/screener?market=US&per_page=3', has_rows)
check('India stock current', '/api/screener?market=INDIA&per_page=3', has_rows)
check('US stock hist', '/api/screener?market=US&date_cutoff=2025-01-02&per_page=3', has_rows)
check('India stock hist', '/api/screener?market=INDIA&date_cutoff=2025-01-02&per_page=3', has_rows)

# Stock sort pst
check('US stock sort pst asc', '/api/screener?market=US&sort_by=prob_up_st_cross&sort_dir=asc&per_page=5', has_rows)
check('US stock sort pst desc', '/api/screener?market=US&sort_by=prob_up_st_cross&sort_dir=desc&per_page=5', has_rows)
check('US stock hist sort pst desc', '/api/screener?market=US&date_cutoff=2025-01-02&sort_by=prob_up_st_cross&sort_dir=desc&per_page=5', has_rows)

# Stock has real pst values
check('US stock current real pst', '/api/screener?market=US&per_page=10', has_real_pst)

# Basket screener
check('US basket current', '/api/basket-screener?market=US&per_page=3', has_rows)
check('US LS current', '/api/basket-screener?market=US&long_short=true&per_page=3', has_rows)
check('US basket hist', '/api/basket-screener?market=US&date_cutoff=2025-01-02&per_page=3', has_rows)
check('US LS hist', '/api/basket-screener?market=US&long_short=true&date_cutoff=2025-01-02&per_page=3', has_rows)

# Basket sort pst
check('US basket sort pst asc', '/api/basket-screener?market=US&sort_by=prob_up_st_cross&sort_dir=asc&per_page=5', has_rows)
check('US basket sort pst desc', '/api/basket-screener?market=US&sort_by=prob_up_st_cross&sort_dir=desc&per_page=5', has_rows)
check('US basket hist sort pst desc', '/api/basket-screener?market=US&date_cutoff=2025-01-02&sort_by=prob_up_st_cross&sort_dir=desc&per_page=5', has_rows)

# LS sort
check('US LS sort pst asc', '/api/basket-screener?market=US&long_short=true&sort_by=prob_up_st_cross&sort_dir=asc&per_page=5', has_rows)
check('US LS hist sort pst desc', '/api/basket-screener?market=US&long_short=true&date_cutoff=2025-01-02&sort_by=prob_up_st_cross&sort_dir=desc&per_page=5', has_rows)

# Basket/LS real pst values
check('US basket hist real pst', '/api/basket-screener?market=US&date_cutoff=2025-01-02&per_page=10&sort_by=prob_up_st_cross&sort_dir=desc', has_real_pst)
check('US LS hist real pst', '/api/basket-screener?market=US&long_short=true&date_cutoff=2025-01-02&per_page=10&sort_by=prob_up_st_cross&sort_dir=desc', has_real_pst)

# Columns
check('Columns has pst', '/api/screener/columns',
      lambda d, r: any(c.get('key') == 'prob_up_st_cross' for c in (r if isinstance(r, list) else d.get('data', d)) if isinstance(c, dict)))

# India basket
check('India basket current', '/api/basket-screener?market=INDIA&per_page=3', has_rows)
check('India basket hist', '/api/basket-screener?market=INDIA&date_cutoff=2025-01-02&per_page=3', has_rows)

# Refresh status
check('US refresh status', '/api/refresh/status?market=US',
      lambda d, r: 'status' in d)
check('India refresh status', '/api/refresh/status?market=INDIA',
      lambda d, r: 'status' in d)

# Print results
passed = sum(1 for _, p, _ in checks if p)
failed = [(n, e) for n, p, e in checks if not p]
print(f'\n{passed}/{len(checks)} PASS')
if failed:
    print('FAILURES:')
    for name, err in failed:
        print(f'  - {name}: {err}')
else:
    print('ALL PASS!')
