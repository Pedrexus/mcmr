import polars as pl


def counted_text(amount: pl.Expr, singular: str) -> pl.Expr:
    """Render one relational count with its correctly inflected noun."""
    return pl.concat_str(
        amount,
        pl.when(amount == 1).then(pl.lit(f" {singular}")).otherwise(pl.lit(f" {singular}s")),
    )
