from typing import TYPE_CHECKING

import pytest

from mcmr.checking.evaluations import DeferredEvaluation, Evaluation, PreparedRule
from mcmr.domain.contracts import Finding
from mcmr.facts import SourceSpan
from mcmr.rules.general import abstraction_level

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mcmr.domain.contracts import RuleSetting


class EvaluationSupplier:
    """Return one evaluation while recording deferred materialization."""

    def __init__(self, evaluation: Evaluation) -> None:
        self.evaluation = evaluation
        self.calls = 0

    def __call__(self) -> Evaluation:
        """Return the retained evaluation and count this request."""
        self.calls += 1
        return self.evaluation


def prepared(settings: Mapping[str, RuleSetting]) -> PreparedRule:
    """Build one prepared rule around controlled settings."""
    return PreparedRule.of(
        abstraction_level,
        ("str", "", []),
        settings,
        (),
    )


def test_prepared_settings_preserve_defaults_and_valid_configured_values() -> None:
    defaults = prepared({})
    configured = prepared(
        {
            "integer": 7,
            "boolean": False,
            "string": "ready",
        }
    )

    assert defaults.integer_setting("missing", 3) == 3
    assert defaults.boolean_setting("missing", default=True)
    assert defaults.string_setting("missing", default="default") == "default"
    assert configured.integer_setting("integer", 0) == 7
    assert not configured.boolean_setting("boolean", default=True)
    assert configured.string_setting("string", default="") == "ready"


def test_prepared_settings_reject_values_for_a_different_setting_contract() -> None:
    configured = prepared(
        {
            "boolean_integer": True,
            "floating_integer": 1.5,
            "integer_boolean": 1,
            "integer_string": 1,
        }
    )

    with pytest.raises(TypeError, match="boolean_integer is not an integer"):
        configured.integer_setting("boolean_integer", 0)
    with pytest.raises(TypeError, match="floating_integer is not an integer"):
        configured.integer_setting("floating_integer", 0)
    with pytest.raises(TypeError, match="integer_boolean is not Boolean"):
        configured.boolean_setting("integer_boolean", default=False)
    with pytest.raises(TypeError, match="integer_string is not text"):
        configured.string_setting("integer_string", default="")


def test_deferred_evaluation_materializes_complete_evidence_once() -> None:
    span = SourceSpan(path="subject.py", end_line=3)
    finding = Finding(message="The subject failed.", span=span)
    supplier = EvaluationSupplier(
        Evaluation(
            rule=abstraction_level.callable_path,
            fact="function:subject.py:answer",
            value="mixed",
            span=span,
            findings=[finding],
        )
    )
    deferred = DeferredEvaluation(
        rule=abstraction_level.callable_path,
        value="mixed",
        finding_count=1,
        supplier=supplier,
    )

    assert deferred.fact == "function:subject.py:answer"
    assert deferred.span == span
    assert deferred.findings == [finding]
    assert deferred.observation().fact == "function:subject.py:answer"
    assert supplier.calls == 1
