from typing import TYPE_CHECKING

from mcmr.domain.contracts import RuleContract, RuleValue
from mcmr.facts import InteropFact, InteropMechanism, InteropReference, SourceSpan
from mcmr.kernel import Kernel
from mcmr.plugins import fact_table
from mcmr.query import RuleQuery, scalar_frame_value
from mcmr.rules.general import cross_language_boundary_width, unreached_cross_language_artifact

from ..support import kernel_binary, needs_kernel, written

if TYPE_CHECKING:
    from pathlib import Path


def artifact(
    *languages: str,
    declared: str = "rust",
    mechanism: InteropMechanism = InteropMechanism.BINARY,
) -> InteropFact:
    """Build one declared artifact and the languages that name it."""
    return InteropFact(
        key=f"interop:{mechanism}:kernel",
        span=SourceSpan(path="kernel/Cargo.toml"),
        name="kernel",
        mechanism=mechanism,
        declared_language=declared,
        references=[
            InteropReference(path=f"{language}/caller", language=language)
            for language in languages
        ],
    )


def value(rule: RuleContract, subject: InteropFact) -> RuleValue:
    """Run one binding rule once over one in-memory typed table."""
    table = fact_table(InteropFact, [subject])
    result = rule.invoke_table(table, settings={}, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic binding rule returned a model query")
    return scalar_frame_value(result.values.collect())


def test_an_artifact_only_its_own_language_names_is_reported() -> None:
    """A seam with one side wired is dead weight that still has to be built and shipped."""
    assert value(unreached_cross_language_artifact, artifact("rust", "manifest")) is True
    assert value(unreached_cross_language_artifact, artifact("rust", "python")) is False
    assert value(unreached_cross_language_artifact, artifact()) is True


def test_a_console_script_is_not_a_seam_waiting_for_its_other_side() -> None:
    """An entry point names a callable its own language holds, so nobody else has to name it."""
    script = artifact(declared="python", mechanism=InteropMechanism.CONSOLE_SCRIPT)

    assert value(unreached_cross_language_artifact, script) is False
    assert value(cross_language_boundary_width, script) == 0


@needs_kernel
def test_a_project_shipping_its_own_command_is_left_alone(tmp_path: Path) -> None:
    """The defect this replaces reported every pure Python CLI as an unreached binary.

    A `project.scripts` entry whose target is the package's own module has no other side to wire,
    while the compiled kernel beside it still answers for whether Python ever spawns it.
    """
    root = written(
        tmp_path,
        {
            "pyproject.toml": (
                '[project]\nname = "shop"\n\n[project.scripts]\nshop = "shop.cli:app"\n'
            ),
            "src/core/Cargo.toml": '[[bin]]\nname = "shop-engine"\npath = "src/main.rs"\n',
            "shop/cli.py": "def app() -> int:\n    return 0\n",
        },
    )
    workspace = Kernel(binary=kernel_binary(), root=root).build(
        [InteropFact.__name__], {InteropFact.__name__: InteropFact}
    )
    declared = {fact.name: fact for fact in workspace.stream(InteropFact)}

    assert declared["shop"].mechanism is InteropMechanism.CONSOLE_SCRIPT
    assert value(unreached_cross_language_artifact, declared["shop"]) is False
    assert declared["shop-engine"].mechanism is InteropMechanism.BINARY
    assert value(unreached_cross_language_artifact, declared["shop-engine"]) is True


def test_the_width_of_a_seam_counts_only_the_languages_that_cross_it() -> None:
    """The declaring language and the manifests describing it are not crossings."""
    assert value(cross_language_boundary_width, artifact("rust", "manifest")) == 0
    assert value(cross_language_boundary_width, artifact("rust", "python", "manifest")) == 1
    assert value(cross_language_boundary_width, artifact("python", "cpp", "typescript")) == 3
