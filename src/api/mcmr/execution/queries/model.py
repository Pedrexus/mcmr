from enum import StrEnum
from typing import TYPE_CHECKING, cast

import polars as pl

from ...domain.contracts import Unit
from ...query import FindingQuery, RuleQuery
from ...table import CallRelation, ClassRelation, FunctionRelation, GenericRelation
from .calls.relations import CallCandidateRelations
from .classes.relations import ClassCandidateRelations
from .comments.relations import CommentCandidateRelations
from .definitions import ModelMode
from .functions.relations import FunctionCandidateRelations
from .generic.relations import CandidateRelations
from .groups import ModelQueryFields

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...domain.contracts import RuleValue
    from ...facts.foundation import Fact
    from ...table import Table
    from .assessment.contract import AssessmentContract


class ModelQuery[Category: StrEnum = StrEnum](ModelQueryFields[Category]):
    """Carry one lazy candidate relation and its closed contextual judgment contract."""

    uncertain: Category | None = None
    choice_question: str = ""
    choice_options: list[str] = []

    @staticmethod
    def assess[Family: Fact, QueryCategory: StrEnum](
        table: Table[Family],
        *,
        contract: AssessmentContract[QueryCategory],
    ) -> ModelQuery[QueryCategory]:
        """Plan cited predicate estimates followed by one deterministic decision table."""
        return ModelQuery(
            candidates=ModelQuery.candidate_relation(table),
            category=type(contract.default),
            instructions=contract.instructions,
            mode=ModelMode.ASSESS,
            criteria=contract.criteria,
            decision_table=contract.decision_table,
            default=contract.default,
            uncertain=contract.uncertain,
        )

    @staticmethod
    def candidate_relation[Family: Fact](table: Table[Family]) -> pl.LazyFrame:
        """Build one normalized model payload per fact entirely in Polars."""
        if table.relation_type is FunctionRelation:
            relations = FunctionCandidateRelations.function(table)
        elif table.relation_type is CallRelation:
            relations = CallCandidateRelations.calls(table)
        elif table.relation_type is ClassRelation:
            relations = ClassCandidateRelations.classes(table)
        elif (
            table.relation_type is GenericRelation
            and table.family.__name__ == "CommentFact"
            and "node.text" in table.frame(GenericRelation.RECORDS).columns
        ):
            relations = CommentCandidateRelations.comments(table)
        elif table.relation_type is GenericRelation:
            relations = CandidateRelations(
                facts=table.lazy(GenericRelation.FACTS),
                records=table.lazy(GenericRelation.RECORDS),
                values=table.lazy(GenericRelation.VALUES),
            )
        else:
            raise TypeError(f"{table.family.__name__} has no contextual candidate projection")
        return relations.candidates()

    @staticmethod
    def classify[Family: Fact, QueryCategory: StrEnum](
        table: Table[Family],
        *,
        category: type[QueryCategory],
        instructions: str,
    ) -> ModelQuery[QueryCategory]:
        """Plan one closed classification over every fact candidate."""
        return ModelQuery(
            candidates=ModelQuery.candidate_relation(table),
            category=category,
            instructions=instructions,
            mode=ModelMode.CLASSIFY,
        )

    def choice(self, question: str, options: Sequence[str]) -> ModelQuery[Category]:
        """Attach one explicit decision repair to every contextual finding."""
        return self.model_copy(
            update={"choice_question": question, "choice_options": list(options)}
        )

    def matching(
        self,
        identities: pl.LazyFrame,
        *,
        column: str = "fact_id",
    ) -> ModelQuery[Category]:
        """Keep candidates whose identity appears in one rule-owned relational selection."""
        if column not in identities.collect_schema().names():
            raise TypeError(f"a contextual identity selection is missing {column}")
        selected = identities.select(column).unique(maintain_order=True)
        return self.model_copy(
            update={"candidates": self.candidates.join(selected, on=column, how="semi")}
        )

    def project(
        self,
        source: pl.LazyFrame,
        *,
        fields: Sequence[str],
    ) -> ModelQuery[Category]:
        """Replace the default fact projection with independently addressable relation rows."""
        identity = (
            "fact_order",
            "fact_id",
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            "language",
        )
        available = set(source.collect_schema().names())
        required = {*identity, *fields}
        if missing := sorted(required - available):
            raise TypeError(f"a contextual projection is missing {', '.join(missing)}")
        candidates = source.with_columns(
            pl.struct(
                pl.struct(*fields).alias("fields"),
                pl.lit(None).alias("records"),
                pl.lit(None).alias("values"),
            )
            .struct.json_encode()
            .alias("subject_json"),
            pl.lit(None).alias("evidence"),
        ).select(*identity, "subject_json", "evidence")
        return self.model_copy(update={"candidates": candidates})

    def resolved(
        self,
        candidates: pl.DataFrame,
        *,
        answers: pl.DataFrame,
    ) -> RuleQuery[RuleValue]:
        """Reduce typed model answer rows into the ordinary relational rule contract."""
        if self.mode is ModelMode.CLASSIFY:
            return self._classified(candidates, answers=answers)
        return self._assessed(candidates, answers=answers)

    def selected(
        self, accepted_paths: Sequence[str], language: str | None
    ) -> ModelQuery[Category]:
        """Apply one prepared rule's source scope before any candidate reaches a model."""
        accepted_language = (
            pl.lit(True) if language is None else pl.col("language") == pl.lit(language)
        )
        return self.model_copy(
            update={
                "candidates": self.candidates.filter(
                    accepted_language & pl.col("path").is_in(list(accepted_paths))
                )
            }
        )

    def where(
        self,
        predicate: pl.Expr,
        *,
        requires: Sequence[str] = (),
    ) -> ModelQuery[Category]:
        """Keep applicable candidates while sparse contract fixtures remain runnable."""
        available = set(self.candidates.collect_schema().names())
        if not set(requires).issubset(available):
            return self
        return self.model_copy(update={"candidates": self.candidates.filter(predicate)})

    @staticmethod
    def _identity(candidates: pl.DataFrame) -> pl.LazyFrame:
        """Keep only stable fact identity after the model transport consumed its payload."""
        return candidates.select(
            "fact_order",
            "fact_id",
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            "language",
        ).lazy()

    def _answer_matrix(
        self,
        identity: pl.LazyFrame,
        answers: pl.DataFrame,
    ) -> tuple[pl.LazyFrame, list[str]]:
        """Join one model answer column per declared criterion."""
        wide = identity
        columns: list[str] = []
        for criterion in self.criteria:
            column = f"criterion:{criterion.name}"
            columns.append(column)
            wide = wide.join(
                answers.lazy()
                .filter(pl.col("criterion") == criterion.name)
                .select("fact_id", pl.col("answer_value").alias(column)),
                on="fact_id",
                how="inner",
            )
        return wide, columns

    def _assessed(
        self,
        candidates: pl.DataFrame,
        *,
        answers: pl.DataFrame,
    ) -> RuleQuery[RuleValue]:
        """Reduce independent predicate rows through the rule's ordered decision table."""
        identity = self._identity(candidates)
        wide, answer_columns = self._answer_matrix(identity, answers)
        values = self._assessment_values(wide, answer_columns)
        finding_source = (
            answers.lazy()
            .drop("answer_value")
            .join(identity, on="fact_id", how="inner")
            .join(
                values.select(
                    "fact_id",
                    pl.col("answer_value").alias("verdict_value"),
                ),
                on="fact_id",
                how="inner",
            )
            .with_columns(pl.col("verdict_value").alias("answer_value"))
            .drop("verdict_value")
        )
        findings = FindingQuery.build(
            finding_source,
            pl.concat_str(
                pl.lit("`"),
                pl.col("criterion"),
                pl.lit("` is `"),
                pl.col("criterion_value"),
                pl.lit("`. "),
                pl.col("reasoning"),
            ),
            (
                (
                    "criterion confidence",
                    pl.col("confidence") * 100.0,
                    Unit.PERCENTAGE,
                ),
            ),
            finding_order=pl.col("criterion_order"),
            evidence=pl.col("evidence_ids"),
            question=self._question(finding_source),
            options=self.choice_options,
        )
        return cast(
            "RuleQuery[RuleValue]",
            RuleQuery.category(
                values,
                pl.col("answer_value"),
                finding_count=pl.lit(len(self.criteria)),
                findings=findings,
            ),
        )

    def _assessment_values(
        self,
        wide: pl.LazyFrame,
        answer_columns: Sequence[str],
    ) -> pl.LazyFrame:
        """Reduce criterion columns through the ordered decision table."""
        if self.default is None or self.uncertain is None:
            raise TypeError("an assessment query needs default and uncertainty categories")
        verdict = pl.lit(str(self.default))
        for category, requirements in reversed(self.decision_table):
            matches = pl.all_horizontal(
                pl.lit(True),
                *[
                    pl.col(f"criterion:{name}") == pl.lit(str(expected))
                    for name, expected in requirements
                ],
            )
            verdict = pl.when(matches).then(pl.lit(str(category))).otherwise(verdict)
        unknown = pl.any_horizontal(
            *[pl.col(name) == pl.lit("unknown") for name in answer_columns]
        )
        return wide.with_columns(
            pl.when(unknown)
            .then(pl.lit(str(self.uncertain)))
            .otherwise(verdict)
            .alias("answer_value")
        )

    def _classified(
        self,
        candidates: pl.DataFrame,
        *,
        answers: pl.DataFrame,
    ) -> RuleQuery[RuleValue]:
        """Turn one closed category answer per candidate into values and findings."""
        source = self._identity(candidates).join(answers.lazy(), on="fact_id", how="inner")
        findings = FindingQuery.build(
            source,
            pl.col("reasoning"),
            (("model confidence", pl.col("confidence") * 100.0, Unit.PERCENTAGE),),
            evidence=pl.col("evidence_ids"),
            question=self._question(source),
            options=self.choice_options,
        )
        return cast(
            "RuleQuery[RuleValue]",
            RuleQuery.category(
                source,
                pl.col("answer_value"),
                findings=findings,
            ),
        )

    def _question(self, source: pl.LazyFrame) -> str | pl.Expr:
        """Render an optional verdict-aware choice question as one expression."""
        del source
        if not self.choice_question:
            return ""
        before, marker, after = self.choice_question.partition("{value}")
        if not marker:
            return self.choice_question
        return pl.concat_str(pl.lit(before), pl.col("answer_value"), pl.lit(after))
