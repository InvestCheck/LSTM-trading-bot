# Prop firm simulation: v2 + stop rule on CME micros (holding through closes and weekends) (no consistency rule)

679 trades on 15 instruments, 506 eval start dates (weekly, 2017-01-03 to 2026-09-08). Flat at the close and over weekends, re entry at 18:00 ET, commissions and a tick each way. Risk fractions are of the plan's drawdown. Funded sizing drops to the second fraction once profit exceeds one drawdown.


## tradeify150: start 150000, target 9000, drawdown 4500 (eod), consistency 100% eval / 100% payout

| eval risk | funded risk (initial / after buffer) | pass rate | median days to pass | fees per pass | P(any payout) | payouts per funded acct | funded life (days) | EV per attempt | EV per year |
|---|---|---|---|---|---|---|---|---|---|
| 5% | 33% / 10.0% | 0% | nan | n/a | 0% | $0 | 0 | $-340 | $-340 |
| 5% | 20% / 10.0% | 0% | nan | n/a | 0% | $0 | 0 | $-340 | $-340 |
| 5% | 20% / 20.0% | 0% | nan | n/a | 0% | $0 | 0 | $-340 | $-340 |
| 5% | 10% / 10.0% | 0% | nan | n/a | 0% | $0 | 0 | $-340 | $-340 |
| 10% | 33% / 10.0% | 3% | 278 | $10,752 | 0% | $0 | 63 | $-340 | $-341 |
| 10% | 20% / 10.0% | 3% | 278 | $10,752 | 0% | $0 | 186 | $-340 | $-337 |
| 10% | 20% / 20.0% | 3% | 278 | $10,752 | 0% | $0 | 186 | $-340 | $-337 |
| 10% | 10% / 10.0% | 3% | 278 | $10,752 | 100% | $1,857 | 544 | $-281 | $-270 |
| 20% | 33% / 10.0% | 28% | 170 | $1,203 | 29% | $985 | 50 | $-62 | $-70 |
| 20% | 20% / 10.0% | 28% | 170 | $1,203 | 41% | $707 | 76 | $-140 | $-155 |
| 20% | 20% / 20.0% | 28% | 170 | $1,203 | 39% | $536 | 70 | $-188 | $-210 |
| 20% | 10% / 10.0% | 28% | 170 | $1,203 | 60% | $1,256 | 218 | $15 | $15 |
| 33% | 33% / 10.0% | 25% | 66 | $1,344 | 31% | $1,336 | 67 | $-2 | $-2 |
| 33% | 20% / 10.0% | 25% | 66 | $1,344 | 35% | $1,718 | 105 | $95 | $107 |
| 33% | 20% / 20.0% | 25% | 66 | $1,344 | 35% | $1,584 | 105 | $61 | $69 |
| 33% | 10% / 10.0% | 25% | 66 | $1,344 | 86% | $1,960 | 262 | $156 | $157 |
| 50% | 33% / 10.0% | 22% | 30 | $1,522 | 39% | $3,895 | 114 | $530 | $606 |
| 50% | 20% / 10.0% | 22% | 30 | $1,522 | 43% | $2,879 | 130 | $303 | $343 |
| 50% | 20% / 20.0% | 22% | 30 | $1,522 | 42% | $2,869 | 131 | $301 | $340 |
| 50% | 10% / 10.0% | 22% | 30 | $1,522 | 79% | $2,681 | 252 | $259 | $270 |

EV per attempt = expected payouts (after split) minus expected fees, per eval started. EV per year assumes attempts run back to back. The strategy's edge here is close to zero after fills, so most of any positive EV is the firm absorbing the drawdown; check the consistency and payout rules against the firm's current terms.
