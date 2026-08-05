import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    MemberDeclaration,
    OverrideFact,
    ParameterDeclaration,
    ParameterKind,
    SourceSpan,
)
from mcmr.plugins import fact_table
from mcmr.project import locate
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.table import AnalysisSession

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Literal

_ROOT = Path(__file__).parents[2]

needs_kernel = pytest.mark.skipif(
    not locate(_ROOT).exists(),
    reason="the differential oracle needs the kernel binary this checkout builds",
)


def table_value(
    rule: RuleContract,
    subject: OverrideFact,
    **settings: RuleSetting,
) -> RuleValue:
    """Run one override rule once over one in-memory typed table."""
    table = fact_table(OverrideFact, [subject])
    result = rule.invoke_table(table, settings=settings, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic override rule returned a model query")
    return scalar_frame_value(result.values.collect())


def member(
    name: str,
    *parameters: str,
    decorators: tuple[str, ...] = (),
    kind: Literal["method", "async", "data"] = "method",
) -> MemberDeclaration:
    """Build one member exactly as the class holding it would write it down.

    Each parameter is spelled the way Python spells it, so `path`, `path=1`, `*rest`, `**extra`,
    and the bare `/` and `*` separators mean here what they mean in a real signature.
    """
    return MemberDeclaration(
        name=name,
        parameters=None if kind == "data" else spelled(parameters),
        decorators=list(decorators),
        asynchronous=kind == "async",
    )


def spelled(parameters: Sequence[str]) -> list[ParameterDeclaration]:
    """Read one signature spelled the way Python spells it into the parameters it states."""
    kind = ParameterKind.POSITIONAL_OR_KEYWORD
    stated: list[ParameterDeclaration] = []
    for item in parameters:
        if item == "/":
            stated = [
                held.model_copy(update={"kind": ParameterKind.POSITIONAL_ONLY}) for held in stated
            ]
        elif item == "*":
            kind = ParameterKind.KEYWORD_ONLY
        elif item.startswith("**"):
            stated.append(
                ParameterDeclaration(name=item.removeprefix("**"), kind=ParameterKind.VAR_KEYWORD)
            )
        elif item.startswith("*"):
            stated.append(
                ParameterDeclaration(
                    name=item.removeprefix("*"), kind=ParameterKind.VAR_POSITIONAL
                )
            )
            kind = ParameterKind.KEYWORD_ONLY
        else:
            named, _, default = item.partition("=")
            stated.append(ParameterDeclaration(name=named, kind=kind, has_default=bool(default)))
    return stated


def link(
    *,
    depth: int = 1,
    base: str = "pkg.Base",
    base_decorators: tuple[str, ...] = (),
    base_names: tuple[str, ...] = ("Base",),
    ancestor_names: tuple[str, ...] = ("Base",),
    declared: tuple[MemberDeclaration, ...] = (),
    inherited: tuple[MemberDeclaration, ...] = (),
    initializer_calls: tuple[str, ...] = (),
) -> OverrideFact:
    """Build one inheritance link in the shape the analysis kernel states it."""
    return OverrideFact(
        key=f"override:pkg.Child:{base}",
        span=SourceSpan(path="pkg/example.py"),
        derived="pkg.Child",
        base=base,
        depth=depth,
        base_decorators=list(base_decorators),
        base_names=list(base_names),
        ancestor_names=list(ancestor_names),
        declared=list(declared),
        inherited=list(inherited),
        initializer_calls=list(initializer_calls),
    )


def pylint_findings(root: Path, symbol: str) -> dict[str, int]:
    """Return how many times Pylint reports one message, keyed by the class it names."""
    completed = subprocess.run(
        [
            "python",
            "-m",
            "pylint",
            "--disable=all",
            f"--enable={symbol}",
            "--output-format=json2",
            "--score=n",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(completed.stdout or '{"messages": []}')
    found: dict[str, int] = {}
    for item in report["messages"]:
        named = str(item["obj"]).split(".")[0]
        found[named] = found.get(named, 0) + 1
    return found


def mcmr_findings(root: Path, rule_id: str) -> dict[str, int]:
    """Return what one MCMR rule reports over the same tree, keyed by the subclass it names."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    definition = next(item for item in catalog.definitions if item.id == rule_id)
    rule = next(item for item in catalog.rules if item.callable_path == definition.callable)
    table = AnalysisSession(
        root,
        suffixes=[".py"],
        typed_families=[OverrideFact],
    ).table(OverrideFact)
    outcome = rule.invoke_table(table, settings={}, dependencies={})
    if not isinstance(outcome, RuleQuery):
        raise TypeError("a deterministic override rule returned a model query")
    found: dict[str, int] = {}
    for row in outcome.values.collect().iter_rows(named=True):
        value = row["integer_value"]
        if value is None and isinstance(row["boolean_value"], bool):
            value = int(row["boolean_value"])
        assert isinstance(value, int)
        if value:
            fact_id = row["fact_id"]
            assert isinstance(fact_id, str)
            named = fact_id.split(":", 2)[1].rsplit(".", 1)[-1]
            found[named] = found.get(named, 0) + value
    return found


def written(root: Path, name: str, *, source: str) -> Path:
    """Write one generated module and return the directory holding it."""
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(source)
    return root
