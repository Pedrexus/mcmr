from typing import TYPE_CHECKING

from mcmr.rules.python import (
    approved_model_foundation,
    empty_declarative_model,
    shared_model_file_shape,
)

from .support import messages, table, total

if TYPE_CHECKING:
    from pathlib import Path


def test_a_configuration_base_is_a_foundation_rather_than_an_empty_model(tmp_path: Path) -> None:
    """A base whose body is model configuration states policy instead of declaring data.

    The defect this replaces recognized a foundation only in a file named `bases.py`, so a project
    keeping the same two bases in `core/base/` had both reported as empty models and as classes
    deriving Pydantic directly, and renaming the folder was the only way to quiet either rule.
    """
    subject = table(
        tmp_path,
        {
            "shop/__init__.py": "",
            "shop/core/__init__.py": "",
            "shop/core/strict.py": """from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
""",
            "shop/core/flexible.py": """from pydantic import BaseModel, ConfigDict


class FlexModel(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
""",
            "shop/orders.py": """from .core.strict import Model


class Order(Model):
    total: int


class Ready(Model):
    pass
""",
        },
    )

    assert total(empty_declarative_model, subject) == 1
    assert messages(empty_declarative_model, subject) == ["`Ready` is a model with no fields"]
    assert total(approved_model_foundation, subject) == 0


def test_an_owned_foundation_establishes_the_policy_a_direct_model_bypasses(
    tmp_path: Path,
) -> None:
    """Owning a base establishes policy, while a folder named after one establishes nothing."""
    owned = table(
        tmp_path / "owned",
        {
            "shop/__init__.py": "",
            "shop/core.py": """from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(frozen=True)
""",
            "shop/orders.py": """from .core import Model


class Order(Model):
    total: int
""",
            "shop/settings.py": """from pydantic import BaseModel


class Settings(BaseModel):
    retries: int
""",
        },
    )
    named = table(
        tmp_path / "named",
        {
            "shop/__init__.py": "",
            "shop/bases/__init__.py": "",
            "shop/bases/text.py": "def clean(value):\n    return value.strip()\n",
            "shop/settings.py": """from pydantic import BaseModel

from .bases.text import clean


class Settings(BaseModel):
    retries: int

    def cleaned(self):
        return clean(str(self.retries))
""",
        },
    )

    assert total(approved_model_foundation, owned) == 1
    assert messages(approved_model_foundation, owned) == [
        "`Settings` inherits Pydantic directly instead of the approved model foundation"
    ]
    assert total(approved_model_foundation, named) == 0


def test_a_models_directory_is_shared_only_when_it_declares_data_models(tmp_path: Path) -> None:
    """The folder name is the contract, and what the folder declares is what confirms it."""
    learning = table(
        tmp_path / "learning",
        {
            "vision/__init__.py": "",
            "vision/models/__init__.py": "",
            "vision/models/encoder.py": """class Encoder:
    def forward(self, batch):
        return batch
""",
            "vision/models/shapes.py": "def resize(batch):\n    return batch\n",
        },
    )
    shared = table(
        tmp_path / "shared",
        {
            "shop/__init__.py": "",
            "shop/models/__init__.py": "",
            "shop/models/account.py": """from pydantic import BaseModel


class Account(BaseModel):
    name: str
""",
            "shop/models/helpers.py": "def normalize(value):\n    return value.strip()\n",
        },
    )

    assert total(shared_model_file_shape, learning) == 0
    assert total(shared_model_file_shape, shared) == 1
    assert messages(shared_model_file_shape, shared) == [
        "`shop/models/helpers.py` declares 0 top-level classes of which 0 are models"
    ]
