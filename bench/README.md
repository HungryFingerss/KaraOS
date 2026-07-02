# bench/ — perception evaluation harness

Measured perception accuracy as CI-gated numbers (SB.7). One package today: `perception/`.

## What it measures
1. **Face-verification EER** — leave-one-out over a synthetic 64-identity gallery (`data/synthetic_embeddings.npz`), enrolled into a REAL temp-dir `FaceDB` and scored through the REAL `recognize()` path (not raw cosine math — the point is to measure the production path).
2. **Speaker-attribution accuracy** — drives the REAL reconciler over the 51 golden routing cases in `tests/reconciler_golden.py` (positive cases only — accuracy is never computed over negative invariants).

## Use it
```bash
python -m bench.perception                    # run both metrics, print the report
python -m bench.perception --alert            # exit non-zero on regression past the bands
python -m bench.perception --write-baseline   # regenerate baseline (human-reviewed commit only)
```

## The committed baseline (`baseline/baseline.json`)
EER **0.0625** (threshold 0.5109) · attribution **51/51**. Regression bands: EER +0.02 absolute, attribution −2.0pp (one case ≈ 1.96pp, so the band respects case granularity). `--alert` gates the nightly CI leg (`slow.yml` runs the bench in a companion + robotics profile matrix).

## Honest limits
- The EER gallery is **synthetic** (deterministic, seed-fixed — `gen_synthetic_embeddings.py`). It gates *regressions in the pipeline math*, not absolute real-world accuracy. A real-photo EER (LFW) is a deferred fast-follow: `--real-eer` currently exits 2 with a NOT-IMPLEMENTED marker rather than pretending.
- Baselines regenerate only through `--write-baseline` (the same code path that consumes them) and land as reviewed commits, never CI-auto.
