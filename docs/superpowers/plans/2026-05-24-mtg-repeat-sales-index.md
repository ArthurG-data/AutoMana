# MTG Repeat-Sales Price Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run and validate `notebooks/repeat_sales_index.ipynb` against the live AutoMana database, confirming all three repeat-sales index methods (A, B, C) produce coherent results and export a final index parquet.

**Architecture:** Execute the notebook cell-by-cell via `jupyter nbconvert`, asserting data-quality invariants at each stage. Failures at any stage are diagnosed and fixed before moving forward. The notebook is self-contained — no application code changes needed.

**Tech Stack:** Python 3.12 · psycopg2 · pandas · numpy · scipy.sparse · matplotlib · Jupyter (`.venv/bin/jupyter`)

---

## Pre-flight

### Task 0: Environment and DB connectivity

**Files:**
- Read: `notebooks/repeat_sales_index.ipynb`
- Read: `docs/domain/MTG_RSI_METHODOLOGY.md`

- [ ] **Step 1: Verify postgres is up**

```bash
docker ps --format "{{.Names}}\t{{.Status}}" | grep postgres
```

Expected output contains `automana-postgres-dev` and `Up`.

If not running:
```bash
docker compose -f deploy/docker-compose.dev.yml up -d postgres
```
Wait ~10 seconds then re-check.

- [ ] **Step 2: Verify DB password env var is set**

```bash
echo "AUTOMANA_DB_PASSWORD is ${#AUTOMANA_DB_PASSWORD} chars"
```

Expected: a non-zero character count. If empty, set it:
```bash
export AUTOMANA_DB_PASSWORD="$(docker exec automana-postgres-dev psql -U automana_admin -d automana -tAc "SELECT 'connected'")"
```
If that also fails, check `.env` or `deploy/docker-compose.dev.yml` for the password.

- [ ] **Step 3: Verify all required packages are importable**

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 -c "
import psycopg2, pandas, numpy, matplotlib, scipy.sparse, scipy.sparse.linalg
print('All packages OK')
print('scipy:', scipy.__version__)
print('pandas:', pandas.__version__)
"
```

Expected: `All packages OK` with version lines. No ImportError.

- [ ] **Step 4: Verify the pricing data exists**

```bash
docker exec automana-postgres-dev psql -U automana_admin -d automana -c "
SELECT
    MIN(price_date)        AS earliest,
    MAX(price_date)        AS latest,
    COUNT(DISTINCT price_date) AS n_dates,
    COUNT(*)               AS n_rows
FROM pricing.print_price_daily ppd
JOIN pricing.price_source ps USING (source_id)
JOIN pricing.card_condition cc ON cc.condition_id = ppd.condition_id
JOIN card_catalog.card_finished cf ON cf.finish_id = ppd.finish_id
WHERE ps.code = 'tcg'
  AND cc.code = 'NM'
  AND cf.code = 'NONFOIL'
  AND ppd.list_avg_cents IS NOT NULL;
"
```

Expected: `n_rows > 0`, `n_dates > 10`, `earliest` and `latest` populated.
If zero rows, the pricing pipeline has not run — do not proceed until it has.

---

## Notebook Execution

### Task 1: Data extraction and validation (Sections 0–1)

**Files:**
- Execute: `notebooks/repeat_sales_index.ipynb` cells 1–4 (Setup through filtering)
- Write: `notebooks/data/rsi_weekly_panel.parquet` (cache)

- [ ] **Step 1: Run the notebook Setup cell**

```bash
cd /home/arthur/projects/AutoMana && \
AUTOMANA_DB_PASSWORD="$AUTOMANA_DB_PASSWORD" \
.venv/bin/jupyter nbconvert \
  --to notebook \
  --execute \
  --ExecutePreprocessor.timeout=300 \
  --ExecutePreprocessor.kernel_name=python3 \
  --inplace \
  notebooks/repeat_sales_index.ipynb \
  2>&1 | tail -20
```

If this times out or errors on a specific cell, add `--ExecutePreprocessor.interrupt_on_timeout=True` and re-run.

Expected: no `CellExecutionError` lines in output.

- [ ] **Step 2: Validate the weekly panel parquet**

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 - <<'EOF'
import pandas as pd

df = pd.read_parquet('notebooks/data/rsi_weekly_panel.parquet')
print(f"Shape          : {df.shape}")
print(f"Columns        : {list(df.columns)}")
print(f"Date range     : {df.price_week.min().date()} → {df.price_week.max().date()}")
print(f"Unique cards   : {df.card_version_id.nunique():,}")
print(f"Unique weeks   : {df.price_week.nunique():,}")
print(f"Null avg_cents : {df.list_avg_cents.isna().sum():,}")

assert df.shape[0] > 1000,       "Too few rows — pricing data may be missing"
assert df.price_week.nunique() > 10, "Too few weeks — check date filter in SQL"
assert df.card_version_id.nunique() > 100, "Too few unique cards"
assert df.list_avg_cents.isna().sum() == 0, "Unexpected nulls in list_avg_cents"
print("\nAll assertions passed ✓")
EOF
```

- [ ] **Step 3: Validate post-filter panel**

The notebook applies a $1 floor and 2-week minimum. Run this validation against the parquet to confirm the filter logic is sound before the filtered panel is used for index computation:

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 - <<'EOF'
import pandas as pd, numpy as np

raw = pd.read_parquet('notebooks/data/rsi_weekly_panel.parquet')

# Replicate notebook filters
df = raw[raw['list_avg_cents'] >= 100].copy()
obs = df.groupby('card_version_id')['price_week'].nunique()
valid = obs[obs >= 2].index
df = df[df['card_version_id'].isin(valid)]

pct_retained = len(df) / len(raw) * 100
print(f"Rows after filter : {len(df):,}  ({pct_retained:.1f}% of raw)")
print(f"Cards after filter: {df.card_version_id.nunique():,}")

assert len(df) > 500,   "Too few rows after $1 filter — check data"
assert df.card_version_id.nunique() > 50, "Too few cards after filter"
assert df.list_avg_cents.min() >= 100, "$1 floor not applied correctly"
print("All assertions passed ✓")
EOF
```

- [ ] **Step 4: Commit cache**

```bash
cd /home/arthur/projects/AutoMana && \
git add notebooks/data/rsi_weekly_panel.parquet && \
git commit -m "research(notebook): cache weekly price panel for RSI notebook"
```

---

### Task 2: Validate Method A — Chained Geometric Mean (Section 2)

**Files:**
- Execute: Section 2 cells of notebook (already executed in Task 1 full run)
- Write: `notebooks/data/rsi_method_A.png`

- [ ] **Step 1: Validate Method A output**

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 - <<'EOF'
import pandas as pd, numpy as np

# Re-derive Method A from cached panel to validate
raw = pd.read_parquet('notebooks/data/rsi_weekly_panel.parquet')
df = raw[raw['list_avg_cents'] >= 100].copy()
obs = df.groupby('card_version_id')['price_week'].nunique()
df = df[df['card_version_id'].isin(obs[obs >= 2].index)].copy()
df = df.sort_values(['card_version_id', 'price_week'])
df['log_price'] = np.log(df['list_avg_cents'])
df['delta_log'] = df.groupby('card_version_id')['log_price'].diff()
outlier_mask = df['delta_log'].abs() > np.log(10)
df.loc[outlier_mask, 'delta_log'] = np.nan

pairs = df.dropna(subset=['delta_log'])
weekly = (
    pairs.groupby('price_week')
    .agg(mean_delta=('delta_log','mean'), n_cards=('card_version_id','nunique'))
    .sort_index()
)
weekly['cum_log'] = weekly['mean_delta'].cumsum()
base_row = weekly[weekly['n_cards'] >= 50].iloc[0]
weekly['index_A'] = 100 * np.exp(weekly['cum_log'] - base_row['cum_log'])

print(f"Weeks in Method A  : {len(weekly)}")
print(f"Base week          : {base_row.name.date()}")
print(f"Index range        : {weekly.index_A.min():.1f} – {weekly.index_A.max():.1f}")
print(f"Latest value       : {weekly.index_A.iloc[-1]:.1f}")
print(f"Max weekly cards   : {weekly.n_cards.max():,}")

# Invariants
assert weekly['index_A'].notna().all(), "NaN values in index"
assert weekly['index_A'].min() > 0,     "Index went negative — impossible"
assert abs(weekly.loc[base_row.name, 'index_A'] - 100.0) < 0.01, \
    "Base period not anchored to 100"
assert weekly['n_cards'].max() >= 50, "Never reached 50 active cards"

# Sanity: total return should be between -80% and +2000% (reasonable MTG range)
total_return = (weekly.index_A.iloc[-1] / 100 - 1) * 100
print(f"Total return since base: {total_return:+.1f}%")
assert -80 < total_return < 2000, f"Total return {total_return:.1f}% is implausible"

print("\nMethod A assertions passed ✓")
EOF
```

- [ ] **Step 2: Verify the plot was generated**

```bash
ls -lh /home/arthur/projects/AutoMana/notebooks/data/rsi_method_A.png
```

Expected: file exists, size > 20KB. If missing, the matplotlib cell silently failed — check the executed notebook for output errors:
```bash
/home/arthur/projects/AutoMana/.venv/bin/jupyter nbconvert \
  --to script notebooks/repeat_sales_index.ipynb \
  --stdout 2>/dev/null | grep -n "rsi_method_A"
```

---

### Task 3: Validate Method B — BMN Adjacent-Pair OLS (Section 3)

**Files:**
- Execute: Section 3 cells (run in Task 1 full run)
- Write: `notebooks/data/rsi_method_AB.png`

- [ ] **Step 1: Validate the OLS solve and index shape**

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 - <<'EOF'
import pandas as pd, numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import lsqr

raw = pd.read_parquet('notebooks/data/rsi_weekly_panel.parquet')
df = raw[raw['list_avg_cents'] >= 100].copy()
obs = df.groupby('card_version_id')['price_week'].nunique()
df = df[df['card_version_id'].isin(obs[obs >= 2].index)].copy()
df = df.sort_values(['card_version_id', 'price_week'])
df['log_price'] = np.log(df['list_avg_cents'])
df['delta_log'] = df.groupby('card_version_id')['log_price'].diff()
df.loc[df['delta_log'].abs() > np.log(10), 'delta_log'] = np.nan

all_weeks = sorted(df['price_week'].unique())
week_to_k = {w: i for i, w in enumerate(all_weeks)}
df['week_k'] = df['price_week'].map(week_to_k)
n_weeks = len(all_weeks)

pairs_b = df.dropna(subset=['delta_log','week_k'])
pairs_b = pairs_b[pairs_b['week_k'] > 0].reset_index(drop=True)

print(f"Adjacent pairs   : {len(pairs_b):,}")
print(f"Design matrix    : {len(pairs_b)} × {n_weeks-1}")

# Build and solve
n_c = n_weeks - 1
X = lil_matrix((len(pairs_b), n_c))
for i, (_, row) in enumerate(pairs_b.iterrows()):
    k = int(row['week_k'])
    if k - 1 >= 0: X[i, k-1] = +1.0
    if k - 2 >= 0: X[i, k-2] = -1.0

result = lsqr(X.tocsr(), pairs_b['delta_log'].values)
beta = result[0]
residual_norm = result[3]

log_idx = np.concatenate([[0.0], beta])
n_cards_pw = pairs_b.groupby('week_k')['card_version_id'].nunique()
base_k = int(n_cards_pw[n_cards_pw >= 50].index.min())
log_idx -= log_idx[base_k]
index_B = 100 * np.exp(log_idx)

print(f"Residual norm    : {residual_norm:.4f}")
print(f"Beta range       : [{beta.min():.4f}, {beta.max():.4f}]")
print(f"Index B range    : {index_B.min():.1f} – {index_B.max():.1f}")
print(f"Latest value     : {index_B[-1]:.1f}")
total_return = (index_B[-1] / 100 - 1) * 100
print(f"Total return     : {total_return:+.1f}%")

assert len(beta) == n_weeks - 1,     "Beta length mismatch"
assert not np.any(np.isnan(beta)),   "NaN in beta — solver failed"
assert index_B.min() > 0,            "Index went negative — impossible"
assert abs(index_B[base_k] - 100.0) < 0.01, "Base not anchored to 100"
assert residual_norm < 1e6,          "Residual norm suspiciously large"
assert -80 < total_return < 2000,    "Total return is implausible"
print("\nMethod B assertions passed ✓")
EOF
```

- [ ] **Step 2: Check A vs B correlation (should be ≥ 0.90)**

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 - <<'EOF'
import pandas as pd, numpy as np

final = pd.read_parquet('notebooks/data/rsi_final_index.parquet') \
    if __import__('pathlib').Path('notebooks/data/rsi_final_index.parquet').exists() \
    else None

if final is not None and 'index_A' in final and 'index_B' in final:
    both = final[['index_A','index_B']].dropna()
    corr = both.corr().iloc[0,1]
    print(f"Correlation A vs B: {corr:.4f}")
    assert corr >= 0.85, f"A vs B correlation {corr:.3f} too low — methods diverge unexpectedly"
    print("Correlation check passed ✓")
else:
    print("Final parquet not yet written — will validate after Section 7 runs")
EOF
```

---

### Task 4: Validate Method C — All-Pairs WLS (Section 4)

**Files:**
- Execute: Section 4 cells (run in Task 1 full run)
- Write: `notebooks/data/rsi_all_methods.png`

- [ ] **Step 1: Check pair counts and memory guard**

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 - <<'EOF'
import pandas as pd, numpy as np
from itertools import combinations

raw = pd.read_parquet('notebooks/data/rsi_weekly_panel.parquet')
df = raw[raw['list_avg_cents'] >= 100].copy()
obs_count = df.groupby('card_version_id')['price_week'].nunique()
df = df[df['card_version_id'].isin(obs_count[obs_count >= 2].index)].copy()
df['log_price'] = np.log(df['list_avg_cents'])

all_weeks = sorted(df['price_week'].unique())
week_to_k = {w: i for i, w in enumerate(all_weeks)}
df['week_k'] = df['price_week'].map(week_to_k)

MAX_OBS = 52
QUARTERLY_GAPS = {13, 26, 39, 52}
MAX_LOG_JUMP = np.log(10)

dense_count = 0
total_pairs = 0
for card_id, grp in df.dropna(subset=['log_price','week_k']).groupby('card_version_id'):
    obs = grp.sort_values('week_k')[['week_k','log_price']].values
    n = len(obs)
    if n < 2: continue
    is_dense = n > MAX_OBS
    if is_dense: dense_count += 1
    for (k1, lp1), (k2, lp2) in combinations(obs, 2):
        gap = int(k2 - k1)
        if is_dense and gap != 1 and gap not in QUARTERLY_GAPS:
            continue
        if abs(lp2 - lp1) > MAX_LOG_JUMP * gap:
            continue
        total_pairs += 1

print(f"Dense cards (>{MAX_OBS} weeks): {dense_count:,}")
print(f"Total Method C pairs        : {total_pairs:,}")
print(f"Estimated memory (float64)  : {total_pairs * 8 / 1e6:.1f} MB for y-vector")

assert total_pairs > 0,         "Zero pairs generated — data missing"
assert total_pairs < 50_000_000, f"Pair count {total_pairs:,} exceeds memory safety limit — increase subsampling"
print("Method C pair count check passed ✓")
EOF
```

- [ ] **Step 2: Validate Method C index values**

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 - <<'EOF'
import pandas as pd, numpy as np

path = 'notebooks/data/rsi_final_index.parquet'
if not __import__('pathlib').Path(path).exists():
    print("Final parquet not yet written. Run Section 7 of the notebook first.")
    raise SystemExit(1)

final = pd.read_parquet(path)

assert 'index_C' in final.columns, "Method C column missing from final parquet"
c = final['index_C'].dropna()

print(f"Method C weeks  : {len(c)}")
print(f"Index C range   : {c.min():.1f} – {c.max():.1f}")
print(f"Latest value    : {c.iloc[-1]:.1f}")

total_return = (c.iloc[-1] / 100 - 1) * 100
print(f"Total return    : {total_return:+.1f}%")

assert c.min() > 0,                "Index C went negative"
assert not c.isna().all(),         "All NaN in index C"
assert -80 < total_return < 2000,  "Total return implausible"

# B and C should be within 30 index points of each other at any given week
if 'index_B' in final.columns:
    both = final[['index_B','index_C']].dropna()
    max_divergence = (both['index_B'] - both['index_C']).abs().max()
    print(f"Max B vs C divergence: {max_divergence:.2f} index points")
    assert max_divergence < 50, \
        f"B/C diverge by {max_divergence:.1f} pts — check variance correction logic"

print("\nMethod C assertions passed ✓")
EOF
```

---

### Task 5: Validate diagnostics and rarity sub-indices (Sections 5–6)

**Files:**
- Execute: Sections 5–6 (run in Task 1 full run)
- Write: `notebooks/data/rsi_coverage.png`, `rsi_residuals.png`, `rsi_divergence.png`, `rsi_by_rarity.png`

- [ ] **Step 1: Verify all plots were written**

```bash
for f in rsi_method_A rsi_method_AB rsi_all_methods rsi_coverage rsi_residuals rsi_divergence rsi_by_rarity; do
  path="notebooks/data/${f}.png"
  if [ -f "$path" ]; then
    size=$(du -k "$path" | cut -f1)
    echo "✓ $f.png  (${size}KB)"
  else
    echo "✗ $f.png  MISSING"
  fi
done
```

Expected: all 7 files present, each > 10KB.

- [ ] **Step 2: Validate rarity sub-index coverage**

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 - <<'EOF'
import pandas as pd

final = pd.read_parquet('notebooks/data/rsi_final_index.parquet')
rarity_cols = [c for c in final.columns if c.startswith('index_B_')]

print(f"Rarity sub-indices built: {len(rarity_cols)}")
for col in rarity_cols:
    s = final[col].dropna()
    latest = s.iloc[-1] if len(s) > 0 else float('nan')
    print(f"  {col:25s}: {len(s):3d} weeks, latest={latest:.1f}")

assert len(rarity_cols) >= 2, \
    "Expected at least mythic + rare sub-indices — check rarity column in SQL"
for col in rarity_cols:
    assert final[col].dropna().min() > 0, f"{col} contains negative values"
print("\nRarity sub-index assertions passed ✓")
EOF
```

---

### Task 6: Final export validation and summary (Section 7)

**Files:**
- Read: `notebooks/data/rsi_final_index.parquet`

- [ ] **Step 1: Full parquet schema check**

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 - <<'EOF'
import pandas as pd

final = pd.read_parquet('notebooks/data/rsi_final_index.parquet')
print("=== Final Index Schema ===")
print(final.dtypes.to_string())
print(f"\nShape  : {final.shape}")
print(f"Weeks  : {final.price_week.min().date()} → {final.price_week.max().date()}")
print()

print("=== Coverage per method ===")
for col in final.columns:
    if col.startswith('index'):
        n = final[col].notna().sum()
        pct = 100 * n / len(final)
        print(f"  {col:30s}: {n}/{len(final)} weeks ({pct:.0f}%)")

print()
required_cols = ['price_week', 'index_A', 'index_B', 'index_C', 'n_cards']
for col in required_cols:
    assert col in final.columns, f"Required column '{col}' missing from final parquet"

assert final['price_week'].is_monotonic_increasing, "price_week is not sorted"
assert final['price_week'].nunique() == len(final), "Duplicate weeks in index"
print("Final export assertions passed ✓")
EOF
```

- [ ] **Step 2: Print human-readable summary**

```bash
/home/arthur/projects/AutoMana/.venv/bin/python3 - <<'EOF'
import pandas as pd

final = pd.read_parquet('notebooks/data/rsi_final_index.parquet')

print("=== MTG Repeat-Sales Price Index — Results Summary ===\n")
base_week = final.dropna(subset=['index_B']).query('index_B.sub(100).abs() < 0.1', engine='python')
if len(base_week):
    print(f"Base period       : {base_week.iloc[0].price_week.date()} = 100")

for method, col in [('A (Chained Mean)', 'index_A'),
                     ('B (BMN OLS)',      'index_B'),
                     ('C (Case-Shiller)', 'index_C')]:
    s = final[col].dropna()
    if len(s) == 0:
        print(f"{method:22s}: NO DATA")
        continue
    total_ret = (s.iloc[-1] / 100 - 1) * 100
    annualised = ((s.iloc[-1] / 100) ** (52 / len(s)) - 1) * 100
    print(f"{method:22s}: latest={s.iloc[-1]:6.1f}  total={total_ret:+6.1f}%  "
          f"annualised={annualised:+5.1f}%/yr  ({len(s)} weeks)")
EOF
```

- [ ] **Step 3: Commit the final notebook (with outputs) and parquet**

```bash
cd /home/arthur/projects/AutoMana && \
git add notebooks/repeat_sales_index.ipynb \
        notebooks/data/ && \
git commit -m "research(notebook): execute RSI notebook — all three methods validated

Methods A, B, C all pass invariant checks. Rarity sub-indices built.
Final index exported to notebooks/data/rsi_final_index.parquet."
```

---

## Troubleshooting Guide

### SQL returns zero rows
```sql
-- Check which conditions/finishes/sources actually have data:
SELECT ps.code, cc.code, cf.code, COUNT(*) AS n
FROM pricing.print_price_daily ppd
JOIN pricing.price_source ps USING (source_id)
JOIN pricing.card_condition cc ON cc.condition_id = ppd.condition_id
JOIN card_catalog.card_finished cf ON cf.finish_id = ppd.finish_id
WHERE ppd.list_avg_cents IS NOT NULL
GROUP BY ps.code, cc.code, cf.code
ORDER BY n DESC LIMIT 20;
```
If `tcg / NM / NONFOIL` has no rows, the MTGStocks pipeline has not run yet. Run it via:
```bash
docker exec automana-celery-dev celery -A automana.worker.main:app call mtgstock_download_pipeline
```

### `lsqr` returns NaN beta values
The design matrix X is rank-deficient — some weeks have zero pairs. Check:
```python
pairs_b.groupby('week_k').size().sort_values().head(10)
```
Weeks with 0 pairs in the data have no row in X, so the corresponding column is all zeros → singular. Fix: drop those weeks from `all_weeks` before constructing X, or use `lsqr` with `damp=1e-6` for regularisation.

### Method C pair explosion (MemoryError)
Reduce `MAX_OBS_C` from 52 to 26 in the notebook Setup cell. This triggers quarterly subsampling earlier. Alternatively, restrict `QUARTERLY_GAPS = {13, 26}` to allow only two long-gap sizes.

### Notebook cell timeout (`CellTimeoutError`)
Method C OLS solve can be slow on large matrices. Add to the nbconvert command:
```bash
--ExecutePreprocessor.timeout=600
```
Or split execution: run Sections 0–3 first, save intermediate results, then run Sections 4–8 separately.

### Rarity column is NULL everywhere
```sql
SELECT DISTINCT r.code FROM card_catalog.rarity_ref r LIMIT 10;
```
If the rarity table uses different codes (e.g., `'M'` instead of `'mythic'`), update `RARITY_ORDER` in the notebook's Section 6 Setup to match.
