from contextlib import suppress
from itertools import product
from pathlib import Path


def locate(root: Path, *, source: Path = Path(__file__)) -> Path:
    """Return a kernel built beside the target or package source, then try the path."""
    checkout = next(
        (
            parent
            for parent in source.resolve().parents
            if (parent / "src" / "core" / "Cargo.toml").is_file()
        ),
        None,
    )
    roots = [root, checkout] if checkout is not None and checkout != root else [root]
    candidates = (
        candidate
        for base, profile in product(roots, ("release", "debug"))
        for candidate in (
            base / ".chefe" / "target-kernel" / profile / "mcmr-kernel",
            base / "src" / "core" / "target" / profile / "mcmr-kernel",
        )
    )
    for path in candidates:
        with suppress(FileNotFoundError):
            path.stat()
            return path
    return Path("mcmr-kernel")
