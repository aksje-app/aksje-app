# Release Notes — v19.22.0 RC16.32j

## Super Portfolio Intelligence Completion

RC16.32j closes the five remaining SP intelligence backlog items from RC16.32i.

### Completed
- Candidate persistence: new challengers must normally qualify in 2 consecutive fresh decision runs before replacing an incumbent.
- Regime-aware rebalance policy: CALM / NORMAL / STRESSED adjusts persistence runs, minimum Decision Confidence and challenger score margin.
- Per-stock data coverage gate: low-coverage new entrants remain visible to AI but cannot enter executable Shadow target. Existing holdings are not sold solely because coverage later becomes incomplete.
- Broad USA discovery: SP now combines S&P 500, S&P MidCap 400, S&P SmallCap 600 and Nasdaq-100 constituents, deduplicated, with a default SP USA capacity of 1,600 symbols.
- AI THINKS vs SHADOW EXECUTED: advisory intent and actual Shadow actions are stored and rendered separately.
- Broad USA coarse-price loading is chunked to 250 symbols per batch to limit peak resource use.

### Safety contracts preserved
- No real orders are submitted.
- Hard-stop exits remain immediate and bypass ordinary rebalance gates.
- Production Norway-only chain is unchanged.
- Deep analysis remains bounded; broadening applies to the cheap discovery stage.
- Executable ordinary rebalance still requires fresh market data and the existing confidence gate.
