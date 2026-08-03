from patos import FrozenModel


class ProposedImport(FrozenModel):
    """Hold one import before the graph has said whether it knows both ends."""

    importer: str
    imported: str

    @classmethod
    def parse(cls, specification: str) -> ProposedImport:
        """Read one `importer:imported` pair, since a module name never holds a colon."""
        parts = specification.split(":")
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"an import reads as `importer:imported`, not {specification!r}")
        return cls(importer=parts[0], imported=parts[1])

    def arrow(self) -> str:
        """Return this import the way a reader reads it."""
        return f"{self.importer} imports {self.imported}"
