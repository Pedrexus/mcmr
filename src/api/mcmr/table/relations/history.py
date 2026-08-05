import polars as pl

from ...facts import Fact
from .generic import FactRelations


class HistoryRelations[Family: Fact](FactRelations[Family]):
    """Derive repository history measures from normalized commit relations."""

    def change_paths(self) -> pl.LazyFrame:
        """Return each requested path within its commit."""
        return self.values("changes.paths").select(
            "fact_order",
            "fact_id",
            pl.col("parent_id").alias("change_id"),
            "ordinal",
            pl.col("string_value").alias("changed_path"),
        )

    def changes(self) -> pl.LazyFrame:
        """Return commits with their complete changed-file width."""
        return self.records("changes").select(
            "fact_order",
            "fact_id",
            "record_id",
            "ordinal",
            "other_file_count",
            (pl.col("paths.length") + pl.col("other_file_count")).alias("changed_file_count"),
        )

    def coupling(self, maximum_commit_files: int) -> pl.LazyFrame:
        """Return exact co-change support and lexical references for focused commits."""
        focused = self.changes().filter(pl.col("changed_file_count") <= maximum_commit_files)
        paths = self.change_paths().join(
            focused.select("fact_id", pl.col("record_id").alias("change_id")),
            on=["fact_id", "change_id"],
            how="inner",
        )
        commits = paths.group_by("fact_id", "changed_path", maintain_order=True).agg(
            pl.len().cast(pl.UInt64).alias("commit_count")
        )
        left = paths.select(
            "fact_id",
            "change_id",
            pl.col("changed_path").alias("left"),
        )
        right = paths.select(
            "fact_id",
            "change_id",
            pl.col("changed_path").alias("right"),
        )
        pairs = (
            left.join(right, on=["fact_id", "change_id"], how="inner")
            .filter(pl.col("left") < pl.col("right"))
            .group_by("fact_id", "left", "right", maintain_order=True)
            .agg(pl.len().cast(pl.UInt64).alias("shared_commit_count"))
            .join(
                commits.select(
                    "fact_id",
                    pl.col("changed_path").alias("left"),
                    pl.col("commit_count").alias("left_commit_count"),
                ),
                on=["fact_id", "left"],
                how="inner",
            )
            .join(
                commits.select(
                    "fact_id",
                    pl.col("changed_path").alias("right"),
                    pl.col("commit_count").alias("right_commit_count"),
                ),
                on=["fact_id", "right"],
                how="inner",
            )
        )
        tests = (
            self.files()
            .filter(pl.col("is_test"))
            .select("fact_id", pl.col("file_path").alias("test_path"))
        )
        pairs = pairs.join(
            tests,
            left_on=["fact_id", "left"],
            right_on=["fact_id", "test_path"],
            how="anti",
        ).join(
            tests,
            left_on=["fact_id", "right"],
            right_on=["fact_id", "test_path"],
            how="anti",
        )
        return self.references(pairs)

    def files(self) -> pl.LazyFrame:
        """Return file histories with derived commit counts and file locations."""
        files = self.records("files").select(
            "fact_order",
            "fact_id",
            "record_id",
            "ordinal",
            pl.col("path").alias("file_path"),
            "author_count",
            "additional_commit_count",
            "days_since_last_change",
            "line_count",
            "is_test",
        )
        facts = self.facts().select(
            "fact_order",
            "fact_id",
            "language",
            "evidence",
        )
        return files.join(facts, on=["fact_order", "fact_id"], how="inner").with_columns(
            (pl.col("author_count") + pl.col("additional_commit_count")).alias("commit_count"),
            pl.col("file_path").alias("path"),
            pl.lit(1, dtype=pl.UInt64).alias("start_line"),
            pl.lit(0, dtype=pl.UInt64).alias("start_column"),
            pl.lit(1, dtype=pl.UInt64).alias("end_line"),
            pl.lit(0, dtype=pl.UInt64).alias("end_column"),
        )

    def imports(self) -> pl.LazyFrame:
        """Return each file's import lines."""
        files = self.records("files").select(
            "fact_id",
            "record_id",
            pl.col("path").alias("reader"),
        )
        return (
            self.values("files.imports")
            .join(
                files,
                left_on=["fact_id", "parent_id"],
                right_on=["fact_id", "record_id"],
                how="inner",
            )
            .select(
                "fact_id",
                "reader",
                pl.col("string_value").alias("import_line"),
            )
        )

    def references(self, pairs: pl.LazyFrame) -> pl.LazyFrame:
        """Attach how many import lines in either file name its co-changed peer."""
        imports = self.imports()
        keys = ["fact_id", "left", "right"]
        left = pairs.select(
            *keys,
            pl.col("left").alias("reader"),
            _stem(pl.col("right")).alias("stem"),
        ).join(imports, on=["fact_id", "reader"], how="left")
        right = pairs.select(
            *keys,
            pl.col("right").alias("reader"),
            _stem(pl.col("left")).alias("stem"),
        ).join(imports, on=["fact_id", "reader"], how="left")
        pattern = pl.concat_str(
            pl.lit(r"(^|[^\p{L}\p{N}_])"),
            pl.col("stem").str.escape_regex(),
            pl.lit(r"($|[^\p{L}\p{N}_])"),
        )
        references = (
            pl.concat([left, right])
            .filter(pl.col("import_line").str.contains(pattern))
            .group_by(*keys, maintain_order=True)
            .agg(pl.len().cast(pl.UInt64).alias("import_reference_count"))
        )
        return pairs.join(references, on=keys, how="left").with_columns(
            pl.col("import_reference_count").fill_null(0)
        )


def _stem(path: pl.Expr) -> pl.Expr:
    """Return the import name one repository path answers to."""
    filename = path.str.split("/").list.last()
    base = filename.str.split(".").list.first()
    parent = path.str.extract(r"(?:^|/)([^/]+)/[^/]+$", 1)
    package_files = ["__init__", "mod", "lib", "index", "main"]
    return (
        pl.when(base.is_in(package_files) & path.str.contains("/", literal=True))
        .then(parent)
        .otherwise(base)
    )
