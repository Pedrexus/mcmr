import re
from typing import TYPE_CHECKING

import polars as pl
from patos import FrozenModel
from pydantic import JsonValue, TypeAdapter
from sqlglot import exp, parse
from sqlglot.errors import ParseError, TokenError

from mcmr.facts import (
    DataAsset,
    DataAssetReference,
    DataAssetReferenceFact,
    DataField,
    DataFieldReference,
    DataFieldReferenceFact,
    DataFieldRepair,
    NodeRef,
    SourceSpan,
)

from .catalog import DataHubCatalog

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mcmr.facts import StringExpressionFact
    from mcmr.plugins import Table


class SQLReferenceExtractor(FrozenModel):
    """Resolve literal SQL tables and columns against one exact DataHub catalog."""

    catalog: DataHubCatalog
    dialect: str = ""
    renames: dict[str, dict[str, str]] = {}

    def facts(
        self,
        source: Table[StringExpressionFact],
    ) -> tuple[list[DataAssetReferenceFact], list[DataFieldReferenceFact]]:
        """Build one source-spanned fact pair for each literal containing data references."""
        assets: list[DataAssetReferenceFact] = []
        fields: list[DataFieldReferenceFact] = []
        expressions = (
            source.records("expressions")
            .filter(pl.col("kind") == "literal")
            .join(source.facts().select("fact_id", "language"), on="fact_id", how="left")
        )
        for raw in expressions.collect().iter_rows(named=True):
            row = TypeAdapter(dict[str, JsonValue]).validate_python(raw)
            span = self._span(row)
            asset_references, field_references = self._references(
                self._text(row, "runtime_value"), location=span.location
            )
            if asset_references:
                assets.append(self._asset_fact(row, asset_references))
            if field_references:
                fields.append(self._field_fact(row, field_references))
        return assets, fields

    @staticmethod
    def _asset_reference(
        identifier: str,
        asset: DataAsset | None,
        location: str,
    ) -> DataAssetReference:
        """Retain one table mention and its exact catalog resolution."""
        return DataAssetReference(
            source_location=location,
            asset_identifier=asset.identifier if asset is not None else identifier,
            asset_exists=asset is not None,
            lifecycle=asset.lifecycle if asset is not None else "unknown",
        )

    @staticmethod
    def _canonical(spelling: str) -> str:
        """Return one engine-neutral type name for a spelling either side may use."""
        try:
            return str(exp.DataType.build(spelling).this.name)
        except ParseError, TokenError, ValueError:
            return spelling.strip().upper()

    @staticmethod
    def _casts(statement: exp.Expression) -> dict[str, str]:
        """Map each column the statement casts to the one type it states for it."""
        stated: dict[str, set[str]] = {}
        for cast in statement.find_all(exp.Cast):
            if isinstance(cast.this, exp.Column):
                stated.setdefault(cast.this.name, set()).add(cast.to.sql())
        return {name: next(iter(types)) for name, types in stated.items() if len(types) == 1}

    @staticmethod
    def _only(assets: Sequence[DataAsset]) -> DataAsset | None:
        """Return the sole distinct asset without guessing across a join."""
        unique = {asset.identifier: asset for asset in assets}
        return next(iter(unique.values())) if len(unique) == 1 else None

    @staticmethod
    def _rewritten(text: str, *, retired: str, successor: str) -> str:
        """Return the literal with one whole-word column swapped, or nothing when it repeats."""
        pattern = re.compile(rf"(?<!\w){re.escape(retired)}(?!\w)")
        return pattern.sub(successor, text) if len(pattern.findall(text)) == 1 else ""

    @staticmethod
    def _span(row: Mapping[str, JsonValue]) -> SourceSpan:
        """Project the exact source span the syntax provider retained."""
        return SourceSpan.model_validate(
            {
                name.removeprefix("node.span."): row[name]
                for name in (
                    "node.span.path",
                    "node.span.start_line",
                    "node.span.start_column",
                    "node.span.end_line",
                    "node.span.end_column",
                )
            }
        )

    @staticmethod
    def _text(row: Mapping[str, JsonValue], name: str) -> str:
        """Read one normalized string cell without coercing another scalar type."""
        value = row.get(name)
        return value if isinstance(value, str) else ""

    def _asset_fact(
        self,
        row: Mapping[str, JsonValue],
        references: Sequence[DataAssetReference],
    ) -> DataAssetReferenceFact:
        """Retain resolved asset references at the source string that named them."""
        return DataAssetReferenceFact(
            key=f"{self._text(row, 'node.id')}:data-assets",
            span=self._span(row),
            language=self._text(row, "language") or None,
            references=list(references),
        )

    def _expected_type(self, written: str, field: DataField | None) -> str:
        """Normalize a stated cast against the catalog so only a real disagreement survives.

        Both spellings go through one engine-neutral canonicaliser, because `NUMBER` and `DECIMAL`
        name the same type while `STRING` and `NUMBER` do not, and only the side that knows the
        engine can tell those apart. Agreement is reported as the catalog's own spelling, so the
        rule compares two equal strings and stays quiet. A disagreement keeps the catalog spelling
        on one side and the parser's neutral name on the other, which is why a source writing
        `STRING` reads as `TEXT` in the finding while still naming the type it really wrote.
        """
        if not written or field is None:
            return ""
        return (
            field.data_type
            if self._canonical(written) == self._canonical(field.data_type)
            else written
        )

    def _field_fact(
        self,
        row: Mapping[str, JsonValue],
        references: Sequence[DataFieldReference],
    ) -> DataFieldReferenceFact:
        """Retain resolved field references at the source string that named them."""
        node = self._node(row)
        return DataFieldReferenceFact(
            key=f"{node.id}:data-fields",
            span=node.span,
            language=self._text(row, "language") or None,
            references=[self._repairable(reference, node) for reference in references],
        )

    def _field_reference(
        self,
        column: exp.Column,
        aliases: Mapping[str, DataAsset | None],
        resolved: Sequence[DataAsset],
        casts: Mapping[str, str],
    ) -> DataFieldReference | None:
        """Resolve a qualified column or one belonging to the only resolved table."""
        asset = aliases.get(column.table) if column.table else self._only(resolved)
        if asset is None:
            return None
        field = self.catalog.field(asset, column.name)
        return DataFieldReference(
            asset_identifier=asset.identifier,
            field_name=column.name,
            asset_exists=True,
            field_exists=field is not None,
            expected_type=self._expected_type(casts.get(column.name, ""), field),
            catalog_type=field.data_type if field is not None else "",
        )

    def _node(self, row: Mapping[str, JsonValue]) -> NodeRef:
        """Project the exact literal anchor a verified rewrite edits."""
        return NodeRef(
            id=self._text(row, "node.id"),
            span=self._span(row),
            kind=self._text(row, "node.kind"),
            text=self._text(row, "node.text"),
        )

    def _references(
        self,
        text: str,
        *,
        location: str,
    ) -> tuple[list[DataAssetReference], list[DataFieldReference]]:
        """Read one direct URN or parse every SQL statement in one literal."""
        if text.startswith("urn:li:dataset:("):
            return [self._asset_reference(text, self.catalog.resolve(text), location)], []
        try:
            statements = parse(text, read=self.dialect or None)
        except ParseError, TokenError:
            return [], []
        assets: list[DataAssetReference] = []
        fields: list[DataFieldReference] = []
        for statement in statements:
            if statement is None:
                continue
            found_assets, found_fields = self._statement(statement, location)
            assets.extend(found_assets)
            fields.extend(found_fields)
        return assets, fields

    def _repairable(self, reference: DataFieldReference, node: NodeRef) -> DataFieldReference:
        """Attach the literal anchor and only the rewrite a catalog-proven rename licenses."""
        successor = self.renames.get(reference.asset_identifier, {}).get(reference.field_name, "")
        replacement = (
            self._rewritten(node.text, retired=reference.field_name, successor=successor)
            if successor and not reference.field_exists
            else ""
        )
        return reference.model_copy(
            update={"repair": DataFieldRepair(node=node, replacement=replacement)}
        )

    def _statement(
        self,
        statement: exp.Expression,
        location: str,
    ) -> tuple[list[DataAssetReference], list[DataFieldReference]]:
        """Resolve the tables and unambiguous columns in one parsed SQL statement."""
        tables = [
            (table, self.catalog.resolve(".".join(part.name for part in table.parts)))
            for table in statement.find_all(exp.Table)
        ]
        aliases = {table.alias_or_name: asset for table, asset in tables}
        resolved = [asset for _table, asset in tables if asset is not None]
        casts = self._casts(statement)
        assets = [
            self._asset_reference(
                ".".join(part.name for part in table.parts),
                asset,
                location,
            )
            for table, asset in tables
        ]
        fields = [
            reference
            for column in statement.find_all(exp.Column)
            if not column.is_star
            if (reference := self._field_reference(column, aliases, resolved, casts)) is not None
        ]
        return assets, fields
