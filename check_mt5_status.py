import MetaTrader5 as mt5

if not mt5.initialize():
    print("MT5 init failed")
    exit(1)

positions = mt5.positions_get()
print(f"Total open positions: {len(positions) if positions else 0}")
if positions:
    for p in positions:
        print(f"Ticket: {p.ticket} | Symbol: {p.symbol} | Type: {p.type} | Vol: {p.volume} | Open: {p.price_open} | Cur: {p.price_current} | SL: {p.sl} | TP: {p.tp} | PnL: ${p.profit:.2f} | Comment: {p.comment}")

account = mt5.account_info()
if account:
    print(f"Balance: ${account.balance:.2f} | Equity: ${account.equity:.2f} | Profit: ${account.profit:.2f}")

mt5.shutdown()
