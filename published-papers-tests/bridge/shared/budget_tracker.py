"""Cumulative-spend tracker with hard abort at BUDGET_USD.

Used by `bridge/run.py` after every API call to (a) accumulate input +
output token totals, (b) compute current spend in USD, (c) project total
spend for the full row count, and (d) raise BudgetExceeded the moment
either current or projected spend crosses the cap.

The class is pure-Python and synchronous so the runner can sprinkle
`tracker.add(...)` + `tracker.check(rows_done, total_rows)` without
fighting asyncio context.
"""
from __future__ import annotations

from .config import BUDGET_USD, INPUT_PRICE_PER_M, OUTPUT_PRICE_PER_M


class BudgetExceeded(RuntimeError):
    """Raised when cumulative spend OR projected spend crosses BUDGET_USD."""


class BudgetTracker:
    def __init__(self, budget_usd: float = BUDGET_USD):
        self.budget_usd:    float = budget_usd
        self.input_tokens:  int   = 0
        self.output_tokens: int   = 0
        self.api_calls:     int   = 0
        self.aborted:       bool  = False

    # ── Recording ────────────────────────────────────────────────────────
    def add(self, input_tokens: int, output_tokens: int) -> None:
        """Accumulate token usage from one API call."""
        self.input_tokens  += max(0, int(input_tokens or 0))
        self.output_tokens += max(0, int(output_tokens or 0))
        self.api_calls     += 1

    # ── Reporting ────────────────────────────────────────────────────────
    def cost_usd(self) -> float:
        """Current cumulative cost based on per-million pricing."""
        return (
            self.input_tokens  * INPUT_PRICE_PER_M  / 1_000_000
            + self.output_tokens * OUTPUT_PRICE_PER_M / 1_000_000
        )

    def project_total(self, rows_done: int, total_rows: int) -> float:
        """Linear projection: current_spend × total_rows / rows_done.

        Returns inf if rows_done == 0 (no data yet — caller treats inf
        as "skip projection check until we have at least one data point").
        """
        if rows_done <= 0:
            return float("inf")
        per_row = self.cost_usd() / rows_done
        return per_row * total_rows

    def remaining(self) -> float:
        return self.budget_usd - self.cost_usd()

    # ── Abort gate ───────────────────────────────────────────────────────
    def check(self, rows_done: int, total_rows: int) -> None:
        """Raise BudgetExceeded if current or projected spend crosses cap.

        Called every 50 rows (or at end of each domain). Caller catches
        BudgetExceeded, writes partial results, exits with code 1.
        """
        cur = self.cost_usd()
        if cur >= self.budget_usd:
            self.aborted = True
            raise BudgetExceeded(
                f"Cumulative cost ${cur:.4f} >= ${self.budget_usd:.2f} cap"
            )
        # Skip projection until we have at least 50 rows of data — early
        # noise can spike the per-row average.
        if rows_done >= 50 and total_rows > rows_done:
            proj = self.project_total(rows_done, total_rows)
            if proj > self.budget_usd:
                self.aborted = True
                raise BudgetExceeded(
                    f"Projected total ${proj:.4f} > ${self.budget_usd:.2f} cap "
                    f"(at row {rows_done}/{total_rows}, current ${cur:.4f})"
                )

    # ── Pretty-print ─────────────────────────────────────────────────────
    def status_line(self, rows_done: int, total_rows: int) -> str:
        cur = self.cost_usd()
        proj = self.project_total(rows_done, total_rows) if rows_done else float("nan")
        proj_str = f"~${proj:.2f}" if proj == proj and proj != float("inf") else "?"
        return (
            f"[${cur:.2f} spent / ${self.budget_usd:.2f} cap | "
            f"{rows_done}/{total_rows} rows | proj total {proj_str}]"
        )
