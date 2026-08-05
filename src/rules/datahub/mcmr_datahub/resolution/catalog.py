from functools import cached_property

from patos import FrozenModel

from mcmr.facts import DataAsset, DataField


class DataHubCatalog(FrozenModel):
    """Resolve exact DataHub assets and fields without fuzzy guesses."""

    assets: list[DataAsset]

    @cached_property
    def exact(self) -> dict[str, list[DataAsset]]:
        """Index every exact catalog spelling while preserving ambiguity."""
        index: dict[str, list[DataAsset]] = {}
        for asset in self.assets:
            for alias in self.aliases(asset):
                index.setdefault(alias, []).append(asset)
        return index

    @cached_property
    def folded(self) -> dict[str, list[DataAsset]]:
        """Index case-folded spellings only as a unique fallback."""
        index: dict[str, list[DataAsset]] = {}
        for alias, assets in self.exact.items():
            for asset in assets:
                index.setdefault(alias.casefold(), []).append(asset)
        return {
            alias: list({asset.identifier: asset for asset in assets}.values())
            for alias, assets in index.items()
        }

    @staticmethod
    def urn_name(identifier: str) -> str:
        """Extract the dataset name from one canonical DataHub dataset URN."""
        prefix = "urn:li:dataset:("
        if not identifier.startswith(prefix) or not identifier.endswith(")"):
            return ""
        platform_and_name, _environment = identifier[len(prefix) : -1].rsplit(",", 1)
        _platform, name = platform_and_name.split(",", 1)
        return name

    def aliases(self, asset: DataAsset) -> set[str]:
        """Return the canonical URN and exact names DataHub states for one asset."""
        qualified = self.urn_name(asset.identifier)
        aliases = {asset.identifier, qualified, qualified.rsplit(".", 1)[-1]}
        parts = qualified.split(".", maxsplit=1)
        if len(parts) == 2:
            aliases.add(parts[1])
        return {alias for alias in aliases if alias}

    def field(self, asset: DataAsset, name: str) -> DataField | None:
        """Resolve one field exactly, with case folding only when unique."""
        if exact := [field for field in asset.fields if field.name == name]:
            return exact[0] if len(exact) == 1 else None
        folded = [field for field in asset.fields if field.name.casefold() == name.casefold()]
        return folded[0] if len(folded) == 1 else None

    def resolve(self, name: str) -> DataAsset | None:
        """Resolve one exact asset spelling and reject ambiguous aliases."""
        exact = self.exact.get(name, [])
        if len(exact) == 1:
            return exact[0]
        folded = self.folded.get(name.casefold(), [])
        return folded[0] if len(folded) == 1 else None
