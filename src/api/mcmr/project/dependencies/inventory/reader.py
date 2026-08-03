import importlib.metadata
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version
from patos import FrozenModel
from pydantic import JsonValue, TypeAdapter

from .declaration import DependencyDeclaration
from .resolution import DependencyResolution


class DependencyInventory(FrozenModel):
    """Read direct Python declarations and resolve their installed or locked versions."""

    root: Path
    table_adapter: ClassVar[TypeAdapter[dict[str, JsonValue]]] = TypeAdapter(dict[str, JsonValue])
    package_adapter: ClassVar[TypeAdapter[list[dict[str, JsonValue]]]] = TypeAdapter(
        list[dict[str, JsonValue]]
    )
    requirement_adapter: ClassVar[TypeAdapter[list[str]]] = TypeAdapter(list[str])

    @staticmethod
    def declaration(value: str, *, is_development: bool = False) -> DependencyDeclaration:
        """Normalize one PEP 508 requirement into the inventory contract."""
        requirement = Requirement(value)
        return DependencyDeclaration(
            name=canonicalize_name(requirement.name),
            requirement=str(requirement),
            is_development=is_development,
        )

    @classmethod
    def document(cls, path: Path) -> dict[str, JsonValue] | None:
        """Read one TOML document, distinguishing absence from malformed content."""
        try:
            source = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return cls.table_adapter.validate_python(tomllib.loads(source))

    @classmethod
    def stated(
        cls,
        name: str,
        value: JsonValue,
        *,
        is_development: bool = False,
    ) -> DependencyDeclaration:
        """Turn one Chefe key and constraint into a PEP 508 declaration."""
        if isinstance(value, str):
            constraint = "" if value == "*" else value
        else:
            table = cls.table(value)
            raw = table.get("version", "")
            constraint = raw if isinstance(raw, str) and raw != "*" else ""
        return cls.declaration(f"{name}{constraint}", is_development=is_development)

    @classmethod
    def table(cls, value: JsonValue) -> dict[str, JsonValue]:
        """Validate one nested TOML table before walking it."""
        return cls.table_adapter.validate_python(value)

    def chefe(self) -> list[DependencyDeclaration]:
        """Read house-manifest Python dependencies without interpreting another ecosystem."""
        document = self.document(self.root / "chefe.toml")
        if document is None:
            return []
        runtime = self._dependency_table(document, "python", "deps")
        development = self._dependency_table(document, "dev", "python", "deps")
        return self._stated_all(runtime) + self._stated_all(development, is_development=True)

    def declarations(self) -> list[DependencyDeclaration]:
        """Return unique direct requirements with runtime ownership taking precedence."""
        unique: dict[str, DependencyDeclaration] = {}
        for item in [*self.pyproject(), *self.chefe()]:
            if item.name not in unique or unique[item.name].is_development:
                unique[item.name] = item
        return [unique[name] for name in sorted(unique)]

    def locked_versions(self, *, dependency_name: str, requirement: str) -> list[str]:
        """Return compatible registry versions from a standardized `uv.lock` when present."""
        document = self.document(self.root / "uv.lock")
        if document is None:
            return []
        required = Requirement(requirement)
        packages = self.package_adapter.validate_python(document.get("package", []))
        candidates = (self._locked_version(item, dependency_name, required) for item in packages)
        versions = list(filter(None, candidates))
        return sorted(set(versions), key=Version)

    def pyproject(self) -> list[DependencyDeclaration]:
        """Read standardized runtime, optional, and build requirements when present."""
        document = self.document(self.root / "pyproject.toml")
        if document is None:
            return []
        return self._pyproject_requirements(document)

    def resolved_version(self, *, name: str, requirement: str) -> DependencyResolution:
        """Return the greatest matching lock resolution or an environment failure."""
        locked = self.locked_versions(dependency_name=name, requirement=requirement)
        if locked:
            return DependencyResolution(version=str(max(Version(item) for item in locked)))
        return self._environment_resolution(name, requirement=requirement)

    @staticmethod
    def _environment_resolution(name: str, *, requirement: str) -> DependencyResolution:
        """Resolve one dependency from installed package metadata."""
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return DependencyResolution(failure="dependency is not installed")
        return DependencyInventory._parsed_resolution(version, requirement=requirement)

    @staticmethod
    def _is_registry_package(
        package: Mapping[str, JsonValue],
        dependency_name: str,
    ) -> bool:
        """Return whether one locked package is the selected registry dependency."""
        name = package.get("name")
        source = package.get("source")
        return (
            isinstance(name, str)
            and canonicalize_name(name) == dependency_name
            and isinstance(source, Mapping)
            and "registry" in source
        )

    @staticmethod
    def _locked_version(
        package: Mapping[str, JsonValue],
        dependency_name: str,
        required: Requirement,
    ) -> str | None:
        """Return one compatible registry package version."""
        if not DependencyInventory._is_registry_package(package, dependency_name):
            return None
        version = package.get("version")
        if not isinstance(version, str):
            return None
        parsed = Version(version)
        return str(parsed) if required.specifier.contains(parsed, prereleases=True) else None

    @staticmethod
    def _parsed_resolution(version: str, *, requirement: str) -> DependencyResolution:
        """Validate one installed version against its declaration."""
        try:
            parsed = Version(version)
        except InvalidVersion:
            return DependencyResolution(failure="installed version is not valid PEP 440")
        required = Requirement(requirement)
        if not required.specifier.contains(parsed, prereleases=True):
            return DependencyResolution(failure="installed version does not satisfy declaration")
        return DependencyResolution(version=str(parsed))

    @classmethod
    def _declared(
        cls,
        value: JsonValue,
        *,
        is_development: bool = False,
    ) -> list[DependencyDeclaration]:
        """Normalize one validated requirement collection."""
        requirements = cls.requirement_adapter.validate_python(value)
        return [cls.declaration(item, is_development=is_development) for item in requirements]

    @classmethod
    def _dependency_table(
        cls,
        document: Mapping[str, JsonValue],
        *path: str,
    ) -> dict[str, JsonValue]:
        """Walk a validated nested dependency table."""
        value: JsonValue = dict(document)
        for key in path:
            value = cls.table(value).get(key, {})
        return cls.table(value)

    @classmethod
    def _optional(cls, value: JsonValue) -> list[DependencyDeclaration]:
        """Normalize every optional dependency group as development input."""
        groups = cls.table(value)
        return [
            item
            for values in groups.values()
            for item in cls._declared(values, is_development=True)
        ]

    @classmethod
    def _pyproject_requirements(
        cls,
        document: Mapping[str, JsonValue],
    ) -> list[DependencyDeclaration]:
        """Normalize standardized project and build dependency tables."""
        project = cls.table(document.get("project", {}))
        build = cls.table(document.get("build-system", {}))
        return (
            cls._declared(project.get("dependencies", []))
            + cls._optional(project.get("optional-dependencies", {}))
            + cls._declared(build.get("requires", []), is_development=True)
        )

    @classmethod
    def _stated_all(
        cls,
        values: Mapping[str, JsonValue],
        *,
        is_development: bool = False,
    ) -> list[DependencyDeclaration]:
        """Normalize every named Chefe constraint in one table."""
        return [
            cls.stated(name, value, is_development=is_development)
            for name, value in values.items()
        ]
