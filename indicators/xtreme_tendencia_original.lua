instrument {
    name = "Xtreme Tendência",
    overlay = true,
    icon = "indicators:MA"
}

buy_color  = '#1cfc03'
sell_color = '#fc0303'
signal_size = shape_size.large
buy_shape = shape_style.arrowup
sell_shape = shape_style.arrowdown

period = input (18, "Período ATR", input.integer, 1)
multiplier = input (2, "Multiplicador", input.double, 1)
high_low = input (false, "Usar High/Low", input.boolean)

atr = rma(tr, period) * multiplier
h = iff(high_low, high, close)
l = iff(high_low, low, close)

atr_ts = iff(
    close > nz(atr_ts[1], 0) and close[1] > nz(atr_ts[1], 0),
    max(nz(atr_ts[1]), h - atr),
    iff(
        close < nz(atr_ts[1], 0) and close[1] < nz(atr_ts[1], 0),
        min(nz(atr_ts[1]), l + atr),
        iff(close > nz(atr_ts[1], 0), h - atr, l + atr)
    )
)

pos = iff(
    close[1] < nz(atr_ts[1], 0) and close > nz(atr_ts[1], 0), 1,
    iff(close[1] > nz(atr_ts[1], 0) and close < nz(atr_ts[1], 0), -1, nz(pos[1], 0))
)

plot(atr_ts, "Xtreme Tendência ATR", pos < 0 and sell_color or buy_color, 3)