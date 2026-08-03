from pathlib import Path

from patos import FrozenModel


class SourceReader(FrozenModel):
    """Read back the exact lines a diagnostic quotes, once per file that has one.

    A report over a large repository would otherwise reread a tree the kernel has already walked,
    so a file is opened only when a finding points into it and its lines are kept for the rest of
    the run. A file deleted after analysis leaves the excerpt out, since a synthesized span naming
    a file the tree no longer holds is still a finding worth printing. A directory fact also has a
    useful location but no source line. Other read failures remain failures rather than being
    mistaken for absent source.
    """

    root: Path
    opened: dict[str, list[str]] = {}

    def line(self, path: str, number: int) -> str:
        """Return one source line, or nothing when the file was deleted after analysis."""
        if path not in self.opened:
            self.opened[path] = self.text(path)
        held = self.opened[path]
        return held[number - 1] if 0 < number <= len(held) else ""

    def text(self, path: str) -> list[str]:
        """Return every line of one file, or nothing when the path has no readable source."""
        try:
            return (self.root / path).read_text(encoding="utf-8").splitlines()
        except FileNotFoundError, IsADirectoryError:
            return []
