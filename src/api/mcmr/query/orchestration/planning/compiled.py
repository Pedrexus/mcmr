import polars as pl
from patos import FrozenModel, Runtime


class CompiledRule(FrozenModel):
    """Carry every lazy output branch of one rule without collecting any branch."""

    result: Runtime[pl.LazyFrame]
    failures: Runtime[pl.LazyFrame]
    findings: Runtime[pl.LazyFrame]
    fix_rewrites: Runtime[pl.LazyFrame]
    fix_nodes: Runtime[pl.LazyFrame]
    fix_imports: Runtime[pl.LazyFrame]
