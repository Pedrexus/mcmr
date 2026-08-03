import re
from typing import TYPE_CHECKING, ClassVar

from patos import FrozenModel
from pydantic import Field

from ..profiles.relation import Relation
from ..profiles.tools import ToolRegistry
from ..profiles.tools.rule import UpstreamRule
from ..profiles.works import WorkRegistry
from .entry import Reference

if TYPE_CHECKING:
    from collections.abc import Sequence


class ReferenceParser(FrozenModel):
    """Read a rule docstring's References section into structured entries."""

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

    @property
    def relations(self) -> dict[str, Relation]:
        """Return every relation keyed by the word that opens a reference stating it."""
        return {relation.word: relation for relation in Relation}

    def cited(
        self,
        line: str,
        relation: Relation,
        *,
        title: str,
        locator: str,
    ) -> Reference:
        """Return a work reference, failing when no registered work has its title."""
        if self.works.of(title) is None:
            raise ValueError(
                f"Reference {line!r} names {title!r}, which no registered work titles"
            )
        return Reference(text=line, relation=relation, work=title, locator=locator)

    def entry(self, line: str) -> Reference:
        """Return the reference one line states, or its attachment URL."""
        match = self.grammar.fullmatch(line)
        if match is None:
            raise ValueError(f"Reference {line!r} states neither a source nor a URL")
        if match["url"]:
            return Reference(url=line)
        relation = self.relations[match["relation"]]
        if match["work"] is not None:
            return self.cited(
                line,
                relation,
                title=match["work"],
                locator=match["locator"] or "",
            )
        return self.named(line, relation, match["tool"], match["identity"].split())

    def identify(
        self,
        *,
        tool: str,
        code_pattern: str,
        tokens: list[str],
    ) -> UpstreamRule | None:
        """Return the exact identity spelled by the tokens after a tool name."""
        codes = [token for token in tokens if code_pattern and re.fullmatch(code_pattern, token)]
        symbols = [
            token for token in tokens if token not in codes and self.symbols.fullmatch(token)
        ]
        if (
            not tokens
            or len(codes) > 1
            or len(symbols) > 1
            or len(codes) + len(symbols) != len(tokens)
        ):
            return None
        return UpstreamRule(
            tool=tool,
            code=next(iter(codes), ""),
            symbol=next(iter(symbols), ""),
        )

    def named(self, line: str, relation: Relation, tool: str, tokens: list[str]) -> Reference:
        """Return a tool rule reference, failing when it names no rule."""
        profile = self.tools.of(tool)
        upstream = (
            self.identify(tool=profile.name, code_pattern=profile.codes, tokens=tokens)
            if profile
            else None
        )
        if upstream is None:
            raise ValueError(f"Reference {line!r} opens on {relation.word} without naming a rule")
        return Reference(text=line, relation=relation, upstream=upstream)

    def parse(self, lines: Sequence[str]) -> list[Reference]:
        """Return one entry per reference, each carrying the URL written beneath it."""
        entries: list[Reference] = []
        for line in lines:
            entry = self.entry(line)
            if entry.url and not entry.text:
                if not entries:
                    raise ValueError(f"Reference {line!r} is a URL with no reference above it")
                entry = entries.pop().with_url(entry.url)
            entries.append(entry)
        return entries
