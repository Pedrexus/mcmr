from pathlib import Path

from mcmr.accounting.upstream import ClaimIndex, Coverage, ToolCoverage
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery

from ..support import mcmr_findings, needs_kernel, pylint_findings, written
from .fixtures import initializers, positions, promises, protocols, sealed, signatures


@needs_kernel
def test_arguments_differ_names_every_class_pylint_names(tmp_path: Path) -> None:
    """Both readers report a changed count, a changed keyword, and a swallowing tail dropped.

    The fixture states each shape once, including the two that need the parameter kinds and the
    defaults the graph now records, so a narrowing, a widening, an added required keyword, a
    dropped keyword, a renamed keyword, and a lost variadic all land on the same classes here as
    they do in Pylint.
    """
    root = written(tmp_path, "generated.py", source=signatures())

    oracle = pylint_findings(root, "arguments-differ")
    ours = mcmr_findings(root, "ALL-OVER0001")

    assert oracle == {
        "Narrowed": 1,
        "Widened": 1,
        "StarLost": 1,
        "KwargsLost": 1,
        "KwonlyAdder": 1,
        "KwonlyGone": 1,
        "KwonlyRenamer": 1,
        "MixedChange": 1,
        "Leaf": 1,
    }
    assert ours == oracle


@needs_kernel
def test_arguments_renamed_counts_the_same_moved_positions_pylint_counts(tmp_path: Path) -> None:
    """One message per position that changed name, which makes a transposition two of them.

    MCMR used to separate the rename from the reordering and only matched Pylint as a union of two
    rules. Counting positions rather than overrides is what closes it, and a reordering is now
    what it always was, which is two names that swapped places.
    """
    root = written(tmp_path, "generated.py", source=signatures())

    oracle = pylint_findings(root, "arguments-renamed")
    ours = mcmr_findings(root, "ALL-OVER0002")

    assert oracle == {"Renamer": 1, "Reorderer": 2, "MixedChange": 2, "StaticRenamer": 1}
    assert ours == oracle


@needs_kernel
def test_signature_differs_names_the_override_that_withdrew_a_default(tmp_path: Path) -> None:
    """The two readings met once the graph started recording which parameters carry a default.

    This rule used to answer a question of its own, a transposition, and was disjoint from Pylint
    by construction. It now answers what Pylint answers, which is an optional argument the
    override made required while changing nothing else.
    """
    root = written(tmp_path, "generated.py", source=signatures())

    oracle = pylint_findings(root, "signature-differs")
    ours = mcmr_findings(root, "ALL-OVER0003")

    assert oracle == {"Requirer": 1}
    assert ours == oracle


@needs_kernel
def test_a_dropped_positional_only_argument_is_reported_here_and_not_by_pylint(
    tmp_path: Path,
) -> None:
    """The one place these two readers part, and it is a gap in the oracle rather than in MCMR.

    Pylint reaches its positional comparison through the list of ordinary parameters its own
    parser builds, and a positional-only parameter is kept in a separate list that the comparison
    never opens. An override that drops one therefore breaks every caller in silence there. MCMR
    counts the slot, which is what a caller has to fill, and leaves the name alone, which is what
    no caller can pass, so the renaming and the withdrawn default still agree exactly.
    """
    root = written(tmp_path, "generated.py", source=positions())

    assert pylint_findings(root, "arguments-differ") == {}
    assert mcmr_findings(root, "ALL-OVER0001") == {"SlotDropper": 1}
    assert mcmr_findings(root, "ALL-OVER0002") == pylint_findings(root, "arguments-renamed") == {}
    assert (
        mcmr_findings(root, "ALL-OVER0003")
        == pylint_findings(root, "signature-differs")
        == {"SlotRequirer": 1}
    )


@needs_kernel
def test_a_changed_call_protocol_names_the_same_classes_pylint_names(tmp_path: Path) -> None:
    """Pylint splits the property half from the async half, so one method can cost two messages."""
    root = written(tmp_path, "generated.py", source=protocols())

    oracle = pylint_findings(root, "invalid-overridden-method")
    ours = mcmr_findings(root, "ALL-OVER0004")

    assert oracle == {"Deviant": 3}
    assert ours == oracle


@needs_kernel
def test_a_sealed_member_and_a_sealed_class_agree_with_pylint(tmp_path: Path) -> None:
    """Both markers are read from the decorator, which is what Pylint reads too."""
    members = written(tmp_path / "members", "generated.py", source=protocols())
    classes = written(tmp_path / "classes", "generated.py", source=sealed())

    assert mcmr_findings(members, "ALL-OVER0008") == pylint_findings(
        members, "overridden-final-method"
    )
    assert mcmr_findings(members, "ALL-OVER0008") == {"Deviant": 1}
    assert mcmr_findings(classes, "ALL-OVER0009") == pylint_findings(
        classes, "subclassed-final-class"
    )
    assert mcmr_findings(classes, "ALL-OVER0009") == {"Discount": 1}


@needs_kernel
def test_a_hidden_method_agrees_with_pylint_where_the_hiding_is_inherited(tmp_path: Path) -> None:
    """The inherited half is the half an inheritance graph owns, and it matches exactly."""
    root = written(tmp_path, "generated.py", source=protocols())

    oracle = pylint_findings(root, "method-hidden")
    ours = mcmr_findings(root, "ALL-OVER0010")

    assert oracle == {"Deviant": 1}
    assert ours == oracle


@needs_kernel
def test_both_initializer_messages_agree_with_pylint(tmp_path: Path) -> None:
    """A skipped base and a borrowed constructor are both read from resolved call edges."""
    root = written(tmp_path, "generated.py", source=initializers())

    skipped = pylint_findings(root, "super-init-not-called")
    strangers = pylint_findings(root, "non-parent-init-called")

    assert skipped == {"Pooled": 1, "Borrower": 1}
    assert mcmr_findings(root, "ALL-OVER0006") == skipped
    assert strangers == {"Borrower": 1}
    assert mcmr_findings(root, "ALL-OVER0007") == strangers


@needs_kernel
def test_an_unkept_promise_agrees_with_pylint_including_what_it_declines_to_report(
    tmp_path: Path,
) -> None:
    """Pylint treats anything under `ABC` as abstract itself, and so does MCMR."""
    root = written(tmp_path, "generated.py", source=promises())

    oracle = pylint_findings(root, "abstract-method")
    ours = mcmr_findings(root, "ALL-OVER0005")

    assert oracle == {"Concrete": 1}
    assert ours == oracle


@needs_kernel
def test_every_override_message_the_ledger_claims_has_a_case_behind_it() -> None:
    """A claim with no measurement behind it is an assertion, which is what the ledger is not.

    Counting the names written here proved only that ten names were written here. What the claim
    needs is that the ledger's own native Pylint messages for this family are exactly the ones a
    differential case above measures, so adding a claim without a case turns this red.
    """
    exercised = {
        "arguments-differ",
        "arguments-renamed",
        "signature-differs",
        "invalid-overridden-method",
        "abstract-method",
        "super-init-not-called",
        "non-parent-init-called",
        "overridden-final-method",
        "subclassed-final-class",
        "method-hidden",
    }
    definitions = list(Catalog(modules=RuleModuleDiscovery().modules).definitions)
    identifiers = {definition.id for definition in definitions}
    account = ToolCoverage(tool="pylint", claims=ClaimIndex(definitions=definitions))
    claimed = {
        entry.rule.symbol
        for entry in account.entries
        if entry.coverage is Coverage.NATIVE
        and any(named.startswith("ALL-OVER") for named in entry.rules)
    }

    assert {f"ALL-OVER{number:04d}" for number in range(1, 11)} <= identifiers
    assert claimed == exercised
