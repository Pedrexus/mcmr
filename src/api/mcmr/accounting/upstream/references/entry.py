from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import Field

from ....domain.contracts import RuleScope
from ....rulebook.catalog import RuleDefinition
from ..profiles.relation import Relation
from ..profiles.tools.rule import UpstreamRule

if TYPE_CHECKING:
    from typing import Self

    from ..profiles.coverage import Coverage
    from ..profiles.tools import ToolProfile


class Reference(FrozenModel):
    """One entry of a rule's References section, as the docstring writes it.

    An entry names either one rule of one upstream tool, in which case `upstream`
    holds the identity, or one registered work, in which case `work` holds its
    title and `locator` holds the chapter or section the rule leaned on. `relation`
    says whether MCMR claims the upstream rule.
    """

    text: str = ""
    url: str = ""
    relation: Relation = Relation.CITES
    upstream: UpstreamRule | None = None
    work: str = ""
    locator: str = ""
    definition: RuleDefinition | None = Field(default=None, exclude=True, repr=False)

    @property
    def claimed_definition(self) -> RuleDefinition:
        """Return the definition after proving this reference is an indexed claim."""
        if self.definition is None:
            raise ValueError("an unindexed reference has no claiming rule definition")
        return self.definition

    @property
    def claimed_upstream(self) -> UpstreamRule:
        """Return the upstream identity after proving this reference makes a claim."""
        if self.upstream is None:
            raise ValueError("a work citation does not name an upstream tool rule")
        return self.upstream

    @property
    def coverage(self) -> Coverage:
        """Return the coverage state of a reference that claims one upstream rule."""
        coverage = self.relation.coverage
        if coverage is None:
            raise ValueError("a citation does not claim upstream rule coverage")
        return coverage

    @property
    def fact(self) -> str:
        """Return the fact family of the rule making this claim."""
        return self.claimed_definition.fact

    @property
    def lines(self) -> list[str]:
        """Return the docstring lines this entry was written as."""
        return [line for line in (self.text, self.url) if line]

    @property
    def rule(self) -> str:
        """Return the identity of the rule making this claim."""
        return self.claimed_definition.id

    @property
    def scope(self) -> RuleScope:
        """Return the language scope of the rule making this claim."""
        return self.claimed_definition.scope

    @property
    def source(self) -> str:
        """Return the work title or the tool name this entry names."""
        return self.work or (self.upstream.tool if self.upstream else "")

    @property
    def spelling(self) -> str:
        """Return the one canonical spelling of this entry, empty for a bare URL."""
        if self.work:
            detail = f", {self.locator}" if self.locator else ""
            return f'{self.relation.word} "{self.work}"{detail}'
        if self.upstream is None:
            return ""
        words = (self.relation.word, self.upstream.tool, self.upstream.code, self.upstream.symbol)
        return " ".join(word for word in words if word)

    @property
    def summary(self) -> str:
        """Return the summary of the rule making this claim."""
        return self.claimed_definition.documentation.summary

    def covers(self, profile: ToolProfile) -> bool:
        """Return whether this reference covers the tool's languages."""
        return self.scope is RuleScope.GENERAL or profile.languages == [self.scope]

    def with_url(self, url: str) -> Self:
        """Return this entry carrying the URL written on the line beneath it."""
        return self.model_copy(update={"url": url})
