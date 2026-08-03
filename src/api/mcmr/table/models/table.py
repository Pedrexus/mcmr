from enum import StrEnum
from typing import TYPE_CHECKING, cast

import polars as pl

from ...facts import Fact
from ..names import GenericRelation

if TYPE_CHECKING:
    from collections.abc import Mapping, Set


class Table[Family: Fact]:
    """Expose one fact family's shared relations as reusable lazy query roots."""

    def __init__[Relation: StrEnum](
        self,
        family: type[Family],
        *,
        relation_type: type[Relation],
        frames: Mapping[Relation, pl.DataFrame],
        languages: set[str] | None = None,
    ) -> None:
        """Require every family relation exactly once."""
        self._family = family
        self.relation_type: type[StrEnum] = relation_type
        self.frames = self._relation_frames(frames)
        self.languages = set(languages or set())
        self.views: dict[str, Table[Fact]] = {}
        self._validate_relations()
        self.relations = self._roots()

    @property
    def family(self) -> type[Family]:
        """Return the exact fact family whose relations this table owns."""
        return self._family

    def counted(self, selected: pl.LazyFrame, value: pl.Expr | None = None) -> pl.LazyFrame:
        """Attach one selected-row count or sum to every fact."""
        counts = selected.group_by("fact_id", maintain_order=True).agg(
            (pl.len() if value is None else value.sum()).cast(pl.UInt64).alias("value")
        )
        return (
            self.facts()
            .join(counts, on="fact_id", how="left")
            .with_columns(pl.col("value").fill_null(0))
        )

    def coverage(self, population: pl.LazyFrame, complete: pl.Expr) -> pl.LazyFrame:
        """Attach the percentage of selected records satisfying one predicate."""
        measured = population.group_by("fact_id", maintain_order=True).agg(
            pl.len().alias("in_scope"),
            complete.sum().alias("complete"),
        )
        return (
            self.facts()
            .join(measured, on="fact_id", how="left")
            .with_columns(
                pl.col("in_scope").fill_null(0),
                pl.col("complete").fill_null(0),
            )
            .with_columns(
                pl.when(pl.col("in_scope") == 0)
                .then(0.0)
                .otherwise(pl.col("complete") / pl.col("in_scope") * 100.0)
                .alias("value")
            )
        )

    def facts(self) -> pl.LazyFrame:
        """Return fact rows with their ordered provider evidence."""
        evidence = (
            self.records("evidence")
            .group_by("fact_id", maintain_order=True)
            .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
        )
        return (
            self.lazy(GenericRelation.FACTS)
            .join(evidence, on="fact_id", how="left")
            .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
        )

    def frame(self, relation: StrEnum) -> pl.DataFrame:
        """Return one eager relation after proving it belongs to this family."""
        if not isinstance(relation, self.relation_type):
            raise TypeError(f"{relation} does not name a {self.family.__name__} table relation")
        return self.frames[relation] if not self.languages else self.relations[relation].collect()

    def lazy(self, relation: StrEnum) -> pl.LazyFrame:
        """Return the shared lazy root for one normalized relation."""
        if not isinstance(relation, self.relation_type):
            raise TypeError(f"{relation} does not name a {self.family.__name__} table relation")
        return self.relations[relation]

    def records(self, relation: str) -> pl.LazyFrame:
        """Return object records from one exact schema relation."""
        return self.lazy(GenericRelation.RECORDS).filter(pl.col("relation") == relation)

    def restricted(self, languages: set[str]) -> Table[Family]:
        """Return one cached language-filtered view over these shared relation roots."""
        if not languages or languages == self.languages:
            return self
        key = "\0".join(sorted(languages))
        if cached := self.views.get(key):
            return cast("Table[Family]", cached)
        return self._restricted_view(key, languages)

    def value_counts(self, relation: str) -> pl.LazyFrame:
        """Attach the number of scalar values in one relation to every fact."""
        return self.counted(self.values(relation))

    def values(self, relation: str) -> pl.LazyFrame:
        """Return scalar values from one exact schema relation."""
        return self.lazy(GenericRelation.VALUES).filter(pl.col("relation") == relation)

    @staticmethod
    def _relation_frames[Relation: StrEnum](
        frames: Mapping[Relation, pl.DataFrame],
    ) -> dict[StrEnum, pl.DataFrame]:
        """Erase only the relation enum subtype after construction validates it."""
        return {cast("StrEnum", relation): frame for relation, frame in frames.items()}

    def _read_languages(self, primary: StrEnum) -> set[str]:
        """Read the languages observed in the identity relation."""
        if "language" not in self.frames[primary].columns:
            raise TypeError(f"{self.family.__name__} table has no language identity")
        return {
            str(language)
            for language in self.frames[primary].get_column("language").drop_nulls().to_list()
        }

    def _relation_difference(
        self,
        *,
        expected: Set[StrEnum],
        received: Set[StrEnum],
    ) -> str:
        """Describe missing and unexpected relation names."""
        missing = ", ".join(sorted(str(relation) for relation in expected - received))
        unexpected = ", ".join(sorted(str(relation) for relation in received - expected))
        return (
            f"{self.family.__name__} table relations differ, missing [{missing}], "
            f"unexpected [{unexpected}]"
        )

    def _restrict_roots(
        self,
        roots: dict[StrEnum, pl.LazyFrame],
        primary: StrEnum,
    ) -> dict[StrEnum, pl.LazyFrame]:
        """Filter the identity relation when this table is language-scoped."""
        if not self.languages:
            return roots
        self.observed_languages &= self.languages
        selected = roots[primary].filter(pl.col("language").is_in(sorted(self.languages)))
        return {
            relation: selected if relation is primary else root for relation, root in roots.items()
        }

    def _restricted_view(self, key: str, languages: set[str]) -> Table[Family]:
        """Create and remember one language-filtered view."""
        view = Table(
            self.family,
            relation_type=self.relation_type,
            frames=self.frames,
            languages=languages,
        )
        self.views[key] = cast("Table[Fact]", view)
        return view

    def _roots(self) -> dict[StrEnum, pl.LazyFrame]:
        """Create lazy roots and their observed language identity."""
        roots = {relation: frame.lazy() for relation, frame in self.frames.items()}
        primary = next(iter(self.relation_type))
        self.observed_languages = self._read_languages(primary)
        return self._restrict_roots(roots, primary)

    def _validate_relations(self) -> None:
        """Prove that each required relation occurs exactly once."""
        if any(not isinstance(relation, self.relation_type) for relation in self.frames):
            raise TypeError(f"a relation does not belong to {self.family.__name__}")
        expected = set(self.relation_type)
        received = set(self.frames)
        if expected != received:
            raise ValueError(self._relation_difference(expected=expected, received=received))
