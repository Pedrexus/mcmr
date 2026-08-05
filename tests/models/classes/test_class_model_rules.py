from typing import TYPE_CHECKING

from mcmr.rules.general import class_method_order
from mcmr.rules.python import (
    approved_model_foundation,
    artificial_single_subclass_base_count,
    coupled_nested_type_candidate,
    duplicate_component_attribute_alias_count,
    empty_declarative_model,
    explicit_registry_name,
    hazardous_multiple_inheritance_mro_count,
    manual_model_attribute_projection_count,
    pass_through_inheritance_layer_count,
    shared_model_file_shape,
    single_implementation_abstract_base,
    standard_dataclass_model,
    staticmethod_calling_classmethod_count,
    utility_namespace_class_count,
)

from .support import messages, table, total

if TYPE_CHECKING:
    from pathlib import Path


def test_registry_name_method_order_and_private_scope_use_native_classes(tmp_path: Path) -> None:
    subject = table(
        tmp_path,
        {
            "registry.py": """from patos import Registry
from typing import Protocol


class HarnessBackend(Registry):
    name = "harness"

    def run(self):
        return 1

    def __init__(self):
        pass


class _Private:
    pass


def outer():
    class _Nested:
        pass


class _RuntimeRule(Protocol):
    pass
"""
        },
    )

    assert total(explicit_registry_name, subject) == 1
    assert total(class_method_order, subject) == 1
    assert messages(class_method_order, subject) == [
        "`HarnessBackend` declares 2 of its 2 members out of order, and `__init__` belongs "
        "where `run` sits"
    ]


def test_coupled_types_and_class_body_shapes_use_graph_relations(tmp_path: Path) -> None:
    subject = table(
        tmp_path,
        {
            "domain.py": "class MessageContent:\n    pass\n\nclass MessageKind:\n    pass\n",
            "api.py": "from domain import MessageContent, MessageKind\n",
            "jobs.py": "from domain import MessageContent, MessageKind\n",
            "utilities.py": """class Utilities:
    @staticmethod
    def build():
        return Utilities.from_config()

    @classmethod
    def from_config(cls):
        return cls()


class Report:
    def __init__(self, document, width):
        self.document = document
        self.path = document.path
        self.title = normalize(document.title)
        self.width = width


class PythonImportManager:
    def render(self, value):
        return self.parse(value)

    @staticmethod
    def parse(value):
        return value.strip()
""",
        },
    )

    assert total(coupled_nested_type_candidate, subject) == 1
    assert total(utility_namespace_class_count, subject) == 2
    assert total(staticmethod_calling_classmethod_count, subject) == 1
    assert total(duplicate_component_attribute_alias_count, subject) == 1
    assert "co-imported by 2 modules" in messages(coupled_nested_type_candidate, subject)[0]
    assert messages(staticmethod_calling_classmethod_count, subject) == [
        "static method `Utilities.build` hard-codes its owner to call a sibling class method"
    ]
    assert any(
        "PythonImportManager" in message
        for message in messages(utility_namespace_class_count, subject)
    )


def test_model_rules_reject_standard_dataclasses_and_empty_models(tmp_path: Path) -> None:
    subject = table(
        tmp_path,
        {
            "models.py": """from abc import ABC, abstractmethod
from dataclasses import dataclass
from patos import FrozenModel
from typing import Protocol


@dataclass
class Point:
    x: int
    y: int


class Empty(FrozenModel):
    pass


class Filled(FrozenModel):
    value: int


class Inherited(Filled):
    pass


class Contract(FrozenModel, ABC):
    @abstractmethod
    def run(self):
        pass


class Structural(FrozenModel, Protocol):
    def run(self):
        pass
""",
        },
    )

    assert total(standard_dataclass_model, subject) == 1
    assert total(empty_declarative_model, subject) == 1


def test_inheritance_rules_read_the_enriched_repository_graph(tmp_path: Path) -> None:
    subject = table(
        tmp_path,
        {
            "shop/__init__.py": "",
            "shop/support.py": """class ServiceSupport:
    def normalize(self, value):
        return value.strip()
""",
            "shop/service.py": """from .support import ServiceSupport


class Service(ServiceSupport):
    def execute(self):
        return self.normalize("value")
""",
            "shop/layers.py": """class Contract:
    def run(self):
        return 1


class AliasLayer(Contract):
    pass


class RealLayer(Contract):
    def execute(self):
        return 2


class Left:
    def load(self):
        return 1


class Right:
    def load(self):
        return 2


class Diamond(Left, Right):
    pass
""",
        },
    )

    assert total(artificial_single_subclass_base_count, subject) == 1
    assert total(pass_through_inheritance_layer_count, subject) == 1
    assert total(hazardous_multiple_inheritance_mro_count, subject) == 1
    assert (
        "passes through its only base"
        in messages(pass_through_inheritance_layer_count, subject)[0]
    )


def test_an_abstract_base_needs_more_than_one_implementation(tmp_path: Path) -> None:
    subject = table(
        tmp_path,
        {
            "providers.py": """from abc import ABC, abstractmethod


class FactProvider(ABC):
    @abstractmethod
    def facts(self): ...


class FileProvider(FactProvider):
    def facts(self):
        return []


class Renderer(ABC):
    @abstractmethod
    def render(self): ...


class TextRenderer(Renderer):
    def render(self):
        return "text"


class JsonRenderer(Renderer):
    def render(self):
        return "json"
""",
            "contracts.py": """from typing import Protocol


class Writer(Protocol):
    def write(self): ...


class FileWriter(Writer):
    def write(self):
        return None
""",
        },
    )

    assert total(single_implementation_abstract_base, subject) == 1
    assert messages(single_implementation_abstract_base, subject) == [
        "`FactProvider` is an abstract base with only `FileProvider` below it"
    ]


def test_an_abstract_base_counts_subclasses_imported_through_its_package(tmp_path: Path) -> None:
    subject = table(
        tmp_path,
        {
            "shop/__init__.py": "",
            "shop/contracts/__init__.py": (
                "from .source import ServiceBase\n\n__all__ = ['ServiceBase']\n"
            ),
            "shop/contracts/source.py": """from abc import ABC, abstractmethod


class ServiceBase(ABC):
    @abstractmethod
    def run(self): ...
""",
            "shop/first.py": """from .contracts import ServiceBase


class FirstService(ServiceBase):
    def run(self):
        return 1
""",
            "shop/second.py": """from .contracts import ServiceBase


class SecondService(ServiceBase):
    def run(self):
        return 2
""",
        },
    )

    assert total(single_implementation_abstract_base, subject) == 0
    assert messages(single_implementation_abstract_base, subject) == []


def test_model_foundation_uses_the_native_import_graph(tmp_path: Path) -> None:
    subject = table(
        tmp_path,
        {
            "shop/__init__.py": "",
            "shop/orders/__init__.py": "",
            "shop/billing/__init__.py": "",
            "shop/bases.py": """from patos import FrozenModel


class Model(FrozenModel):
    pass
""",
            "shop/types.py": """from pydantic import BaseModel


class OrderLine(BaseModel):
    total: int
""",
            "shop/orders/place.py": """from ..types import OrderLine


def place(line: OrderLine) -> int:
    return line.total
""",
            "shop/billing/charge.py": """from ..types import OrderLine


def charge(line: OrderLine) -> int:
    return line.total
""",
        },
    )

    assert total(approved_model_foundation, subject) == 1


def test_model_file_shape_and_projection_keep_exact_findings(tmp_path: Path) -> None:
    subject = table(
        tmp_path,
        {
            "models/mixed.py": """from pydantic import BaseModel


class Policy(BaseModel):
    id: int


class Helper:
    pass
""",
            "projection.py": """def project(definition):
    return {
        "id": definition.id,
        "summary": definition.summary,
        "status": definition.status,
        "source-hash": definition.source_hash,
    }
""",
        },
    )

    assert total(shared_model_file_shape, subject) == 1
    assert total(manual_model_attribute_projection_count, subject) == 1
    assert total(manual_model_attribute_projection_count, subject, minimum_attributes=5) == 0
    assert (
        "repeats model attributes `id`, `summary`, `status`, `source_hash`"
        in messages(manual_model_attribute_projection_count, subject)[0]
    )
