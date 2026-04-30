
def calc_levels(entry_price, stop_loss_pct, take_profit_pct):
    stop_loss = entry_price * (1 - stop_loss_pct / 100)
    take_profit = entry_price * (1 + take_profit_pct / 100)
    return round(stop_loss, 2), round(take_profit, 2)
