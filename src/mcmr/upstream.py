import re
from enum import StrEnum, auto
from functools import cached_property
from importlib.resources import files
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field

from .bases import FrozenFlexModel
from .models import RuleDefinition, RuleScope

if TYPE_CHECKING:
    from collections.abc import Sequence


class Coverage(StrEnum):
    """Say what MCMR does about one rule an upstream tool ships.

    A tool that claims to supersede another owes an account of every rule that other tool emits,
    and the account has to be honest in five different ways. Answering it, choosing not to answer
    it because something else in the stack already does, answering the same concern differently,
    being unable to answer it, and it never having been a question about code are five different
    states, and collapsing them into a coverage percentage hides the only one a reader needs to act
    on.

    The last one earns its place because it was previously counted as a failure. A message
    reporting that a plugin would not load or that a pragma named a numeric identifier says nothing
    about the repository, so calling it unavailable conflates `we cannot do this` with `this was
    never about the code`, understates what MCMR covers, and buries the real gaps underneath
    eighteen entries nobody could ever close.
    """

    NATIVE = auto()
    DELEGATED = auto()
    ADAPTED = auto()
    INAPPLICABLE = auto()
    UNAVAILABLE = auto()


class Relation(StrEnum):
    """Say how one MCMR rule stands to the upstream rule its reference names.

    Only the first two are coverage claims. A citation names prior art and asserts nothing, which
    is what keeps a rule from accidentally claiming a message the account already delegates
    elsewhere by merely mentioning it.
    """

    GENERALIZES = auto()
    ADAPTS = auto()
    CITES = auto()

    @property
    def coverage(self) -> Coverage | None:
        """Return the coverage this relation claims, or nothing when it claims none."""
        return {
            Relation.GENERALIZES: Coverage.NATIVE,
            Relation.ADAPTS: Coverage.ADAPTED,
        }.get(self)

    @property
    def word(self) -> str:
        """Return the word that opens a reference stating this relation."""
        return self.capitalize()


class UpstreamRule(FrozenFlexModel):
    """Identify one rule of one upstream tool by its code, its symbol, or both."""

    tool: str
    code: str = ""
    symbol: str = ""


class ToolProfile(FrozenFlexModel):
    """Describe how one upstream tool spells a rule code and where it documents a rule.

    `codes` is the pattern a code token matches, empty for a tool that identifies a rule by name
    alone. `documentation` is formatted with the code, the symbol, the category the code letter
    names, and the symbol read as a path, so a website generator turns any reference into a link
    without a table of URLs beside it.
    """

    name: str
    codes: str = ""
    documentation: str = ""
    categories: dict[str, str] = {}
    inventoried: bool = False
    languages: tuple[RuleScope, ...] = ()

    @property
    def slug(self) -> str:
        """Return the name this tool's frozen data files are stored under."""
        return self.name.casefold()

    def link(self, rule: UpstreamRule) -> str:
        """Return the page documenting one rule of this tool, empty when none is derivable."""
        if not self.documentation:
            return ""
        return self.documentation.format(
            code=rule.code,
            symbol=rule.symbol,
            category=self.categories.get(rule.code[:1], ""),
            path=rule.symbol.replace("-", "/", 1),
        )


class ToolRegistry(FrozenFlexModel):
    """Name every upstream tool a rule reference may cite, and how each spells a rule.

    A tool absent from here is prose, so adding one is how a reference stops being decoration and
    starts being checked against what that tool actually ships.
    """

    profiles: ClassVar[tuple[ToolProfile, ...]] = (
        ToolProfile(
            name="Pylint",
            codes=r"[CEFIRW]\d{4}",
            documentation=(
                "https://pylint.readthedocs.io/en/stable/user_guide/messages/{category}/{symbol}.html"
            ),
            categories={
                "C": "convention",
                "E": "error",
                "F": "fatal",
                "I": "informational",
                "R": "refactor",
                "W": "warning",
            },
            inventoried=True,
            languages=(RuleScope.PYTHON,),
        ),
        ToolProfile(
            name="Ruff",
            codes=r"[A-Z]{1,5}\d{3,4}",
            documentation="https://docs.astral.sh/ruff/rules/{symbol}/",
            inventoried=True,
            languages=(RuleScope.PYTHON,),
        ),
        ToolProfile(
            name="Clippy",
            documentation="https://rust-lang.github.io/rust-clippy/master/index.html#{symbol}",
            inventoried=True,
            languages=(RuleScope.RUST,),
        ),
        ToolProfile(
            name="clang-tidy",
            documentation="https://clang.llvm.org/extra/clang-tidy/checks/{path}.html",
            inventoried=True,
            languages=(RuleScope.C, RuleScope.CPP, RuleScope.CUDA),
        ),
        ToolProfile(
            name="ESLint",
            documentation="https://eslint.org/docs/latest/rules/{symbol}",
            inventoried=True,
            languages=(RuleScope.TYPESCRIPT,),
        ),
        ToolProfile(
            name="typescript-eslint",
            documentation="https://typescript-eslint.io/rules/{symbol}/",
            inventoried=True,
            languages=(RuleScope.TYPESCRIPT,),
        ),
        ToolProfile(
            name="cppcheck",
            documentation="https://cppcheck.sourceforge.io/manual.html",
            inventoried=True,
            languages=(RuleScope.C, RuleScope.CPP),
        ),
        ToolProfile(
            name="SonarSource",
            codes=r"S\d+",
            documentation="https://rules.sonarsource.com/python/RSPEC-{code}/",
        ),
        ToolProfile(
            name="wemake-python-styleguide",
            codes=r"WPS\d{3}",
            documentation="https://wemake-python-styleguide.readthedocs.io/en/latest/pages/usage/violations/",
        ),
        ToolProfile(
            name="flake8-class-attributes-order",
            codes=r"CCE\d{3}",
            documentation="https://github.com/best-doctor/flake8-class-attributes-order",
        ),
        ToolProfile(name="Vulture", documentation="https://github.com/jendrikseipp/vulture"),
    )

    @cached_property
    def by_name(self) -> dict[str, ToolProfile]:
        """Return every profile keyed by the lowercased name a docstring writes."""
        return {profile.name.casefold(): profile for profile in self.profiles}

    def of(self, name: str) -> ToolProfile | None:
        """Return the profile a token names, or nothing when no registered tool matches."""
        return self.by_name.get(name.casefold())


class SourceKind(StrEnum):
    """Say what kind of thing a rule leaned on, since a book and a linter are not comparable.

    `language` is the documentation of a language itself and `documentation` is the documentation
    of a library or a tool, which are different claims about how settled a statement is. `tool` is
    reserved for an upstream checker whose rules the coverage account answers for, so it never
    appears in the registry of works and is assigned where the two halves meet.
    """

    BOOK = auto()
    PAPER = auto()
    STANDARD = auto()
    LANGUAGE = auto()
    DOCUMENTATION = auto()
    ARTICLE = auto()
    TOOL = auto()


class Work(FrozenFlexModel):
    """One published work a rule may cite, carrying what a citation and a link need.

    The title is the identity, written verbatim inside the quotes of a reference line, which is
    what makes one work one row however many rules cite it. The author is display detail, because
    the question a reader asks is which work shaped the catalog rather than which person did.
    """

    title: str
    kind: SourceKind
    author: str = ""
    link: str = ""

    @property
    def citation(self) -> str:
        """Return the work as a page cites it, the title first and the author behind it."""
        return f"{self.title}, {self.author}" if self.author else self.title


class WorkRegistry(FrozenFlexModel):
    """Name every work a rule reference may cite, and how a page should render each.

    A work absent from here fails the parse rather than becoming a row of its own, which is what
    stops one book arriving twice under two spellings. The registry does no resolution, since the
    title in the reference line is already the key, so it holds only what a citation renders with.
    """

    works: tuple[Work, ...]

    @classmethod
    def load(cls) -> WorkRegistry:
        """Read the registry of works this package ships."""
        return cls.model_validate_json(files("mcmr.data").joinpath("works.json").read_text())

    @cached_property
    def by_title(self) -> dict[str, Work]:
        """Return every work keyed by the title a reference line quotes."""
        return {work.title: work for work in self.works}

    def of(self, title: str) -> Work | None:
        """Return the work a quoted title names, or nothing when none is registered."""
        return self.by_title.get(title)


class Reference(FrozenFlexModel):
    """One entry of a rule's References section, as the docstring writes it.

    An entry names either one rule of one upstream tool, in which case `upstream` holds the
    identity, or one registered work, in which case `work` holds its title and `locator` holds the
    chapter or section the rule leaned on. `relation` says whether MCMR claims the upstream rule.
    """

    text: str = ""
    url: str = ""
    relation: Relation = Relation.CITES
    upstream: UpstreamRule | None = None
    work: str = ""
    locator: str = ""

    @property
    def lines(self) -> tuple[str, ...]:
        """Return the docstring lines this entry was written as."""
        return tuple(line for line in (self.text, self.url) if line)

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

    def with_url(self, url: str) -> Reference:
        """Return this entry carrying the URL written on the line beneath it."""
        return self.model_copy(update={"url": url})


class ReferenceParser(FrozenFlexModel):
    """Read the References section of a rule docstring into structured entries.

    One regular expression reads every line of the section, and it is the grammar rather than a
    description of one, so what `SYSTEM.md` documents and what the catalog is held to cannot drift
    apart. A line is a bare URL attaching to the entry above it, a rule of an upstream tool written
    `relation tool identity [identity]`, or a work written `relation "Title"` with an optional
    locator behind a comma. Nothing else parses, so a section can hold no prose at all.

    The quotes are what make a work syntactically distinct from a tool, which is the same trick the
    relation word plays for the tool half. Both halves are positional and neither infers anything
    from the shape of the words, so `Fluent Python` cannot arrive a second time as
    `Luciano Ramalho, Fluent Python` and a sentence mentioning a tool cannot become a coverage
    claim. An author never appears, because the work is the identity and the person is display
    detail the registry holds.
    """

    tools: ToolRegistry = ToolRegistry()
    works: WorkRegistry = Field(default_factory=WorkRegistry.load)

    grammar: ClassVar[re.Pattern[str]] = re.compile(
        r"(?P<url>https?://\S+)"
        r"|(?P<relation>Generalizes|Adapts|Cites) "
        r"(?:"
        r'"(?P<work>[^"]+)"(?:, (?P<locator>.+))?'
        r"|(?P<tool>[A-Za-z][A-Za-z0-9-]*)(?P<identity>(?: [A-Za-z0-9][\w.-]*){1,2})"
        r")"
    )
    symbols: ClassVar[re.Pattern[str]] = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-_.][A-Za-z0-9]+)*")

    @cached_property
    def relations(self) -> dict[str, Relation]:
        """Return every relation keyed by the word that opens a reference stating it."""
        return {relation.word: relation for relation in Relation}

    def parse(self, lines: Sequence[str]) -> tuple[Reference, ...]:
        """Return one entry per reference, each carrying the URL written beneath it."""
        entries: list[Reference] = []
        for line in lines:
            entry = self.entry(line)
            if entry.url and not entry.text:
                if not entries:
                    raise ValueError(f"Reference {line!r} is a URL with no reference above it")
                entry = entries.pop().with_url(entry.url)
            entries.append(entry)
        return tuple(entries)

    def entry(self, line: str) -> Reference:
        """Return the reference one line states, or the URL it attaches to the entry above."""
        match = self.grammar.fullmatch(line)
        if match is None:
            raise ValueError(f"Reference {line!r} states neither a source nor a URL")
        if match["url"]:
            return Reference(url=line)
        relation = self.relations[match["relation"]]
        if match["work"] is not None:
            return self.cited(line, relation, match["work"], match["locator"] or "")
        return self.named(line, relation, match["tool"], match["identity"].split())

    def cited(self, line: str, relation: Relation, title: str, locator: str) -> Reference:
        """Return the reference naming one work, failing when the registry titles no such work."""
        if self.works.of(title) is None:
            raise ValueError(
                f"Reference {line!r} names {title!r}, which no registered work titles"
            )
        return Reference(text=line, relation=relation, work=title, locator=locator)

    def named(self, line: str, relation: Relation, tool: str, tokens: list[str]) -> Reference:
        """Return the reference naming one rule of one tool, failing when it names no rule."""
        profile = self.tools.of(tool)
        upstream = self.identify(profile, tokens) if profile else None
        if upstream is None:
            raise ValueError(f"Reference {line!r} opens on {relation.word} without naming a rule")
        return Reference(text=line, relation=relation, upstream=upstream)

    def identify(self, profile: ToolProfile, tokens: list[str]) -> UpstreamRule | None:
        """Return the identity the tokens after a tool name spell, when they spell exactly one."""
        codes = [token for token in tokens if profile.codes and re.fullmatch(profile.codes, token)]
        symbols = [
            token for token in tokens if token not in codes and self.symbols.fullmatch(token)
        ]
        recognized = len(codes) + len(symbols)
        if not tokens or len(codes) > 1 or len(symbols) > 1 or recognized != len(tokens):
            return None
        return UpstreamRule(
            tool=profile.name,
            code=next(iter(codes), ""),
            symbol=next(iter(symbols), ""),
        )


class Claim(FrozenFlexModel):
    """One MCMR rule's stated coverage of one upstream rule."""

    upstream: UpstreamRule
    coverage: Coverage
    rule: str
    summary: str
    scope: RuleScope
    fact: str

    def covers(self, profile: ToolProfile) -> bool:
        """Whether this rule answers every language the upstream tool checks.

        A general rule reaches every language only when its providers supply the fact it reads,
        which the provider coverage gate verifies. A language-specific rule can cover a tool only
        when that tool itself has exactly that language boundary.
        """
        return self.scope is RuleScope.GENERAL or profile.languages == (self.scope,)


class ClaimIndex(FrozenFlexModel):
    """Collect every coverage claim the catalog's own docstrings state.

    This is the whole inversion. Provenance is written once, on the rule that earned it, and the
    account of any tool is read back out of the catalog rather than maintained beside it, so the
    two can no longer disagree.
    """

    definitions: tuple[RuleDefinition, ...]
    parser: ReferenceParser = ReferenceParser()

    @cached_property
    def references(self) -> tuple[tuple[RuleDefinition, Reference], ...]:
        """Return every reference every rule states, beside the rule that states it."""
        return tuple(
            (definition, reference)
            for definition in self.definitions
            for reference in self.parser.parse(definition.documentation.references)
        )

    @cached_property
    def claims(self) -> tuple[Claim, ...]:
        """Return every reference that claims coverage, in rule order."""
        return tuple(
            Claim(
                upstream=reference.upstream,
                coverage=coverage,
                rule=definition.id,
                summary=definition.documentation.summary,
                scope=definition.scope,
                fact=definition.fact,
            )
            for definition, reference in self.references
            if reference.upstream is not None and (coverage := reference.relation.coverage)
        )

    @cached_property
    def by_identity(self) -> dict[tuple[str, str], tuple[Claim, ...]]:
        """Return every claim keyed by the tool and by each identity token it names."""
        index: dict[tuple[str, str], list[Claim]] = {}
        for claim in self.claims:
            for token in (claim.upstream.code, claim.upstream.symbol):
                if token:
                    index.setdefault((claim.upstream.tool, token), []).append(claim)
        return {key: tuple(found) for key, found in index.items()}

    def of(self, tool: str, code: str, symbol: str) -> tuple[Claim, ...]:
        """Return every claim naming one rule of one tool, by either of its identity tokens."""
        found = {
            claim.rule: claim
            for token in (code, symbol)
            if token
            for claim in self.by_identity.get((tool, token), ())
            if claim.upstream.code in {"", code} and claim.upstream.symbol in {"", symbol}
        }
        return tuple(found[rule] for rule in sorted(found))


class ToolRule(FrozenFlexModel):
    """Identify one rule in the frozen inventory of one upstream tool."""

    code: str = ""
    symbol: str
    group: str = ""


class Inventory(FrozenFlexModel):
    """Hold every rule one upstream tool ships, frozen from that tool's own registry."""

    tool: str
    version: str
    rules: tuple[ToolRule, ...]

    @classmethod
    def load(cls, tool: str) -> Inventory:
        """Read the inventory this package freezes for one tool."""
        return cls.model_validate_json(files("mcmr.data").joinpath(f"{tool}.json").read_text())


class Gap(FrozenFlexModel):
    """State why MCMR does not answer a set of one tool's rules, and what answers them instead.

    A gap is a statement about the upstream tool rather than about any MCMR rule, which is why it
    lives beside that tool's inventory instead of in code. Naming a whole group is how one sentence
    answers for a checker without repeating itself once per message.
    """

    coverage: Coverage
    reason: str
    symbols: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()


class GapAccount(FrozenFlexModel):
    """Hold every gap recorded beside one tool's inventory, and the fallback for the rest."""

    tool: str
    default: Gap
    gaps: tuple[Gap, ...] = ()

    @classmethod
    def load(cls, tool: str) -> GapAccount:
        """Read the gap account this package records for one tool."""
        source = files("mcmr.data").joinpath(f"{tool}.gaps.json").read_text()
        return cls.model_validate_json(source)

    @cached_property
    def by_symbol(self) -> dict[str, Gap]:
        """Return the gap each named symbol falls to, first statement winning."""
        return {symbol: gap for gap in reversed(self.gaps) for symbol in gap.symbols}

    @cached_property
    def by_group(self) -> dict[str, Gap]:
        """Return the gap each named group falls to, first statement winning."""
        return {group: gap for gap in reversed(self.gaps) for group in gap.groups}

    def gap(self, rule: ToolRule) -> Gap:
        """Return what happens to one rule, from the symbol first and the group after."""
        stated = self.by_symbol.get(rule.symbol) or self.by_group.get(rule.group)
        return stated or self.default


class CoverageEntry(FrozenFlexModel):
    """State what MCMR does about one rule of one upstream tool, and why."""

    rule: ToolRule
    coverage: Coverage
    reason: str
    rules: tuple[str, ...] = ()


class ToolCoverage(FrozenFlexModel):
    """Account for every rule one upstream tool ships, one entry each.

    Resolution runs from the specific to the general. A rule the catalog claims takes the claim, a
    rule the account names outright takes its stated gap, one whose group is named takes that, and
    anything left falls to the default, which says it is unaccounted for rather than quietly
    covered.
    """

    tool: str
    claims: ClaimIndex

    @cached_property
    def profile(self) -> ToolProfile:
        """Return the registered profile of the tool this report accounts for."""
        profile = ToolRegistry().of(self.tool)
        if profile is None:
            raise ValueError(f"{self.tool} is not a registered upstream tool")
        return profile

    @cached_property
    def inventory(self) -> Inventory:
        """Return the frozen inventory of the tool this report accounts for."""
        return Inventory.load(self.profile.slug)

    @cached_property
    def account(self) -> GapAccount:
        """Return the gaps recorded beside that inventory."""
        return GapAccount.load(self.profile.slug)

    @cached_property
    def entries(self) -> tuple[CoverageEntry, ...]:
        """Return one entry for every rule the inventory holds."""
        return tuple(self.entry(rule) for rule in self.inventory.rules)

    def entry(self, rule: ToolRule) -> CoverageEntry:
        """Return what MCMR does about one rule, reading the claims before the gaps."""
        claimed = tuple(
            claim
            for claim in self.claims.of(self.profile.name, rule.code, rule.symbol)
            if claim.covers(self.profile)
        )
        if not claimed:
            gap = self.account.gap(rule)
            return CoverageEntry(rule=rule, coverage=gap.coverage, reason=gap.reason)
        exact = any(claim.coverage is Coverage.NATIVE for claim in claimed)
        named = ", ".join(claim.rule for claim in claimed)
        answers = " ".join(claim.summary for claim in claimed)
        return CoverageEntry(
            rule=rule,
            coverage=Coverage.NATIVE if exact else Coverage.ADAPTED,
            reason=f"MCMR {'generalizes' if exact else 'adapts'} this rule as {named}. {answers}",
            rules=tuple(claim.rule for claim in claimed),
        )

    def tally(self) -> dict[Coverage, int]:
        """Return how many rules fall into each state."""
        return {
            coverage: sum(entry.coverage is coverage for entry in self.entries)
            for coverage in Coverage
        }
