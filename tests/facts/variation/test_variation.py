from typing import TYPE_CHECKING

import pytest

from mcmr.kernel import Kernel, buildable

from ...support import kernel_binary, needs_kernel, project_root, written
from .corpus import fixture_files, manifestless_files
from .support import collect, invariant_reasons, unfilled_reasons, unmoved

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the second project of the corpus, which states what this repository does not."""
    return written(tmp_path_factory.mktemp("variation"), fixture_files())


@pytest.fixture(scope="module")
def manifestless_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the third project of the corpus, which declares nothing about itself."""
    return written(tmp_path_factory.mktemp("manifestless"), manifestless_files())


@pytest.fixture(scope="module")
def observed(fixture_root: Path) -> dict[str, set[str]]:
    """Return every distinct value each fact field took across the whole corpus."""
    seen: dict[str, set[str]] = {}
    for root in (project_root(), fixture_root):
        collect(root, seen)
    return seen


@needs_kernel
def test_no_provider_states_the_same_thing_forever_without_a_recorded_reason(
    observed: Mapping[str, set[str]],
) -> None:
    """A field one corpus never moves is either invariant or fabricated, and which one is a claim.

    A provider writing a literal is indistinguishable from a provider deriving a value that
    happens to agree, right up until a rule reads it and answers the same thing forever. So the
    ledger fails in both directions. A newly constant field has to be written down with its reason,
    and a field that starts varying has to have its entry taken out, because an entry nobody
    removed is the stale allowance a reader would trust.
    """
    assert sorted(unmoved(observed) - set(invariant_reasons())) == []
    assert sorted(set(invariant_reasons()) - unmoved(observed)) == []


@needs_kernel
def test_no_family_answers_nothing_without_a_recorded_reason(
    observed: Mapping[str, set[str]],
) -> None:
    """A family nothing fills is a rule reading an empty stream, which reads as a clean repository.

    That is the same defect one level up, so it is recorded the same way and held to the same
    ledger from both sides.
    """
    silent = {
        name for name in buildable() if not any(path.startswith(f"{name}.") for path in observed)
    }

    assert sorted(silent - set(unfilled_reasons())) == []
    assert sorted(set(unfilled_reasons()) - silent) == []


def test_every_recorded_entry_names_something_real_and_says_why() -> None:
    """The ledger cannot record a field no family declares, and cannot record one without a reason.

    Without this the tables only grow, and an entry naming a field somebody renamed would keep
    excusing a field that no longer exists.
    """
    families = set(buildable())

    assert set(unfilled_reasons()) <= families
    assert {path.split(".")[0] for path in invariant_reasons()} <= families
    assert all(reason for reason in {**unfilled_reasons(), **invariant_reasons()}.values())


@needs_kernel
@pytest.mark.parametrize("corpus", ["fixture_root", "manifestless_root"])
def test_every_fact_names_a_place_the_repository_holds(
    corpus: str, request: pytest.FixtureRequest
) -> None:
    """A fact pointing at a file nobody wrote is the fabrication defect one level up.

    The ledger asks whether a field ever moved, which cannot see a whole fact that had no evidence
    behind it. A location can be checked directly, and it is the same claim in both directions. A
    repository declaring no manifest gets no manifest facts, and a repository declaring one gets
    facts at the file it declared. Without the third corpus the first half of that never runs,
    since every project the ledger reads carries a manifest.
    """
    root = request.getfixturevalue(corpus)
    families = buildable()
    workspace = Kernel(binary=kernel_binary(), root=root).build(sorted(families), families)
    stated = {fact.span.path for family in families.values() for fact in workspace.stream(family)}

    assert stated
    assert sorted(path for path in stated if not (root / path).exists()) == []
