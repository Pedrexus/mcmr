from itertools import product
from pathlib import Path


def _is_installed(path: Path) -> bool:
    """Whether one checkout kernel candidate exists, without hiding inspection failures."""
    try:
        path.stat()
    except FileNotFoundError:
        return False
    return True


def _checkout(source: Path) -> Path | None:
    """Find the source checkout enclosing an installed API module, when one exists."""
    return next(
        (
            parent
            for parent in source.resolve().parents
            if (parent / "src" / "core" / "Cargo.toml").is_file()
        ),
        None,
    )


def locate(root: Path, *, source: Path = Path(__file__)) -> Path:
    """Return a kernel built beside the target or package source, then try the path."""
    checkout = _checkout(source)
    roots = [root, checkout] if checkout is not None and checkout != root else [root]
    candidates = (
        candidate
        for base, profile in product(roots, ("release", "debug"))
        for candidate in (
            base / ".chefe" / "target-kernel" / profile / "mcmr-kernel",
            base / "src" / "core" / "target" / profile / "mcmr-kernel",
        )
    )
    return next((path for path in candidates if _is_installed(path)), Path("mcmr-kernel"))
