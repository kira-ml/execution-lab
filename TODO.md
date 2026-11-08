# TODO — Execution & Market-Impact Lab

**Version:** 0.1.0  
**Status:** Built, tested, and documented. **Not finished by the charter’s acceptance criteria.**  
**Current binding constraint:** empirical credibility + release/reviewer, not more code.  
**Audit date:** 2026-11-08

> **Handoff rule:** do not add new features, new data sources, or a UI. Finish the evidence and release, then freeze. Risk Cockpit does not start until this project is frozen.

---

## 0. Current state (verified)

- [x] Public repo: https://github.com/kira-ml/execution-lab
- [x] 76 tests pass locally.
- [x] CI green on Python 3.10, 3.11, 3.12.
- [x] Synthetic demo runs: 6 tickers, 1,825 daily rows, seed `20261108`.
- [x] Real-data aggregate check: 12 ETFs, 4,966 daily rows, 2013-01-31 to 2026-09-29.
- [x] Spread-proxy sensitivity: 0.5x, 0.75x, 1x, 1.5x, 2x; see `docs/SPREAD_SENSITIVITY.md`.
- [x] No raw vendor data in the repo; manifests and data-license notes exist.
- [x] Limitations, method, reviewer brief, and decision log exist.
- [ ] `v0.1.0` tag/release. **Local prep complete; awaiting owner approval. GitHub CLI is not installed.**
- [ ] External reviewer recorded. **Request prepared; not sent.**
- [ ] Actual Robustfolio/Epistemic DRO weights loaded. **Downgraded to “integration layer only” for v0.1.0.**

**Known issue (confirmed and resolved):** the real-data headline originally overclaimed on the spread. VNQ is liquid; the **20.21 bps half-spread is a Corwin-Schultz proxy**, not a quote. The base rank flip is only **0.025 Sharpe** post-cost, and it **does not survive** a plausible lower spread: at 0.5x the proxy, momentum's net Sharpe is 0.429 versus equal weight 0.411, so momentum is back ahead. At 0.75x the two are effectively tied (0.410 vs 0.407). The robust finding is momentum's implementation fragility, not a reliable rank change. The README and real-data report are demoted accordingly.

---

## 1. P0 — Make the empirical claim robust

### 1.1 Spread sensitivity

- [x] Add a spread multiplier sensitivity: **0.5×, 0.75×, 1×, 1.5×, 2×** the Corwin-Schultz proxy.
- [ ] If a quoted-spread series is legally available, add it as a second proxy. **Not available; the proxy is the only spread source.**
- [x] Re-run the 12-ETF real-data check for each multiplier.
- [x] Produce a table: spread multiplier × strategy × net Sharpe and rank.
- [x] Report whether equal weight still overtakes momentum. **No at 0.5×; tie at 0.75×; yes at 1×–2×.**
- [x] Add a figure: `docs/real-data/fig_spread_sensitivity.png`.
- [x] Update `docs/REAL_DATA_CHECK.md` with the robustness result.
- [x] Update the README headline: the flip is **not robust**; demoted to a conditional secondary result.
- [x] Do not make a wide-spread claim about VNQ without quoted-spread evidence.

**Acceptance:** a reader can see whether the rank flip is robust to the largest uncertainty in the model. **Result:** it is not; the flip disappears at 0.5× and is a tie at 0.75×.

### 1.2 Actual portfolio weights

- [ ] Export one real weight history from Robustfolio or Epistemic DRO to the documented CSV schema.
- [ ] Run the cost model on those weights, not only reconstructed strategies.
- [ ] Report the cost drag and rank effect on the actual book.
- [x] If the export is not feasible, explicitly change the integration acceptance criterion to **“integration layer only”** and remove the implied full-integration claim from README/summary. **README and CHARTER now state that actual Robustfolio/Epistemic DRO weights are not loaded.**
- [ ] Document the exact source, period, and export command.

**Acceptance:** the project either tests the actual portfolios or clearly says it does not. **Current status: it clearly says it does not; actual-weight integration remains open.**

### 1.3 Data provenance clarification

- [x] Add one sentence to `README.md` and `docs/REAL_DATA_CHECK.md`:

> “This uses the separate Robustfolio ETF snapshot; it does not evaluate or consume the Epistemic DRO 2025–2026 holdout.”

- [x] Ensure the real-data check does not imply a holdout result.
- [x] Confirm no Epistemic DRO holdout files or results were used. **`git grep` finds only prose references; no holdout data or results are present.**

**Acceptance:** a reader cannot confuse the Execution Lab data with the Epistemic DRO holdout.

---

## 2. P0 — Release and external review

### 2.1 Release `v0.1.0`

- [x] Confirm working tree clean and tests green.
- [x] Confirm no raw data or secrets in the release.
- [x] Confirm release notes include the synthetic headline, aggregate real-data
      check, spread-sensitivity result and noise caveat, provenance sentence, and
      known gaps.
- [ ] Create tag `v0.1.0`. **Awaiting owner approval.**
- [ ] Create GitHub release with:
  - synthetic demo report and figures;
  - aggregate real-data tables and figures;
  - method/limitations/reviewer brief;
  - no raw vendor data.
- [ ] Add repo topics: `execution`, `market-impact`, `transaction-costs`, `portfolio-construction`, `quantitative-finance`, `reproducibility`.
- [ ] Verify release links and asset downloads.

**Owner approval required for the public tag/release.** Local preparation is
complete. `gh` is not installed, so the release commands cannot be run as written
until the GitHub CLI is available or the release is done through the browser/API
with approval.

### 2.2 External review

- [x] Finalize `docs/REVIEW.md` and the ready-to-send request.
- [x] Add or update the tracking table with date, request status, reviewer,
      response, and strongest objection.
- [ ] Send one request to an execution/microstructure/quant reviewer using `docs/REVIEW.md`. **Awaiting owner approval; not sent.**
- [ ] Ask the specific questions:
  - Is the Corwin-Schultz proxy appropriate for ETFs, or does it overstate spread?
  - Is arrival-price timing risk the right benchmark?
  - Is the square-root `k` range reasonable?
  - Does the rank flip survive a spread correction?
- [ ] Record reviewer, scope, strongest objection, and action.
- [ ] If no response after two follow-ups, record the attempt and freeze with “external review requested; none recorded.”

**Acceptance:** one external objection recorded, or a documented attempt.
**Current status:** request prepared and tracked; no contact made.

---

## 3. P1 — Engineering hygiene

- [x] Add `ruff` to `[project.optional-dependencies].dev` and run it.
- [x] Add a lint step to CI (`python -m ruff check .`).
- [x] Do **not** add `mypy`; it would create noise without changing a decision.
- [x] Keep CI on Python 3.10–3.12.
- [x] Re-run the demo on CI and confirm the artifact upload.
- [x] `ruff check .` passes locally with the conservative rule set (E4/E7/E9/F/I).

---

## 4. P2 — Optional, only if it changes a decision

- [ ] Add a direct comparison of observed quoted spreads vs the Corwin-Schultz proxy.
- [ ] Add an intraday calibration only if legally usable data exists.
- [ ] Add a small `spread_sensitivity` CLI flag if it makes the check reproducible.
- [ ] Do not add a UI, broker connection, order router, RL, deep learning, or LLM.

---

## 5. Stop rules

- [ ] No new features until P0 is done.
- [ ] No new project until this repo is frozen.
- [ ] No raw vendor data in the repo/release.
- [ ] No order-book realism claim without order-book data.
- [ ] No live-trading or alpha claim.
- [ ] If spread sensitivity kills the headline, report that; do not tune the proxy to preserve it.
- [ ] If a task exceeds its estimate by 50%, stop and reassess.
- [ ] After release/reviewer, freeze v0.1.0 and start Risk Cockpit only then.

---

## 6. Definition of done

- [x] Spread sensitivity added; rank-flip robustness stated honestly. **The flip is not robust.**
- [x] Actual weights integrated **or** integration claim explicitly downgraded. **Downgraded to “integration layer only.”**
- [x] Provenance sentence added; holdout not implicated.
- [ ] `v0.1.0` release exists and assets download. **Awaiting owner approval.**
- [ ] External reviewer recorded or documented attempt. **Request prepared; not sent.**
- [x] Tests, CI, and demo green.
- [x] README headline matches the evidence.
- [x] Lint passes and runs in CI.
- [ ] Repo frozen; no endless polishing. **Ready to freeze after release/reviewer decisions.**

---

## 7. Open questions

- Which public intraday data, if any, is legally usable for calibration?
- Is a daily-data impact model defensible as a ranking/sensitivity tool? Current answer: yes, if clearly bounded.
- Which portfolio should be the first real-weight integration: Robustfolio or Epistemic DRO?
- What is the minimum external review that makes the cost model credible?
- Does the real-data rank flip survive a plausible spread correction? **No. It disappears at 0.5× and is a tie at 0.75×; the robust finding is momentum's fragility.**

---

## 8. Evidence standard

- **Verified:** command/test/repo evidence exists.
- **Assumed:** modelling choice or proxy.
- **Proposed:** next step not yet executed.

Do not blur these categories in the README, release notes, or reviewer response.
