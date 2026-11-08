# Project Charter — Execution & Market-Impact Lab

**Status:** **ACTIVE — owner override on 2026-11-08.**  
**Owner:** Ken Ira Lacson Talingting  
**Version:** 0.1.0  
**Estimated effort when activated:** 8–10 weeks at 8–10 hours/week (80–100 hours).  
**Project type:** Applied system.

> **Activation note.** The project was originally parked behind the gate in
> `../FUTURE_FLAGSHIPS_PLAN_2026-11-08.md`. The owner explicitly requested the
> build on 2026-11-08. The gate was not fully met: Robustfolio has `v1.1`, not
> `v1.1.1`, and the external checks are pending. The override is recorded here
> and in [`PROJECT_STATE.md`](PROJECT_STATE.md); it is not retroactively described
> as a satisfied gate.

---

## 1. Problem

A backtest that subtracts 10 bps assumes away the hardest part of implementation. Real cost depends on:

- order size relative to volume;
- volatility;
- liquidity and spread;
- urgency;
- execution schedule.

The project asks whether a portfolio edge survives those costs, and how the ranking of strategies changes under realistic assumptions.

## 2. Decision

For a target portfolio and rebalance:

- Choose an execution schedule that balances expected cost and timing risk.
- Quantify how sensitive the strategy ranking is to impact assumptions.
- Identify which strategies are implementation-fragile.

## 3. Users

- A portfolio researcher checking whether a backtest is implementable.
- A quant/risk analyst comparing rebalance policies.
- The owner, as a reusable execution-cost layer for future projects.

## 4. Scope

### In scope

- One asset class: ETFs.
- Daily OHLCV and dollar volume; optional intraday bars only from a legitimate source.
- Cost decomposition, conservative impact model, execution schedules, sensitivity.
- Integration with one existing portfolio (Robustfolio or Epistemic DRO weights).
- Tests, CI, one-command demo, short paper/brief.

### Out of scope

- Live execution, order routing, brokerage APIs.
- Order-book simulation without order-book data.
- Intraday alpha research.
- Reinforcement learning or deep learning.
- A trading platform.

## 5. Data constraints

- Public/demo data only; no raw vendor redistribution.
- No order-book data unless a legitimate source is obtained.
- Document every proxy and assumption.
- No claim that a daily-data impact model is a live execution simulator.

## 6. Method

1. **Cost decomposition:** spread + commission + market impact + timing risk.
2. **Impact model:** \( \text{impact} \approx k \cdot \sigma \cdot \sqrt{Q/V} \), with sensitivity to \(k\).
3. **Execution schedules:** immediate, TWAP, VWAP, POV.
4. **Integration:** apply to existing weights; compare net performance/ranking.
5. **Optional ML:** not implemented. There is not enough out-of-sample execution data to justify a learned slippage model, and a regularized baseline would not change the main conclusion.

## 7. Deliverables

- [x] Python package/CLI.
- [x] Calibration notebook / module and sensitivity report.
- [x] Short paper/brief.
- [x] Tests, CI, one-command demo.
- [ ] One external reviewer — pending.

## 8. Acceptance criteria

- [x] Cost model documented; assumptions and limitations explicit.
- [x] At least four execution schedules compared.
- [x] Integration with a target-weight portfolio — a generic loader plus a synthetic demo book. **Limitation:** actual Robustfolio or Epistemic DRO weights have not yet been loaded; the CSV schema is ready for them.
- [x] Ranking sensitivity shown — across cost models, `k`, and AUM.
- [x] Tests and CI.
- [ ] External reviewer recorded — pending.
- [x] No live-trading claim.
- [ ] Release and one-page brief — the brief exists; the tagged release is pending.

## 9. Kill criteria

- No reliable volume/spread data → narrow to a conservative stylized model and document it. **Triggered:** the public demo uses a synthetic panel and a stylized spread proxy.
- Impact parameter not identifiable → report a sensitivity range, not a point estimate. **Implemented:** `k` grid, implied-k, and break-even k.
- Scope exceeds 10 weeks → cut intraday, schedules, or asset classes. **Not triggered:** the build is deliberately small.
- Temptation to build a trading platform → stop. **Not triggered:** no routing, broker, or live path.
- No external reviewer after two asks → document and freeze; do not polish indefinitely. **Pending:** record the attempts in `PROJECT_STATE.md`.

## 10. Main risks

| Risk | Mitigation |
|---|---|
| Daily data is not an execution simulator | State assumptions; sensitivity; no live claim |
| Impact model overfits one sample | Conservative range; out-of-sample calibration hook |
| Scope creep into trading infrastructure | Hard non-goals; 10-week cap |
| Data licensing | Synthetic demo; no vendor redistribution |
| Metric gaming | Report cost, variance, turnover, and ranking sensitivity together |
| False precision from a point `k` | Always report a range and a break-even |
