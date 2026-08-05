import subprocess
from io import StringIO
from pathlib import Path
from shlex import quote
from typing import TYPE_CHECKING

import pytest

from mcmr.facts import ImportBindingFact, ModuleFact
from mcmr.kernel import (
    FamilyStream,
    Kernel,
    KernelClient,
    KernelExchange,
    KernelStats,
    KernelStreamBatch,
    Workspace,
)
from mcmr.project import locate
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery

if TYPE_CHECKING:
    from collections.abc import Sequence

_ROOT = Path(__file__).parents[2]
_BINARY = locate(_ROOT)
needs_kernel = pytest.mark.skipif(not _BINARY.exists(), reason="the analysis kernel is not built")


def streaming_stub(path: Path, payload: str, *, diagnostic: str = "", status: int = 0) -> Path:
    """Write one executable kernel stub with independent output and diagnostics."""
    commands = ["#!/bin/sh", "cat >/dev/null", f"printf %s {quote(payload)}"]
    if diagnostic:
        commands.append(f"printf %s {quote(diagnostic)} >&2")
    commands.append(f"exit {status}")
    path.write_text("\n".join(commands) + "\n")
    path.chmod(0o755)
    return path


@needs_kernel
def test_a_stale_protocol_version_is_refused(tmp_path: Path) -> None:
    """A kernel speaking another protocol fails loudly instead of feeding stale facts."""
    stub = streaming_stub(
        tmp_path / "stub",
        "H\t99\n",
    )
    rules = [
        rule
        for rule in Catalog(modules=RuleModuleDiscovery().modules).rules
        if rule.qualname == "unused_import"
    ]

    with pytest.raises(RuntimeError, match="protocol 99"):
        Kernel(binary=stub, root=tmp_path).run(rules)


@needs_kernel
def test_a_failing_kernel_reports_its_own_message(tmp_path: Path) -> None:
    """The kernel's diagnostic reaches the caller rather than an empty workspace."""
    stub = tmp_path / "stub"
    stub.write_text("#!/bin/sh\necho 'the root does not exist' >&2\nexit 1\n")
    stub.chmod(0o755)
    rules = [
        rule
        for rule in Catalog(modules=RuleModuleDiscovery().modules).rules
        if rule.qualname == "unused_import"
    ]

    with pytest.raises(RuntimeError, match="the root does not exist"):
        Kernel(binary=stub, root=tmp_path).run(rules)


def test_streamed_facts_arrive_in_typed_batches_and_empty_families_stay_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A consumer can release one directory while an empty provider still counts as reached."""
    records = (
        KernelStreamBatch(
            family="ModuleFact",
            payload='[{"key":"module:a/one.py","span":{"path":"a/one.py"}}]\n',
        ),
        KernelStreamBatch(
            family="ModuleFact",
            payload='[{"key":"module:b/two.py","span":{"path":"b/two.py"}}]\n',
        ),
        KernelStreamBatch(
            family="ModuleFact",
            payload="[]\n",
        ),
        KernelStats(file_count=2),
    )
    monkeypatch.setattr(KernelClient, "stream", lambda self, request: iter(records))

    streamed = list(
        Kernel(binary=Path("unused"), root=Path()).build_streams(
            ["ModuleFact"], {"ModuleFact": ModuleFact}
        )
    )

    batches = [item for item in streamed if isinstance(item, FamilyStream)]
    assert [[fact.key for fact in batch.facts] for batch in batches] == [
        ["module:a/one.py"],
        ["module:b/two.py"],
        [],
    ]
    stats = streamed[-1]
    assert isinstance(stats, KernelStats)
    assert stats.file_count == 2
    assert stats.total_nanoseconds > 0


@pytest.mark.parametrize(
    ("records", "message"),
    [
        ((KernelStats(),), "omitted fact families"),
        (
            (
                KernelStreamBatch(
                    family="UnexpectedFact",
                    payload="[]\n",
                ),
                KernelStats(),
            ),
            "unexpected fact family",
        ),
    ],
)
def test_an_invalid_stream_fails_at_its_broken_contract(
    monkeypatch: pytest.MonkeyPatch,
    records: Sequence[KernelStreamBatch | KernelStats],
    message: str,
) -> None:
    """Missing and undeclared fact families are provider failures rather than empty evidence."""
    monkeypatch.setattr(KernelClient, "stream", lambda self, request: iter(records))
    kernel = Kernel(binary=Path("unused"), root=Path())

    with pytest.raises(RuntimeError, match=message):
        list(kernel.build_streams(["ModuleFact"], {"ModuleFact": ModuleFact}))


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            "H\t16\ninvalid\n",
            "invalid stream record",
        ),
        (
            "H\t16\nB\tModuleFact\n",
            "invalid fact batch",
        ),
        (
            "H\t16\nX\t{}\n",
            "invalid stream record",
        ),
        (
            "H\t16\nB\tModuleFact\t[]\n",
            "without statistics",
        ),
        (
            "H\t16\nF\t{}\nF\t{}\n",
            "more than one footer",
        ),
        (
            "H\t16\nF\t{}\nB\tModuleFact\t[]\n",
            "facts after its footer",
        ),
    ],
)
def test_stream_records_require_one_footer_at_the_end(
    *, tmp_path: Path, payload: str, message: str
) -> None:
    """A footer is the proof the producer completed, and it may appear exactly once at the end."""
    stub = streaming_stub(tmp_path / "records", payload)

    with pytest.raises(RuntimeError, match=message):
        list(KernelExchange(stub, {}, 16).read())


def test_stream_process_contracts_fail_loudly_without_live_pipes_or_output(tmp_path: Path) -> None:
    """A disconnected or silent producer cannot be mistaken for an empty successful analysis."""

    def rejected(cases: Sequence[tuple[Path, str]]) -> None:
        """Require broken producers to expose their bounded diagnostics."""
        for stub, message in cases:
            with pytest.raises(RuntimeError, match=message):
                list(KernelExchange(stub, {}, 16).read())

    class Disconnected:
        stdin = None
        stdout = None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self) -> int:
            return 0

    disconnected = Disconnected()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "Popen", lambda *args, **kwargs: disconnected)
        with pytest.raises(RuntimeError, match="did not open"):
            list(KernelExchange(Path("disconnected"), {}, 16).read())
    assert disconnected.terminated

    rejected(
        [
            (
                streaming_stub(tmp_path / "silent", "", diagnostic="silent failure", status=1),
                "silent failure",
            ),
            (
                streaming_stub(
                    tmp_path / "interrupted", "H\t16\n", diagnostic="provider panic", status=1
                ),
                "provider panic",
            ),
            (streaming_stub(tmp_path / "quiet", ""), "no response was written"),
        ]
    )


def test_an_abandoned_stream_stops_its_producer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Closing a consumer releases a producer rather than leaving it blocked on its output pipe."""

    class Running:
        stdin = StringIO()
        stdout = StringIO("H\t16\nB\tModuleFact\t[]\n")

        def __init__(self) -> None:
            self.terminated = False

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self) -> int:
            return 0

    running = Running()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: running)
    records = KernelExchange(Path("running"), {}, 16).read()
    assert isinstance(next(records), KernelStreamBatch)
    records.close()
    assert running.terminated


@pytest.mark.parametrize(
    "header",
    ["B\t16", 'H\t"16"'],
)
def test_a_stream_header_has_one_typed_shape(tmp_path: Path, header: str) -> None:
    """A version-like value outside the header envelope is not a protocol handshake."""
    stub = streaming_stub(
        tmp_path / "header",
        header + "\n",
    )
    with pytest.raises(RuntimeError, match="invalid stream header"):
        list(KernelExchange(stub, {}, 16).read())


def test_the_workspace_runs_only_the_rules_it_holds_facts_for() -> None:
    """A rule whose stream the kernel did not build never reaches the engine."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    rules = [
        rule for rule in catalog.rules if rule.qualname in {"unused_import", "module_line_count"}
    ]
    workspace = Workspace(streams={ImportBindingFact: []})

    assert [rule.qualname for rule in workspace.runnable(rules)] == ["unused_import"]


def test_sections_do_not_start_the_kernel_when_no_source_family_is_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty request finishes with statistics and performs no subprocess work."""
    kernel = Kernel(binary=Path("unused"), root=tmp_path)

    streamed = [KernelStats()]
    monkeypatch.setattr(KernelClient, "stream", lambda self, request: iter(streamed))
    result = list(kernel.sections([]))

    assert result == [KernelStats()]


class TestKernelLocation:
    """Verify every supported standalone kernel lookup path."""

    def test_the_binary_falls_back_to_the_path_when_nothing_is_built(self, tmp_path: Path) -> None:
        """Without a local build the client asks the path for the kernel."""
        assert locate(
            tmp_path,
            source=tmp_path / "installed/mcmr/kernel/analysis.py",
        ) == Path("mcmr-kernel")

    def test_the_binary_locator_does_not_treat_an_inspection_failure_as_absence(
        self,
        tmp_path: Path,
    ) -> None:
        """A local build hidden by an operational failure must not select another executable."""
        release = tmp_path / "src/core/target/release/mcmr-kernel"
        release.parent.mkdir(parents=True)
        release.symlink_to(release)

        with pytest.raises(OSError, match="symbolic links"):
            locate(tmp_path)

    def test_the_binary_locator_finds_the_package_source_checkout(self, tmp_path: Path) -> None:
        """An installed module can recover its source checkout without fixed parent indexes."""
        checkout = tmp_path / "checkout"
        source = checkout / "src/api/mcmr/kernel/analysis.py"
        manifest = checkout / "src/core/Cargo.toml"
        binary = checkout / "src/core/target/debug/mcmr-kernel"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("")
        binary.parent.mkdir(parents=True)
        binary.write_text("")

        assert locate(tmp_path / "target", source=source) == binary

    def test_the_binary_locator_prefers_the_isolated_standalone_cache(
        self, tmp_path: Path
    ) -> None:
        """The standalone kernel stays separate from the Python extension feature cache."""
        binary = tmp_path / ".chefe/target-kernel/release/mcmr-kernel"
        binary.parent.mkdir(parents=True)
        binary.write_text("")

        assert locate(tmp_path) == binary
