import re
import subprocess
from pathlib import Path

import pytest

from mcmr.facts import CloneFragment, CloneGroupFact, SourceSpan
from mcmr.kernel import Kernel, locate
from mcmr.rules.general.deterministic.duplication.r0003 import pasted_block_copy_count
from mcmr.rules.general.deterministic.duplication.r0004 import duplicated_repository_share

ROOT = Path(__file__).parents[1]

# One module whose only interesting property is the block another module also states. The lines
# around it differ on purpose, so neither reader can grow the match past what was really pasted.
LEADING = 'CONFIG = {"retries": 2}\n\n\n'
FOLLOWING = "def describe(name):\n    return name.upper()\n\n\n"
BLOCK = (
    "def {name}({rows}, {limit}):\n"
    "    {total} = 0\n"
    "    for {row} in {rows}:\n"
    "        if {row}.value > {limit}:\n"
    "            {total} = {total} + {row}.value * 2\n"
    "        else:\n"
    "            {total} = {total} - 1\n"
    "    if {total} < 0:\n"
    "        return 0\n"
    "    return {total}\n"
)
ORIGINAL = BLOCK.format(name="collect", rows="rows", limit="limit", total="total", row="row")
RENAMED = BLOCK.format(name="gather", rows="items", limit="floor", total="carried", row="item")


def fragment(path: str, start: int, end: int) -> CloneFragment:
    """Build one copy of a repeated fragment at a stated place."""
    return CloneFragment(path=path, start_line=start, end_line=end, line_count=end - start + 1)


def group(*fragments: CloneFragment, tokens: int = 90, repository: int = 400) -> CloneGroupFact:
    """Build one clone group the way the kernel states it."""
    return CloneGroupFact(
        key="clone:a.py:1:90",
        span=SourceSpan(path=fragments[0].path if fragments else ""),
        language="python",
        fragments=list(fragments),
        token_length=tokens,
        repository_line_count=repository,
    )


def paste(root: Path, copied: str) -> None:
    """Write two modules that share one block and differ everywhere else."""
    (root / "module_a.py").write_text(LEADING + ORIGINAL)
    (root / "module_b.py").write_text(FOLLOWING + copied)


def symilar_blocks(root: Path) -> tuple[list[frozenset[tuple[str, int, int]]], float]:
    """Return the blocks Symilar reports over one tree, and the share it says they occupy.

    Symilar prints a half-open slice into the real lines of each file, so `[3:13]` names the ten
    lines a reader would call four through thirteen. Both numbers are turned back into the lines a
    person would point at, which is the only form the two tools can be compared in.
    """
    completed = subprocess.run(
        [
            "python",
            "-m",
            "pylint.checkers.symilar",
            "--duplicates=4",
            *sorted(str(path) for path in root.glob("*.py")),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    blocks: list[frozenset[tuple[str, int, int]]] = []
    current: set[tuple[str, int, int]] = set()
    share = 0.0
    for line in completed.stdout.splitlines():
        if re.fullmatch(r"\d+ similar lines in \d+ files", line):
            current = set()
            blocks.append(frozenset())
        elif found := re.fullmatch(r"==(.+):\[(\d+):(\d+)\]", line):
            current.add((Path(found[1]).name, int(found[2]) + 1, int(found[3])))
            blocks[-1] = frozenset(current)
        elif found := re.fullmatch(r"TOTAL lines=\d+ duplicates=\d+ percent=([\d.]+)", line):
            share = float(found[1])
    return blocks, share


def mcmr_blocks(root: Path) -> tuple[list[frozenset[tuple[str, int, int]]], list[CloneGroupFact]]:
    """Return the blocks MCMR reports over the same tree, in the same form."""
    client = Kernel(binary=locate(ROOT), root=root)
    workspace = client.build([CloneGroupFact.__name__], {CloneGroupFact.__name__: CloneGroupFact})
    groups = workspace.stream(CloneGroupFact)
    return [
        frozenset(
            (Path(item.path).name, item.start_line, item.end_line) for item in found.fragments
        )
        for found in groups
    ], groups


def test_a_block_is_only_a_paste_once_it_is_long_enough_to_be_one() -> None:
    """Normalization discards every name, so a short run of shape is not evidence of a copy."""
    copied = group(fragment("a.py", 4, 13), fragment("b.py", 5, 14))

    assert pasted_block_copy_count(copied).value == 1
    assert pasted_block_copy_count(copied, minimum_token_length=200).value == 0
    assert pasted_block_copy_count(copied, minimum_line_count=40).value == 0


def test_a_block_pasted_twice_is_worth_two_deletions() -> None:
    """One of the copies is the one worth keeping, so the value is what a merge would remove."""
    spread = group(fragment("a.py", 1, 12), fragment("b.py", 1, 12), fragment("c.py", 1, 12))

    assert pasted_block_copy_count(spread).value == 2
    assert duplicated_repository_share(spread).value == pytest.approx(6.0)


def test_a_group_with_nothing_in_it_measures_nothing() -> None:
    """The engine builds every fact family empty first, and an empty group has no share."""
    empty = group(repository=0)

    assert pasted_block_copy_count(empty).value == 0
    assert duplicated_repository_share(empty).value == 0.0
    assert empty.copy_count == 0
    assert empty.line_count == 0
    assert empty.redundant_line_count == 0


def test_a_share_of_a_repository_that_was_never_read_is_zero() -> None:
    """A denominator of nothing would divide by zero rather than report a fact."""
    unmeasured = group(fragment("a.py", 1, 12), repository=0)

    assert duplicated_repository_share(unmeasured).value == 0.0
    assert duplicated_repository_share(unmeasured, minimum_line_count=40).value == 0.0


@pytest.mark.skipif(
    not locate(ROOT).exists(),
    reason="the differential oracle needs the kernel binary this checkout builds",
)
class TestAgainstSymilar:
    """Check the clone detector against Pylint's own, which ships as `symilar`.

    The two tools do not ask the same question and pretending they do would be the dishonest way
    to pass. Symilar compares stripped lines of text, so a block only matches where the copy kept
    every name and every literal. MCMR compares normalized tokens, so a copy still matches after
    its locals were renamed and its formatting was redone. That makes MCMR strictly the wider
    reader, and the relationship worth pinning is containment rather than equality. Where the copy
    is verbatim the two agree exactly, on the files, on the lines, and on the share of the tree
    those lines occupy. Where the copy was renamed Symilar reports nothing and MCMR reports the
    block, which is the whole reason the detector normalizes at all.
    """

    def test_a_verbatim_paste_lands_on_the_lines_symilar_names(self, tmp_path: Path) -> None:
        """The strongest form of the claim, where neither reader has an excuse to differ."""
        paste(tmp_path, ORIGINAL)

        oracle, _ = symilar_blocks(tmp_path)
        ours, _ = mcmr_blocks(tmp_path)

        assert oracle == [frozenset({("module_a.py", 4, 13), ("module_b.py", 5, 14)})]
        assert ours == oracle

    def test_the_repository_share_is_the_number_symilar_prints(self, tmp_path: Path) -> None:
        """Symilar divides duplicated lines by every line it read, and so does this rule."""
        paste(tmp_path, ORIGINAL)

        _, share = symilar_blocks(tmp_path)
        _, groups = mcmr_blocks(tmp_path)

        assert share == pytest.approx(37.04, abs=0.01)
        assert duplicated_repository_share(groups[0]).value == pytest.approx(share, abs=0.01)

    def test_a_renamed_paste_is_found_where_symilar_sees_nothing(self, tmp_path: Path) -> None:
        """Symilar compares text, so renaming every local hides the copy from it completely."""
        paste(tmp_path, RENAMED)

        oracle, _ = symilar_blocks(tmp_path)
        ours, groups = mcmr_blocks(tmp_path)

        assert oracle == []
        assert ours == [frozenset({("module_a.py", 4, 13), ("module_b.py", 5, 14)})]
        assert pasted_block_copy_count(groups[0], minimum_token_length=40).value == 1

    def test_two_modules_that_share_no_block_are_quiet_in_both(self, tmp_path: Path) -> None:
        """A reader that finds duplication everywhere has told you nothing about anywhere."""
        (tmp_path / "module_a.py").write_text(LEADING + ORIGINAL)
        (tmp_path / "module_b.py").write_text(
            "def describe(name):\n    return name.upper()\n\n\n"
            "def widest(rows):\n    return max(len(row.label) for row in rows)\n"
        )

        oracle, _ = symilar_blocks(tmp_path)
        ours, _ = mcmr_blocks(tmp_path)

        assert oracle == []
        assert ours == []
