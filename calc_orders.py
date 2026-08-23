import math

prices = {
    'TGT': 140.68, 'CCCC': 3.54, 'STAA': 24.955, 'AAPL': 326.41, 'ROST': 235.35,
    'BAH': 64.12, 'LSPD': 10.27, 'RYN': 21.49, 'COUR': 5.39, 'GPK': 10.71
}

long_syms = ['TGT', 'CCCC', 'STAA', 'AAPL', 'ROST']
short_syms = ['BAH', 'LSPD', 'RYN', 'COUR', 'GPK']
TARGET = 100.0

print("=" * 70)
print("LONG POSITIONS (buy $100 each via notional)")
print("=" * 70)
for sym in long_syms:
    p = prices[sym]
    qty = TARGET / p
    print(f"  BUY  {sym}: ${TARGET:.0f} / ${p:.2f} = {qty:.4f} shares")

print()
print("=" * 70)
print("SHORT POSITIONS (sell int, buy back fractional)")
print("=" * 70)
total_short_value = 0
for sym in short_syms:
    p = prices[sym]
    net_short = TARGET / p
    sell_int = math.ceil(net_short)
    buyback = sell_int - net_short
    short_val = sell_int * p
    buyback_val = buyback * p
    total_short_value += short_val
    print(f"  SELL {sym}: short {sell_int} shares @ ${p:.2f} = ${short_val:.2f}")
    print(f"  BUY  {sym}: buyback {buyback:.4f} shares @ ${p:.2f} = ${buyback_val:.2f}")
    print(f"  => net short: {net_short:.4f} shares = ${TARGET:.2f}")
    print()

print("=" * 70)
print("ORDER SUMMARY")
print("=" * 70)
print("5 LONG orders: notional market buy $100 each")
print("5 SHORT pairs: sell int market + buyback fractional market")
print("Total: 15 orders")
print(f"Total capital needed for shorts: ${total_short_value:.2f} (temporarily tied up)")
