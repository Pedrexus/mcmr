import json
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from mcmr.cli import allowance, globs, judgment
from mcmr.cli import snapshot as snapshot_command
from mcmr.models import RuleDefinition, RuleDocumentation, RuleScope
from mcmr.policy import Boolean, Category, Numeric, Policy, Verdict, standard
from mcmr.runs import (
    FailingSite,
    GitIdentity,
    RuleRecord,
    RunIdentity,
    RunRecord,
    RunStats,
    RunStore,
    allowed,
    contract,
    section,
    stated,
)
from tests.conftest import BINARY, needs_kernel

if TYPE_CHECKING:
    from pathlib import Path

moments = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=st.just(UTC),
)
values = st.one_of(
    st.booleans(),
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    st.text(max_size=20),
)
policies = st.one_of(
    st.none(),
    st.builds(Boolean, expected=st.booleans()),
    st.builds(
        Numeric,
        minimum=st.none() | st.floats(allow_nan=False, allow_infinity=False, width=32),
        maximum=st.none() | st.floats(allow_nan=False, allow_infinity=False, width=32),
    ),
    st.builds(Category, accepted=st.frozensets(st.text(min_size=1, max_size=8), min_size=1)),
)
rule_records = st.builds(
    RuleRecord,
    rule=st.text(min_size=1, max_size=12),
    contract=st.text(alphabet="0123456789abcdef", min_size=16, max_size=16),
    policy=policies,
    observations=st.integers(min_value=0, max_value=500),
    unassessed=st.integers(min_value=0, max_value=500),
    failing=st.lists(
        st.builds(FailingSite, fact=st.text(min_size=1, max_size=20), value=values), max_size=6
    ).map(tuple),
)
identities = st.builds(
    RunIdentity,
    taken_at=moments.map(lambda moment: f"{moment.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z"),
    commit=st.text(alphabet="0123456789abcdef", max_size=40),
    branch=st.text(max_size=12),
    is_dirty=st.booleans(),
)
run_records = st.builds(
    RunRecord,
    profile=st.sampled_from(["relaxed", "standard", "strict"]),
    identity=identities,
    stats=st.builds(
        RunStats,
        file_count=st.integers(min_value=0, max_value=9999),
        fact_count=st.integers(min_value=0, max_value=9999),
        invocation_count=st.integers(min_value=0, max_value=9999),
    ),
    rules=st.lists(rule_records, max_size=6).map(tuple),
)


def definition(identifier: str, output: str = "int", unit: str = "count") -> RuleDefinition:
    """Build one rule definition with only the fields a record fingerprints."""
    return RuleDefinition(
        id=identifier,
        callable=f"mcmr.rules.general.deterministic.demo.r0001.{identifier.lower()}",
        scope=RuleScope.GENERAL,
        lane="deterministic",
        family="demo",
        fact="ModuleFact",
        output=output,
        unit=unit,
        documentation=RuleDocumentation(summary="", definition="", examples=""),
    )


def record(*rules: RuleRecord, profile: str = "standard", commit: str = "abc1234") -> RunRecord:
    """Build one run record over the rules a test cares about."""
    return RunRecord(
        profile=profile,
        identity=RunIdentity(taken_at="2026-07-26T00:00:00Z", commit=commit, branch="main"),
        stats=RunStats(file_count=3, fact_count=9, invocation_count=12),
        rules=rules,
    )


def rule(
    identifier: str,
    *failing: tuple[str, int],
    contract_digest: str = "0000000000000000",
    policy: Policy | None = None,
) -> RuleRecord:
    """Build one rule record failing at the named sites."""
    return RuleRecord(
        rule=identifier,
        contract=contract_digest,
        policy=stated(policy or Numeric(maximum=0)),
        observations=4,
        unassessed=1,
        failing=tuple(FailingSite(fact=site, value=value) for site, value in failing),
    )


def repository(root: Path) -> Path:
    """Write one small package under version control, and return its root."""
    package = root / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "store.py").write_text(
        '"""Store."""\n\n\ndef load():\n    """Load."""\n    return 1\n'
    )
    (package / "engine.py").write_text(
        '"""Engine."""\n\nfrom .store import load\n\n\n'
        'def run():\n    """Run."""\n    return load()\n'
    )
    for arguments in (
        ("init", "-q"),
        ("config", "user.email", "runs@example.test"),
        ("config", "user.name", "runs"),
        ("add", "-A"),
        ("commit", "-qm", "first"),
    ):
        subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)
    return root


@settings(max_examples=40, deadline=None)
@given(run_records)
def test_a_record_written_to_the_store_reads_back_exactly_as_it_was_written(
    tmp_path_factory: pytest.TempPathFactory, subject: RunRecord
) -> None:
    """A store nobody can trust to return what it took is not a baseline, it is a rumor."""
    store = RunStore(directory=tmp_path_factory.mktemp("store"))

    assert store.read(store.write(subject)) == subject


@settings(max_examples=40, deadline=None)
@given(run_records)
def test_writing_one_record_twice_produces_the_same_bytes(
    tmp_path_factory: pytest.TempPathFactory, subject: RunRecord
) -> None:
    """A store a reader diffs across commits has to hold still when nothing moved."""
    directories = [tmp_path_factory.mktemp("stable") for _ in range(2)]
    written = [RunStore(directory=directory).write(subject) for directory in directories]

    assert written[0].read_text() == written[1].read_text()
    assert written[0].name == written[1].name


def test_a_record_this_release_cannot_read_is_refused_rather_than_reinterpreted(
    tmp_path: Path,
) -> None:
    """A field that used to mean something else is worse than a file that will not open."""
    store = RunStore(directory=tmp_path)
    path = store.write(record(rule("ALL-DEMO0001")))
    payload = json.loads(path.read_text())
    payload["version"] = 2
    path.write_text(json.dumps(payload))

    with pytest.raises(ValidationError):
        store.read(path)


def test_the_store_returns_the_runs_in_the_order_they_happened(tmp_path: Path) -> None:
    """A series is only a series in order, and an empty store is not an error."""
    store = RunStore(directory=tmp_path)
    later = record(rule("ALL-DEMO0001"))
    earlier = later.model_copy(
        update={
            "identity": RunIdentity(taken_at="2026-07-25T00:00:00Z", commit="9999999"),
            "profile": "strict",
        }
    )

    assert store.records() == ()
    assert store.latest("standard") is None

    store.write(later)
    store.write(earlier)

    assert [item.identity.taken_at for item in store.records()] == [
        "2026-07-25T00:00:00Z",
        "2026-07-26T00:00:00Z",
    ]
    assert store.latest("standard") == later
    assert store.latest("relaxed") is None


def test_a_run_says_how_much_of_the_repository_failed_and_which_rules_judged_it() -> None:
    """The counts a report leads with come off the record rather than off a second traversal."""
    subject = record(
        rule("ALL-DEMO0001", ("a.py", 3), ("b.py", 4)),
        rule("ALL-DEMO0002"),
    )

    assert subject.failing_count == 2
    assert subject.failing_rule_count == 1
    assert subject.unassessed_count == 2
    assert set(subject.index()) == {"ALL-DEMO0001", "ALL-DEMO0002"}
    assert {site: held.value for site, held in subject.rules[0].sites.items()} == {
        "a.py": 3,
        "b.py": 4,
    }


def test_the_catalog_fingerprint_ignores_the_order_the_rules_arrive_in() -> None:
    """Two runs holding the same catalog have to agree, whichever way the file lists it."""
    first = record(rule("ALL-DEMO0001"), rule("ALL-DEMO0002"))
    second = record(rule("ALL-DEMO0002"), rule("ALL-DEMO0001"))
    moved = record(rule("ALL-DEMO0001"), rule("ALL-DEMO0002", contract_digest="ffffffffffffffff"))

    assert first.catalog == second.catalog
    assert first.catalog != moved.catalog


def test_a_rule_fingerprint_moves_when_the_bar_moves_and_not_when_a_set_is_rehashed() -> None:
    """A profile that tightened is measuring something else, and a set has no order to speak of."""
    tightened = rule("ALL-DEMO0001", policy=Numeric(maximum=5))
    loosened = rule("ALL-DEMO0001", policy=Numeric(maximum=50))
    accepted = rule("ALL-DEMO0001", policy=Category(accepted=frozenset({"a", "b", "c"})))
    reordered = rule("ALL-DEMO0001", policy=Category(accepted=frozenset({"c", "b", "a"})))
    unjudged = rule("ALL-DEMO0001", policy=None)

    assert tightened.judgment != loosened.judgment
    assert accepted.judgment == reordered.judgment
    assert unjudged.judgment != tightened.judgment


def test_a_set_of_accepted_categories_is_written_in_one_order(tmp_path: Path) -> None:
    """A record two runs are diffed through cannot depend on how this process hashed a string."""
    store = RunStore(directory=tmp_path)
    subject = record(rule("ALL-DEMO0001", policy=Category(accepted=frozenset({"c", "a", "b"}))))

    written = json.loads(store.write(subject).read_text())

    assert written["rules"][0]["policy"]["accepted"] == ["a", "b", "c"]
    assert store.read(store.write(subject)) == subject


def test_the_contract_fingerprint_follows_what_a_rule_measures() -> None:
    """A rewritten docstring leaves two runs comparable, and a new result shape does not."""
    counted = definition("ALL-DEMO0001")
    measured = definition("ALL-DEMO0001", output="float", unit="percentage")
    documented = counted.model_copy(
        update={
            "documentation": RuleDocumentation(
                summary="reworded", definition="reworded", examples="reworded"
            )
        }
    )
    configured = counted.model_copy(update={"settings": {"minimum_lines": "40"}})

    assert contract(counted) == contract(documented)
    assert contract(counted) != contract(measured)
    assert contract(counted) != contract(configured)


def test_a_policy_shape_a_record_cannot_carry_is_refused_rather_than_dropped() -> None:
    """Recording a judged rule as unjudged would be a lie a later comparison would repeat."""

    class Always(Policy):
        """Accept anything, which is a shape this release does not ship."""

        def verdict(self, value: bool | int | float | str) -> Verdict:
            """Return that everything passes."""
            return Verdict.PASS

    assert stated(None) is None
    assert stated(Numeric(maximum=1)) == Numeric(maximum=1)
    with pytest.raises(TypeError):
        stated(Always())


def test_a_report_renders_what_the_profile_accepts_for_every_policy_shape() -> None:
    """A failure only reads as a failure beside the allowance it broke."""
    assert allowed(Numeric(maximum=500)) == "<= 500"
    assert allowed(Numeric(minimum=80.0)) == ">= 80"
    assert allowed(Numeric(minimum=1, maximum=3)) == "1..3"
    assert allowed(Boolean()) == "False"
    assert allowed(Category(accepted=frozenset({"cohesive", "layered"}))) == "cohesive, layered"
    assert allowed(None) == ""
    assert allowance(standard(), definition("ALL-MODU0001")) == "<= 500"


def test_a_bounded_section_states_its_own_count_and_its_own_truncation() -> None:
    """A block that quietly dropped half its entries would read as good news."""
    assert section("Regressed", [], 3) == ["", "Regressed (0)"]
    assert section("Regressed", ["a", "b"], 3) == ["", "Regressed (2)", "  a", "  b"]
    assert section("Regressed", ["a", "b", "c"], 2) == [
        "",
        "Regressed (3)",
        "  a",
        "  b",
        "  and 1 more",
    ]


def test_a_run_names_the_commit_it_judged_and_says_when_the_tree_was_not_clean(
    tmp_path: Path,
) -> None:
    """A commit alone would name source that was never judged, so a dirty tree is marked."""
    root = repository(tmp_path / "checkout")
    moment = datetime(2026, 7, 26, 6, 30, 12, 999, tzinfo=UTC)

    clean = GitIdentity(root=root).read(moment)
    (root / "pkg" / "store.py").write_text('"""Store."""\n')
    dirty = GitIdentity(root=root).read(moment)

    assert clean.taken_at == "2026-07-26T06:30:12.000Z"
    assert len(clean.commit) == 40
    assert clean.branch in {"main", "master"}
    assert clean.is_dirty is False
    assert clean.label == f"{clean.commit[:7]}"
    assert dirty.is_dirty is True
    assert dirty.label == f"{clean.commit[:7]}*"


def test_a_tree_outside_version_control_still_records_a_run(tmp_path: Path) -> None:
    """Refusing to snapshot a real tree would be a worse answer than an honest blank."""
    identity = GitIdentity(root=tmp_path).read(datetime(2026, 7, 26, tzinfo=UTC))

    assert identity.commit == ""
    assert identity.branch == ""
    assert identity.label == "untracked"


def test_the_commit_agrees_with_the_archy_oracle_on_the_same_checkout(tmp_path: Path) -> None:
    """Archy records the same two facts about a checkout, so its answer is the one MCMR owes."""
    root = repository(tmp_path / "checkout")
    ours = GitIdentity(root=root).read(datetime(2026, 7, 26, tzinfo=UTC))
    theirs = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert ours.commit == theirs.stdout.strip()


@needs_kernel
def test_a_snapshot_records_every_selected_rule_and_not_only_the_ones_that_failed(
    tmp_path: Path,
) -> None:
    """A rule the baseline held is exactly what tells a new rule apart from a regression."""
    root = repository(tmp_path / "checkout")
    judged = judgment(root, "standard", "", "", "", BINARY).run()

    subject = judged.record(GitIdentity(root=root).read(datetime(2026, 7, 26, tzinfo=UTC)))

    assert len(subject.rules) == len(judged.selection)
    assert subject.profile == "standard"
    assert subject.stats.file_count == 3
    assert subject.stats.invocation_count == judged.engine.invocation_count
    assert [item.rule for item in subject.rules] == sorted(item.rule for item in subject.rules)
    assert judged.unassessed_count == subject.unassessed_count
    assert len(judged.failures) == subject.failing_count


@needs_kernel
def test_two_snapshots_of_one_unchanged_tree_record_the_same_judgment(tmp_path: Path) -> None:
    """A baseline that moved on its own would report every later run as a regression."""
    root = repository(tmp_path / "checkout")
    identity = GitIdentity(root=root).read(datetime(2026, 7, 26, tzinfo=UTC))
    runs = [
        judgment(root, "standard", "", "", "", BINARY).run().record(identity) for _ in range(2)
    ]

    assert runs[0] == runs[1]
    assert runs[0].model_dump_json() == runs[1].model_dump_json()


@needs_kernel
def test_the_snapshot_command_writes_to_the_store_or_to_a_named_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mcmr snapshot` is how a project states the baseline it wants to be held to."""
    root = repository(tmp_path / "checkout")

    snapshot_command(root, kernel=BINARY, select="imports.r0003")
    assert "recorded 1 rules" in capsys.readouterr().out
    assert len(list((root / ".mcmr" / "runs").glob("*.json"))) == 1

    named = tmp_path / "elsewhere" / "baseline.json"
    snapshot_command(root, kernel=BINARY, select="imports.r0003", output=named)

    assert str(named) in capsys.readouterr().out
    assert RunStore(directory=tmp_path).read(named).profile == "standard"


def test_the_extra_patterns_a_command_skips_are_read_the_same_way_everywhere() -> None:
    """Every command taking an exclusion reads the same comma separated list."""
    assert globs("") == ()
    assert globs(" **/a/**, **/b/** ,") == ("**/a/**", "**/b/**")
