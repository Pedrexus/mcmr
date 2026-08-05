from enum import StrEnum
from typing import TYPE_CHECKING, TypeIs, cast

import polars as pl
from pydantic import JsonValue, TypeAdapter

from ...domain.contracts import Unit
from ...query import FindingQuery, RuleQuery
from .contracts import Assessment, Classification, ModelMode
from .groups import ModelQueryFields

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ...domain.contracts import ModelProvenance, RuleValue
    from ...facts.foundation import Fact
    from ...table import Table
    from .contracts import AssessmentContract


class ModelQuery[Category: StrEnum = StrEnum](ModelQueryFields[Category]):
    """Carry one lazy candidate relation and its closed contextual judgment contract."""

    uncertain: Category | None = None
    choice_question: str = ""
    choice_options: list[str] = []
    reported: dict[str, str] = {}

    @property
    def stated_instructions(self) -> str:
        """Return the rule instructions beside what selecting each category reports.

        A category name says what the model observed and never what the engine will do with it,
        so `use_plain_class` reads as a recommendation while the policy scores it as a defect. A
        model choosing between names it cannot see the consequences of will pick the one that
        describes its conclusion, which is how a passing subject arrives with a failing label.
        """
        if not self.reported:
            return self.instructions
        stated = "\n".join(
            f"- `{name}` {effect}" for name, effect in sorted(self.reported.items())
        )
        return (
            f"{self.instructions}\n\nWhat selecting each category reports. Choose the category "
            f"the evidence states rather than the one whose report you would prefer.\n{stated}"
        )

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
        return table.contextual_candidates()

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

    def judged(self, reported: Mapping[str, str]) -> ModelQuery[Category]:
        """Record what this project reports for each category the model may select.

        reported: one sentence per category naming what selecting it makes the engine report.
        """
        if self.mode is not ModelMode.CLASSIFY or not reported:
            return self
        return self.model_copy(update={"reported": dict(reported)})

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


def is_model_query(query: RuleQuery | ModelQuery) -> TypeIs[ModelQuery]:
    """Narrow one planned rule result to the contextual query contract."""
    return isinstance(query, ModelQuery)


def answer_frame[Category: StrEnum](
    query: ModelQuery[Category],
    *,
    rows: Sequence[Mapping[str, JsonValue]],
    outcomes: Sequence[Classification[StrEnum] | Assessment],
) -> pl.DataFrame:
    """Normalize typed model results into classification or criterion rows."""
    normalized: list[dict[str, JsonValue]] = []
    for row, outcome in zip(rows, outcomes, strict=True):
        fact_id = TypeAdapter(str).validate_python(row["fact_id"])
        if isinstance(outcome, Classification):
            classification = _provenance_columns(outcome.provenance)
            classification["fact_id"] = fact_id
            classification["answer_value"] = str(outcome.value)
            classification["reasoning"] = outcome.reasoning
            classification["evidence_ids"] = [str(identifier) for identifier in outcome.evidence]
            classification["confidence"] = outcome.confidence
            normalized.append(classification)
            continue
        for order, answer in enumerate(outcome.answers):
            criterion = _provenance_columns(answer.provenance)
            criterion["fact_id"] = fact_id
            criterion["criterion_order"] = order
            criterion["criterion"] = answer.criterion
            criterion["answer_value"] = str(answer.value)
            criterion["criterion_value"] = str(answer.value)
            criterion["reasoning"] = answer.reasoning
            criterion["evidence_ids"] = [str(identifier) for identifier in answer.evidence]
            criterion["confidence"] = answer.confidence
            normalized.append(criterion)
    return pl.DataFrame(normalized, schema=_answer_schema(query.mode))


def _answer_schema(mode: ModelMode) -> dict[str, pl.DataType | type[pl.DataType]]:
    """Return the stable answer relation schema for either contextual operation."""
    shared: dict[str, pl.DataType | type[pl.DataType]] = {
        "fact_id": pl.String,
        "answer_value": pl.String,
        "reasoning": pl.String,
        "evidence_ids": pl.List(pl.String),
        "confidence": pl.Float64,
        "provenance_backend": pl.String,
        "provenance_model": pl.String,
        "provenance_reasoning_effort": pl.String,
        "provenance_input_tokens": pl.UInt64,
        "provenance_cached_input_tokens": pl.UInt64,
        "provenance_output_tokens": pl.UInt64,
        "provenance_reasoning_tokens": pl.UInt64,
    }
    if mode is ModelMode.CLASSIFY:
        return shared
    return {
        "fact_id": pl.String,
        "criterion_order": pl.UInt64,
        "criterion": pl.String,
        "answer_value": pl.String,
        "criterion_value": pl.String,
        "reasoning": pl.String,
        "evidence_ids": pl.List(pl.String),
        "confidence": pl.Float64,
        **{name: dtype for name, dtype in shared.items() if name.startswith("provenance_")},
    }


def _provenance_columns(provenance: ModelProvenance) -> dict[str, JsonValue]:
    """Flatten model provenance into columns shared by every finding row."""
    return {
        "provenance_backend": provenance.backend,
        "provenance_model": provenance.model,
        "provenance_reasoning_effort": provenance.reasoning_effort,
        "provenance_input_tokens": provenance.input_tokens,
        "provenance_cached_input_tokens": provenance.cached_input_tokens,
        "provenance_output_tokens": provenance.output_tokens,
        "provenance_reasoning_tokens": provenance.reasoning_tokens,
    }
