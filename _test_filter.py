import sys
sys.path.insert(0, '.')
from dumbmoney.basket_screener import get_string_screener

try:
    r = get_string_screener('US', page=1, per_page=3, args={'atr_status': 'crossed-above'})
    print('total:', r['total'], 'data:', len(r['data']))
    for d in r['data'][:3]:
        print(f"  {d['symbol']} atr_crossed_above={d['atr_crossed_above']} atr_signal={d['atr_signal']}")
except Exception as e:
    import traceback; traceback.print_exc()

try:
    r = get_string_screener('US', page=1, per_page=3, args={'accel_status': 'crossed-up'})
    print('accel total:', r['total'], 'data:', len(r['data']))
    for d in r['data'][:3]:
        print(f"  {d['symbol']} accel_crossed_up={d['accel_crossed_up']}")
except Exception as e:
    import traceback; traceback.print_exc()
