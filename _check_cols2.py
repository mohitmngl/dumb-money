import urllib.request, json

data = json.loads(urllib.request.urlopen("http://localhost:8474/api/screener?market=US&per_page=3&sort=weighted_alpha&sort_dir=desc").read())

first = data["data"][0]

# Simulate the JS renderTable logic
COLUMNS = [
  {'key':'_check'}, {'key':'symbol'}, {'key':'name'}, {'key':'exchange'},
  {'key':'asset_class'}, {'key':'price'}, {'key':'change_pct'}, {'key':'next_day_return'},
  {'key':'prob_up_1d'}, {'key':'prob_up_5d'}, {'key':'weighted_alpha'}, {'key':'volume'},
  {'key':'streak'}, {'key':'confluence'}, {'key':'ai_overall_score'}, {'key':'ai_volume_profile_score'},
  {'key':'ai_trendline_score'}, {'key':'ai_sentiment_score'}, {'key':'ai_conclusion'},
  {'key':'atr_signal'}, {'key':'atr_crossed_above'}, {'key':'atr_crossed_below'},
  {'key':'atr_stop'}, {'key':'atrp'}, {'key':'accel_signal'}, {'key':'accel_crossed_up'},
  {'key':'accel_crossed_down'}, {'key':'marginable'}, {'key':'fractionable'},
  {'key':'profit_status'}, {'key':'pre_change_pct'}, {'key':'post_change_pct'},
  {'key':'last_updated'},
]

print(f"COLUMNS count: {len(COLUMNS)}")
print(f"API keys count: {len(first.keys())}")
print()

# Check th count vs td count
th_count = len(COLUMNS)  # forEach generates one th per column
td_count = 1 + (len(COLUMNS) - 1)  # 1 checkbox + forEach skips _check
print(f"Th count (forEach): {th_count}")
print(f"Td count (1 checkbox + forEach non-check): {td_count}")
print(f"Match: {th_count == td_count}")
print()

# Now check: for each non-_check COLUMNS entry, does row[key] exist?
print("Checking column key -> API value mapping:")
for col in COLUMNS:
    k = col['key']
    if k == '_check':
        print(f"  {k:>25s} → (checkbox)")
        continue
    v = first.get(k, '*** MISSING ***')
    print(f"  {k:>25s} → {v}")
