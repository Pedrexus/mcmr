from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from hypothesis import settings
from patos import FrozenModel
from pydantic import BaseModel

from mcmr.domain.contracts import fact_type
from mcmr.facts import Fact, SourceSpan, SyntaxFact, SyntaxNode
from mcmr.kernel import locate
from mcmr.query import RuleQuery
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.table import fact_table

if TYPE_CHECKING:
    from mcmr.domain.contracts import Finding, RuleContract, RuleSetting, RuleValue


def project_root() -> Path:
    """Return the MCMR checkout root used by integration fixtures."""
    return Path(__file__).parents[2]


def kernel_binary() -> Path:
    """Return the analysis kernel built from this checkout."""
    return locate(project_root())


needs_kernel = pytest.mark.skipif(
    not kernel_binary().exists(), reason="the analysis kernel is not built"
)

settings.register_profile("mcmr", max_examples=25, deadline=None)
settings.load_profile("mcmr")


def measured(finding: Finding) -> dict[str, float]:
    """Return the named numbers one finding carries."""
    return {item.name: item.value for item in finding.measurements}


def written(root: Path, sources: Mapping[str, str]) -> Path:
    """Write one project out of a mapping of relative paths to source, and return its root."""
    for name, text in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


@cache
def built_catalog() -> Catalog:
    """Return the one built catalog every test reads its rules and definitions out of."""
    return Catalog(modules=RuleModuleDiscovery().modules)


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    """Return the built catalog, discovered once for the whole session."""
    return built_catalog()


def family_of(rule: RuleContract) -> type[Fact]:
    """Return the fact family one rule declares as its first parameter."""
    first = next(iter(rule.signature.parameters.values()))
    return fact_type(rule.hints[first.name])


def retained_query(
    subject: Fact,
    rule: RuleContract,
    **settings: RuleSetting,
) -> RuleQuery:
    """Invoke one generic rule once over one normalized in-memory table."""
    table = fact_table(type(subject), [subject])
    result = rule.invoke_table(table, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic test rule returned a model query")
    return result


def query_value(query: RuleQuery) -> RuleValue:
    """Return the single non-null scalar emitted for one retained fact."""
    values = query.values.collect()
    for column in ("boolean_value", "integer_value", "float_value", "category_value"):
        scalar = values.get_column(column).drop_nulls()
        if scalar.len() == 1:
            return cast("RuleValue", scalar.item())
    raise TypeError("the rule emitted no single scalar value")


class Declaration(FrozenModel):
    """Build a syntax fact from the file, declaration name, and body a test varies."""

    path: str
    qualname: str = "run"
    kind: str = "callable"
    language: str = "python"
    source: str = ""

    @property
    def span(self) -> SourceSpan:
        """Return the span every node of this declaration is located against."""
        return SourceSpan(path=self.path)

    def around(self, tree: SyntaxNode | None) -> SyntaxFact:
        """Return the fact carrying exactly this tree, which may be no tree at all."""
        return SyntaxFact(
            key=f"syntax:{self.path}:{self.qualname}",
            span=self.span,
            language=self.language,
            qualname=self.qualname,
            kind=self.kind,
            source=self.source,
            tree=tree,
        )

    def of(self, *body: SyntaxNode, span: SourceSpan | None = None) -> SyntaxFact:
        """Return the fact whose declaration node holds the given statements."""
        return self.around(
            SyntaxNode(
                kind=self.kind,
                name=self.qualname,
                text=self.source,
                span=span,
                children=list(body),
            )
        )


type FactValue = (
    bool
    | int
    | float
    | str
    | None
    | BaseModel
    | list[FactValue]
    | tuple[FactValue, ...]
    | dict[str, FactValue]
)

type Declared = (
    bool | int | float | str | None | BaseModel | Sequence[Declared] | Mapping[str, Declared]
)
