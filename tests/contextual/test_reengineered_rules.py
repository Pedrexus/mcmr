from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import JsonValue, TypeAdapter

if TYPE_CHECKING:
    import polars as pl

from mcmr.domain.contracts import RuleContract, RuleSetting
from mcmr.execution import ClassificationBackend, CodexBackend
from mcmr.execution.queries import ModelQuery
from mcmr.facts import (
    ClassFact,
    CommentFact,
    Fact,
    ModuleCouplingFact,
    ModuleFact,
    OverrideFact,
    ProseSegmentFact,
    SourceSpan,
)
from mcmr.rules.general import (
    comment_accuracy,
    comment_intent,
    comment_language,
    dependency_hub_quality,
    docstring_language,
    inheritance_design,
    mixed_class_responsibilities,
    module_cohesion,
    substitutability,
)
from mcmr.rules.python import model_foundation
from mcmr.table import AnalysisSession, Table, fact_table

type JsonObject = dict[str, JsonValue]


def candidates(
    rule: RuleContract,
    table: Table[Fact],
    **settings: RuleSetting,
) -> pl.DataFrame:
    """Return the lazy candidates one contextual rule admits without running its backend."""
    query = rule.invoke_table(
        table,
        settings=settings,
        dependencies={ClassificationBackend: CodexBackend()},
    )
    if not isinstance(query, ModelQuery):
        raise TypeError("a contextual rule returned a deterministic query")
    return query.candidates.collect()


def analyzed(
    root: Path,
    family: type[Fact],
    suffixes: list[str] | None = None,
) -> Table[Fact]:
    """Build one typed family from a real fixture project."""
    return AnalysisSession(
        root,
        suffixes=suffixes,
        typed_families=[family.__name__],
    ).table(family)


def subjects(frame: pl.DataFrame) -> list[JsonObject]:
    """Decode each retained candidate payload for exact evidence assertions."""
    adapter = TypeAdapter(JsonObject)
    return [adapter.validate_json(value) for value in frame.get_column("subject_json")]


def fields(subject: JsonObject) -> JsonObject:
    """Return one candidate's validated scalar field mapping."""
    return TypeAdapter(JsonObject).validate_python(subject["fields"])


def records(subject: JsonObject) -> list[JsonObject]:
    """Return one candidate's validated record list."""
    return TypeAdapter(list[JsonObject]).validate_python(subject["records"])


def text(record: JsonObject, name: str) -> str:
    """Return one required string from a normalized candidate row."""
    return TypeAdapter(str).validate_python(record[name])


def test_architecture_candidates_hold_exact_declarations_and_honor_size_settings(
    tmp_path: Path,
) -> None:
    """Architecture judgments receive one real entity after deterministic size routing."""
    source = """def price(order):
    return order.total


def render(order):
    return f"<p>{order.total}</p>"


def notify(order):
    return send_mail(order.owner)


def archive(order):
    return save(order)


class Checkout:
    def price(self, order):
        return order.total

    def render(self, order):
        return f"<p>{order.total}</p>"

    def notify(self, order):
        return send_mail(order.owner)

    def archive(self, order):
        return save(order)
"""
    (tmp_path / "mixed.py").write_text(source)
    module_table = analyzed(tmp_path, ModuleFact)
    class_table = analyzed(tmp_path, ClassFact)

    module_frame = candidates(module_cohesion, module_table)
    class_frame = candidates(mixed_class_responsibilities, class_table)
    module_records = records(subjects(module_frame)[0])
    class_fields = fields(subjects(class_frame)[0])
    class_records = records(subjects(class_frame)[0])

    assert (
        module_frame.height,
        [record["name"] for record in module_records],
        text(module_records[0], "source").startswith("def price"),
        class_frame.height,
        class_fields["name"],
        text(class_fields, "source").startswith("class Checkout"),
        text(class_records[1], "source").startswith("def render"),
        candidates(module_cohesion, module_table, minimum_members=6).is_empty(),
        candidates(
            mixed_class_responsibilities,
            class_table,
            minimum_methods=5,
        ).is_empty(),
    ) == (
        1,
        ["price", "render", "notify", "archive", "Checkout"],
        True,
        1,
        "Checkout",
        True,
        True,
        True,
        True,
    )


def test_dependency_hubs_are_real_high_degree_coupling_facts() -> None:
    """Nominate only comparable degree outliers and retain their graph measurements."""
    table = fact_table(
        ModuleCouplingFact,
        [
            ModuleCouplingFact(
                key=f"coupling:pkg.module_{degree}",
                span=SourceSpan(path=f"pkg/module_{degree}.py"),
                module=f"pkg.module_{degree}",
                afferent_count=degree,
            )
            for degree in range(10)
        ],
    )

    frame = candidates(dependency_hub_quality, table)

    assert frame.get_column("module").to_list() == ["pkg.module_8", "pkg.module_9"]
    assert [fields(subject)["afferent_count"] for subject in subjects(frame)] == [8, 9]


def test_comment_candidates_exclude_documentation_directives_code_and_fragments(
    tmp_path: Path,
) -> None:
    """Only substantive implementation prose reaches either comment judgment."""
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "comment-fixture"\nversion = "0.0.0"\nedition = "2024"\n'
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src/lib.rs").write_text(
        """/// Explain the public API.
pub fn run() {
    // Retry because the peer closes idle sockets.
    let retries = 3;

    // tiny
    let value = 1;

    // NOLINT
    let other = 2;

    // let disabled = true;
}
"""
    )
    table = analyzed(tmp_path, CommentFact, suffixes=[".rs"])

    intent, accuracy, language = (
        candidates(rule, table) for rule in (comment_intent, comment_accuracy, comment_language)
    )

    assert intent.height == accuracy.height == 1
    assert language.height == 2
    comment_fields = fields(subjects(intent)[0])
    assert comment_fields["text"] == ("Retry because the peer closes idle sockets.")
    assert comment_fields["following_source"] == ("    let retries = 3;\n\n    // tiny")


def test_docstring_language_candidates_are_precise_and_skip_short_text(tmp_path: Path) -> None:
    """Each substantial docstring reaches its own bounded contextual judgment."""
    (tmp_path / "reader.py").write_text(
        '''def read() -> str:
    """Return the decoded content while preserving its source encoding."""
    return "content"


def tiny() -> None:
    """No-op."""
'''
    )
    table = analyzed(tmp_path, ProseSegmentFact)

    frame = candidates(docstring_language, table)

    assert frame.height == 1
    assert frame.item(0, "path") == "reader.py"
    assert fields(subjects(frame)[0])["text"] == (
        "Return the decoded content while preserving its source encoding."
    )


def test_inheritance_candidates_hold_member_source_and_skip_links_without_a_question(
    tmp_path: Path,
) -> None:
    """Inheritance rules receive direct resolved links and substitutability needs an override."""
    (tmp_path / "models.py").write_text(
        """class Report:
    def render(self, width=80):
        return width


class HtmlReport(Report):
    def render(self, width=80):
        return f"<p>{width}</p>"


class EmptyReport(Report):
    def export(self):
        return None
"""
    )
    table = analyzed(tmp_path, OverrideFact)

    design = candidates(inheritance_design, table)
    contract = candidates(substitutability, table)
    contract_subject = subjects(contract)[0]

    assert design.height == 2
    assert contract.height == 1
    assert fields(contract_subject)["overridden_member_count"] == 1
    sources = {
        text(record, "source")
        for record in records(contract_subject)
        if record["relation"] in {"declared", "inherited"}
    }
    assert any(source.startswith("def render") for source in sources)


def test_model_foundation_skips_transitive_models_and_keeps_actionable_classes(
    tmp_path: Path,
) -> None:
    """Resolved model ancestry removes compliant classes before contextual classification."""
    (tmp_path / "bases.py").write_text(
        "from patos import FrozenModel\n\n\nclass Fact(FrozenModel):\n    pass\n"
    )
    (tmp_path / "records.py").write_text(
        """from dataclasses import dataclass
from pydantic import BaseModel

from bases import Fact


class Existing(Fact):
    name: str


@dataclass(frozen=True, slots=True)
class Legacy:
    name: str


class Bypass(BaseModel):
    name: str


class PlainRecord:
    def __init__(self, name: str):
        self.name = name
"""
    )
    frame = candidates(model_foundation, analyzed(tmp_path, ClassFact))
    names = {fields(subject)["name"] for subject in subjects(frame)}

    assert names == {"Legacy", "Bypass", "PlainRecord"}
    assert all(fields(subject)["source"] for subject in subjects(frame))
