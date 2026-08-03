from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from hypothesis import strategies as st
from patos import FrozenModel

from mcmr.domain.contracts import RuleSetting, RuleValue
from mcmr.facts import Fact
from mcmr.query import RuleQuery

from ..support import kernel_binary
from .adapters import Oracle, required_row_value, scalar_row
from .contracts import Report, Site, contract, extracted, retained_fact, tabled

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


class RuleReader(FrozenModel, ABC):
    """Run one MCMR rule over one tree through the real kernel and say where it answered.

    A rule locates a finding as precisely as the fact it read allows, and that is a property of the
    rule rather than of the comparison, so each subclass is one of the three answers a rule can
    give. Nothing here reads a rule's condition a second time: the rule is always the judge and a
    reader only asks it and records where it spoke.
    """

    rule_id: str
    family: type[Fact]
    settings: dict[str, RuleSetting] = {}
    languages: list[str] = []
    suffixes: list[str] = []

    @property
    def name(self) -> str:
        """Return the rule this reader runs."""
        return self.rule_id

    def counted(self, subject: Fact) -> int:
        """Return how many findings the rule answered with about one fact."""
        value = scalar(self.queried(subject))
        return int(value) if isinstance(value, bool | int) else 0

    def facts(self, root: Path) -> list[Fact]:
        """Return the family this rule reads, narrowed to the languages the case asked for."""
        stream = extracted(root, self.family, *self.suffixes)
        if not self.languages:
            return stream
        return [fact for fact in stream if fact.language in self.languages]

    def narrowed_values(self, query: RuleQuery) -> list[Mapping[str, RuleValue | None]]:
        """Narrow one completed query's values to requested languages."""
        rows = query.values.collect().iter_rows(named=True)
        return [row for row in rows if not self.languages or row["language"] in self.languages]

    def queried(self, subject: Fact) -> RuleQuery:
        """Return the deterministic table query planned for one retained fact."""
        table = retained_fact(subject)
        result = contract(self.rule_id).invoke_table(
            table, settings=self.settings, dependencies={}
        )
        if not isinstance(result, RuleQuery):
            raise TypeError(f"{self.rule_id} returned a contextual model query")
        return result

    def query(self, root: Path) -> RuleQuery:
        """Run this rule once over the native table for the whole repository."""
        result = contract(self.rule_id).invoke_table(
            tabled(root, self.family, *self.suffixes),
            settings=self.settings,
            dependencies={},
        )
        if not isinstance(result, RuleQuery):
            raise TypeError(f"{self.rule_id} returned a contextual model query")
        return result

    def report(self, root: Path) -> Report:
        """Return where this rule reported over one tree."""
        return Report(reader=self.name, sites=list(self.sites(root)))

    @abstractmethod
    def sites(self, root: Path) -> Iterable[Site]:
        """Return every site this rule reported over one tree."""

    def stated(self, subject: Fact) -> list[Site]:
        """Return the span of every finding the rule stated about one fact."""
        query = self.queried(subject)
        if query.findings is None:
            return []
        return [
            Site(path=row["path"], line=row["start_line"], through=row["end_line"])
            for row in query.findings.rows.collect().iter_rows(named=True)
        ]

    def values(self, root: Path) -> list[Mapping[str, RuleValue | None]]:
        """Return this rule's value rows narrowed to requested languages."""
        return self.narrowed_values(self.query(root))


class DeclarationReader(RuleReader):
    """Locate every finding at the declaration the rule answered about, once per unit it counted.

    A rule reading one declaration answers for the whole of it, so the declaration is the finest
    place a count can be pinned to and the count is how many findings sit inside it. Repeating the
    range gives a multiset an oracle's lines fold into, so a rule counting three findings in a
    callable that holds one of them fails even where the totals agree.
    """

    def sites(self, root: Path) -> Iterable[Site]:
        """Return one site per finding, at the range of the declaration that holds it."""
        return [
            Site(
                path=required_row_value(row, "path", str),
                line=required_row_value(row, "start_line", int),
                through=required_row_value(row, "end_line", int),
            )
            for row in self.values(root)
            for _ in range(int(scalar_row(row)))
        ]


class MeasureReader(RuleReader):
    """Locate a measurement at the declaration it measures, once per unit of the magnitude.

    A measurement is a property of the declaration rather than a total over the facts that state
    it, so where a family emits one fact per relationship a declaration takes part in, the
    magnitude is the greatest any of them answered rather than their sum. Two `OverrideFact`
    records about one derived class both state that it has two ancestors, and adding them would
    report four.
    """

    def sites(self, root: Path) -> Iterable[Site]:
        """Return one site per unit of the greatest magnitude measured at each declaration."""
        greatest: dict[Site, int] = {}
        for row in self.values(root):
            where = Site(
                path=required_row_value(row, "path", str),
                line=required_row_value(row, "start_line", int),
                through=required_row_value(row, "end_line", int),
            )
            greatest[where] = max(greatest.get(where, 0), int(scalar_row(row)))
        return [where for where, magnitude in greatest.items() for _ in range(magnitude)]


class FindingReader(RuleReader):
    """Locate every finding where the rule itself said it is.

    A rule that has migrated to reporting findings states a span for each one, which is the most
    precise answer available and needs no second reading of anything.
    """

    def sites(self, root: Path) -> Iterable[Site]:
        """Return the span of every finding the rule stated."""
        query = self.query(root)
        if query.findings is None:
            return []
        allowed = {str(row["fact_id"]) for row in self.narrowed_values(query)}
        return [
            Site(path=row["path"], line=row["start_line"], through=row["end_line"])
            for row in query.findings.rows.collect().iter_rows(named=True)
            if str(row["fact_id"]) in allowed
        ]


class RecordReader(RuleReader):
    """Locate every finding at the record inside a fact that caused it.

    A fact carries every record one file states and the rule answers with one number for all of
    them, so comparing against a reader that names a line needs the rule asked again for each
    record alone. The rule stays the judge, which is what makes this a comparison of findings
    rather than a restatement of the rule's condition beside it.
    """

    field: str

    def sites(self, root: Path) -> Iterable[Site]:
        """Return the node of every record the rule reported when it was handed that record."""
        return [
            Site.at(fact.span.path, record.node.span.start_line)
            for fact in self.facts(root)
            for record in getattr(fact, self.field)
            if self.counted(fact.model_copy(update={self.field: [record]}))
            and record.node is not None
        ]


class Shape(FrozenModel):
    """One source shape and which of its own lines a reader is expected to keep reporting.

    The answer travels with the shape rather than being read back out of the source afterwards, so
    a property built from these states an opinion of its own instead of only comparing two readers
    of the same text. `opening` holds what has to stay at the top of a file, such as an import or
    an include, and `body` holds the rest. `reported` indexes into the two concatenated, so a shape
    states its answer wherever the answer sits.
    """

    opening: list[str] = []
    body: list[str] = []
    reported: set[int] = set()


class Source(FrozenModel):
    """One generated source and the lines a reader is expected to report in it."""

    text: str
    reported: set[int]


@st.composite
def assembled(
    draw: st.DrawFn,
    shapes: list[Shape],
    *,
    prologue: list[str] | None = None,
    limit: int = 6,
) -> Source:
    """Build one source out of independent shapes and state which of its lines stay reported.

    Every shape names its own declarations, so any subset of them concatenates into a source that
    still says what each of them means. The openings gather at the top in the order they were drawn
    and the bodies follow, which is what a language demanding its imports first requires and what
    every other language tolerates.
    """
    drawn = draw(st.lists(st.sampled_from(shapes), min_size=1, max_size=limit, unique_by=id))
    opening = [] if prologue is None else list(prologue)
    openings: list[int] = []
    for shape in drawn:
        openings.append(len(opening) + 1)
        opening.extend(shape.opening)
    body: list[str] = []
    bodies: list[int] = []
    for shape in drawn:
        body.extend(("", ""))
        bodies.append(len(opening) + len(body) + 1)
        body.extend(shape.body)
    return Source(
        text="\n".join([*opening, *body, ""]),
        reported={
            openings[index] + offset
            if offset < len(shape.opening)
            else bodies[index] + offset - len(shape.opening)
            for index, shape in enumerate(drawn)
            for offset in shape.reported
        },
    )


def scalar[Value: RuleValue](query: RuleQuery[Value]) -> Value:
    """Return the scalar from a query that produced exactly one value row."""
    values = query.values.collect()
    if values.height != 1:
        raise ValueError(f"expected one value row and received {values.height}")
    return cast("Value", scalar_row(values.row(0, named=True)))


class Trees(FrozenModel):
    """Write one fresh tree per generated example, under a directory pytest cleans up.

    A reading is cached by the tree it read, so a property that draws a new source has to write it
    somewhere nothing has been asked about yet. The number of trees already grown is read off the
    filesystem rather than counted, which keeps this frozen and keeps two properties sharing one
    directory from handing out the same name.
    """

    root: Path

    def grow(self, sources: Mapping[str, str]) -> Path:
        """Write one more generated tree and return it."""
        planted = self.root / f"tree{sum(1 for _ in self.root.iterdir())}"
        planted.mkdir()
        return written(planted, sources)


def written(root: Path, sources: Mapping[str, str]) -> Path:
    """Write one generated source per relative name and return the tree holding them."""
    for relative, source in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return root


needs_kernel = pytest.mark.skipif(
    not kernel_binary().exists(),
    reason="a differential oracle needs the kernel binary this checkout builds",
)


def needs(*tools: str) -> pytest.MarkDecorator:
    """Skip a case whose oracle is not installed here, naming which tool is missing.

    A skipped oracle proves nothing, so the reason names the tool rather than the case, and the
    suite's own summary is then the ledger of what could not be checked on this machine.
    """
    absent = sorted(tool for tool in tools if not Oracle.installed(tool))
    return pytest.mark.skipif(
        bool(absent), reason=f"the differential oracle needs {', '.join(absent)} installed"
    )
