from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from .relations import OverrideTables

_PAIR = ["fact_id", "inherited_id", "declared_id"]
_PLACEHOLDER = r"^(?:_+$|_[a-zA-Z0-9_]*[a-zA-Z0-9]$|dummy|ignored_|unused_)"


class SignatureTables:
    """Derive substitutability measurements from normalized override signatures."""

    def __init__(self, relations: OverrideTables) -> None:
        self.relations = relations

    def changes(self) -> pl.LazyFrame:
        """Return one row of signature changes for every comparable override."""
        pairs = self._pairs()
        inherited = self._parameters(pairs, "inherited")
        declared = self._parameters(pairs, "declared")
        declared_varargs = self._has_kind(
            parameters=declared,
            kind="var_positional",
            name="declared_varargs",
        )
        declared_kwargs = self._has_kind(
            parameters=declared,
            kind="var_keyword",
            name="declared_kwargs",
        )
        held_positions, declared_positions, positions_changed, slots_changed = (
            self._positional_changes(
                inherited=inherited,
                declared=declared,
                declared_varargs=declared_varargs,
            )
        )
        keywords_changed = self._keyword_changes(
            inherited=inherited,
            declared=declared,
            declared_kwargs=declared_kwargs,
        )
        return self._join_changes(
            pairs,
            positions_changed,
            slots_changed,
            keywords_changed,
            self._variadics_removed(inherited=inherited, declared=declared),
            self._renames(
                inherited=held_positions,
                declared=declared_positions,
                counts_changed=positions_changed,
            ),
            declared_varargs,
            self._optional_counts(inherited=inherited, declared=declared),
        )

    @staticmethod
    def _counts_changed(
        *,
        inherited: pl.LazyFrame,
        declared: pl.LazyFrame,
        name: str,
    ) -> pl.LazyFrame:
        """State whether ordered parameter lists stopped accepting the same positions."""
        held = inherited.select(
            *_PAIR,
            "position",
            pl.lit(True).alias("held"),
        )
        answers = declared.select(
            *_PAIR,
            "position",
            pl.lit(True).alias("answered"),
            pl.col("has_default").alias("answer_has_default"),
        )
        return (
            held.join(
                answers,
                on=[*_PAIR, "position"],
                how="full",
                coalesce=True,
            )
            .group_by(*_PAIR)
            .agg(
                (
                    (pl.col("held").fill_null(False) & ~pl.col("answered").fill_null(False))
                    | (
                        ~pl.col("held").fill_null(False)
                        & pl.col("answered").fill_null(False)
                        & ~pl.col("answer_has_default").fill_null(False)
                    )
                )
                .any()
                .alias(name)
            )
        )

    @staticmethod
    def _has_kind(*, parameters: pl.LazyFrame, kind: str, name: str) -> pl.LazyFrame:
        """State whether each pair's declaration carries one parameter kind."""
        return (
            parameters.filter(pl.col("kind") == kind)
            .select(*_PAIR)
            .unique()
            .with_columns(pl.lit(True).alias(name))
        )

    @staticmethod
    def _join_changes(pairs: pl.LazyFrame, *relations: pl.LazyFrame) -> pl.LazyFrame:
        """Join every derived signature relation and calculate the two final counts."""
        changes = pairs.select(*_PAIR)
        for relation in relations:
            changes = changes.join(relation, on=_PAIR, how="left")
        changed = (
            pl.col("positions_changed").fill_null(False)
            | pl.col("slots_changed").fill_null(False)
            | pl.col("keywords_changed").fill_null(False)
        )
        differing = changed.cast(pl.UInt64) + pl.col("variadics_removed").fill_null(False).cast(
            pl.UInt64
        )
        return changes.with_columns(
            differing.alias("differing_arguments"),
            pl.col("renamed_parameters").fill_null(0).cast(pl.UInt64),
        ).with_columns(
            (
                (pl.col("differing_arguments") == 0)
                & (pl.col("renamed_parameters") == 0)
                & ~pl.col("declared_varargs").fill_null(False)
                & (
                    pl.col("declared_optional").fill_null(0)
                    < pl.col("inherited_optional").fill_null(0)
                )
            )
            .cast(pl.UInt64)
            .alias("required_what_the_base_defaulted")
        )

    @staticmethod
    def _keywords_changed(
        *,
        inherited: pl.LazyFrame,
        declared: pl.LazyFrame,
    ) -> pl.LazyFrame:
        """State whether required keyword names differ across the two signatures."""
        held = inherited.select(*_PAIR, "name").unique()
        answers = declared.select(*_PAIR, "name", "has_default").unique()
        missing = held.join(
            answers.select(*_PAIR, "name"),
            on=[*_PAIR, "name"],
            how="anti",
        ).select(*_PAIR)
        added = (
            answers.join(held, on=[*_PAIR, "name"], how="anti")
            .filter(~pl.col("has_default"))
            .select(*_PAIR)
        )
        return (
            pl.concat([missing, added], how="vertical")
            .unique()
            .with_columns(pl.lit(True).alias("keywords_changed"))
        )

    @staticmethod
    def _optional_counts(
        *,
        inherited: pl.LazyFrame,
        declared: pl.LazyFrame,
    ) -> pl.LazyFrame:
        """Count optional positional arguments on both sides of each pair."""
        kinds = ["positional_only", "positional_or_keyword"]
        held = (
            inherited.filter(pl.col("has_default") & pl.col("kind").is_in(kinds))
            .group_by(*_PAIR)
            .agg(pl.len().cast(pl.UInt64).alias("inherited_optional"))
        )
        answers = (
            declared.filter(pl.col("has_default") & pl.col("kind").is_in(kinds))
            .group_by(*_PAIR)
            .agg(pl.len().cast(pl.UInt64).alias("declared_optional"))
        )
        return held.join(answers, on=_PAIR, how="full", coalesce=True)

    @staticmethod
    def _renames(
        *,
        inherited: pl.LazyFrame,
        declared: pl.LazyFrame,
        counts_changed: pl.LazyFrame,
    ) -> pl.LazyFrame:
        """Count corresponding named positions whose public name changed."""
        compared = inherited.select(
            *_PAIR,
            "position",
            pl.col("name").alias("inherited_name"),
        ).join(
            declared.select(
                *_PAIR,
                "position",
                pl.col("name").alias("declared_name"),
            ),
            on=[*_PAIR, "position"],
            how="inner",
        )
        return (
            compared.join(counts_changed, on=_PAIR, how="left")
            .filter(
                ~pl.col("positions_changed").fill_null(False)
                & (pl.col("inherited_name") != pl.col("declared_name"))
                & ~pl.col("inherited_name").str.contains(_PLACEHOLDER)
                & ~pl.col("declared_name").str.contains(_PLACEHOLDER)
            )
            .group_by(*_PAIR)
            .agg(pl.len().cast(pl.UInt64).alias("renamed_parameters"))
        )

    @staticmethod
    def _sequence(
        *,
        parameters: pl.LazyFrame,
        kind: str,
        classmethod_column: str = "",
    ) -> pl.LazyFrame:
        """Return one binding kind with a stable ordinal inside each signature."""
        selected = (
            parameters.filter(pl.col("kind") == kind)
            .sort(*_PAIR, "ordinal")
            .with_columns(pl.col("ordinal").cum_count().over(_PAIR).alias("position"))
        )
        if classmethod_column:
            selected = selected.filter(~pl.col(classmethod_column) | (pl.col("position") > 1))
        return selected.select(*_PAIR, "position", "name", "has_default")

    @staticmethod
    def _unswallowed(
        *,
        inherited: pl.LazyFrame,
        declared: pl.LazyFrame,
        tail: pl.LazyFrame,
        tail_column: str,
    ) -> pl.LazyFrame:
        """Keep only inherited names a declared variadic tail does not swallow."""
        answered = (
            declared.select(*_PAIR, "name")
            .unique()
            .with_columns(pl.lit(True).alias("answered_by_name"))
        )
        return (
            inherited.join(tail, on=_PAIR, how="left")
            .join(answered, on=[*_PAIR, "name"], how="left")
            .filter(
                ~pl.col(tail_column).fill_null(False) | pl.col("answered_by_name").fill_null(False)
            )
            .select(*_PAIR, "position", "name", "has_default")
        )

    @staticmethod
    def _variadics_removed(
        *,
        inherited: pl.LazyFrame,
        declared: pl.LazyFrame,
    ) -> pl.LazyFrame:
        """State whether the base offered a variadic tail the override removed."""
        inherited_tails = inherited.filter(
            pl.col("kind").is_in(["var_positional", "var_keyword"])
        ).select(*_PAIR, "kind")
        declared_tails = declared.filter(
            pl.col("kind").is_in(["var_positional", "var_keyword"])
        ).select(*_PAIR, "kind")
        return (
            inherited_tails.join(declared_tails, on=[*_PAIR, "kind"], how="anti")
            .select(*_PAIR)
            .unique()
            .with_columns(pl.lit(True).alias("variadics_removed"))
        )

    def _keyword_changes(
        self,
        *,
        inherited: pl.LazyFrame,
        declared: pl.LazyFrame,
        declared_kwargs: pl.LazyFrame,
    ) -> pl.LazyFrame:
        """Compare keyword-only names after accounting for a variadic tail."""
        inherited_keywords = self._sequence(parameters=inherited, kind="keyword_only")
        declared_keywords = self._sequence(parameters=declared, kind="keyword_only")
        held_keywords = self._unswallowed(
            inherited=inherited_keywords,
            declared=declared_keywords,
            tail=declared_kwargs,
            tail_column="declared_kwargs",
        )
        return self._keywords_changed(inherited=held_keywords, declared=declared_keywords)

    def _pairs(self) -> pl.LazyFrame:
        """Return method pairs whose call signatures are meaningfully comparable."""
        return self.relations.paired_members().filter(
            pl.col("inherited_callable")
            & pl.col("declared_callable")
            & ~pl.col("name").str.starts_with("__")
            & ~pl.col("declared_setter")
        )

    def _parameters(self, pairs: pl.LazyFrame, side: str) -> pl.LazyFrame:
        """Attach one side's ordered parameter records to each comparable pair."""
        return pairs.select(
            *_PAIR,
            f"{side}_classmethod",
        ).join(
            self.relations.records(f"{side}.parameters").select(
                pl.col("parent_id").alias(f"{side}_id"),
                "ordinal",
                "name",
                "kind",
                "has_default",
            ),
            on=f"{side}_id",
            how="inner",
        )

    def _positional_changes(
        self,
        *,
        inherited: pl.LazyFrame,
        declared: pl.LazyFrame,
        declared_varargs: pl.LazyFrame,
    ) -> tuple[pl.LazyFrame, pl.LazyFrame, pl.LazyFrame, pl.LazyFrame]:
        """Compare named positions and positional-only slots against a variadic tail."""
        inherited_positions = self._sequence(
            parameters=inherited,
            kind="positional_or_keyword",
            classmethod_column="inherited_classmethod",
        )
        declared_positions = self._sequence(
            parameters=declared,
            kind="positional_or_keyword",
            classmethod_column="declared_classmethod",
        )
        held_positions = self._unswallowed(
            inherited=inherited_positions,
            declared=declared_positions,
            tail=declared_varargs,
            tail_column="declared_varargs",
        )
        positions_changed = self._counts_changed(
            inherited=held_positions,
            declared=declared_positions,
            name="positions_changed",
        )
        inherited_slots = self._sequence(parameters=inherited, kind="positional_only")
        declared_slots = self._sequence(parameters=declared, kind="positional_only")
        held_slots = self._unswallowed(
            inherited=inherited_slots,
            declared=declared_slots,
            tail=declared_varargs,
            tail_column="declared_varargs",
        )
        slots_changed = self._counts_changed(
            inherited=held_slots,
            declared=declared_slots,
            name="slots_changed",
        )
        return held_positions, declared_positions, positions_changed, slots_changed
