from typing import TYPE_CHECKING, cast

from mcmr.domain.contracts import RuleContract, RuleLane, RuleScope
from mcmr.kernel import Kernel, buildable
from mcmr.query import RuleQuery
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery

from ...support import kernel_binary

if TYPE_CHECKING:
    from collections.abc import Collection
    from pathlib import Path

    from mcmr.facts import Fact
    from mcmr.table import Table


def query_count(rule: RuleContract, subject: Table[Fact]) -> int:
    """Invoke one deterministic rule once and sum its table-wide integer values."""
    result = rule.invoke_table(subject, settings={}, dependencies={})
    if not isinstance(result, RuleQuery):
        raise TypeError("a deterministic language rule returned a model query")
    total = result.values.collect().get_column("integer_value").drop_nulls().sum()
    return 0 if total is None else cast("int", total)


# One fixture per language states the same program. A family answering for only one is then a
# frontend gap rather than a fixture difference.

# Each fixture holds comments, prose, a type and method, a branch, a call, and a short local name.
# It also derives from a base declaring the same method.

# Calls are reached through receivers. Without that shape, `OverrideFact` escaped comparison and
# a dropped receiver could turn builtin matching into false positives.
_FIXTURES: dict[str, tuple[str, str]] = {
    "python": (
        "sample.py",
        '''import json


class Base:
    def load(self, name: str) -> str:
        return ''


# TODO: handle the empty case
class Loader(Base):
    """Load one record."""

    def load(self, name: str) -> str:
        # d = read(name)
        # e = parse(d)

        # retry twice before giving up
        d = json.dumps({'name': name})
        if name:
            return d
        return ''
''',
    ),
    "rust": (
        "sample.rs",
        """use std::fmt::Debug;

pub trait Base {
    fn load(&self, name: &str) -> usize;
}

// TODO: handle the empty case
pub struct Loader {
    limit: usize,
}

impl Base for Loader {
    fn load(&self, name: &str) -> usize {
        // let d = read(name);
        // let e = parse(d);

        // retry twice before giving up
        let d = name.len();
        if d > self.limit { return self.limit; }
        d
    }
}

pub fn describe(value: &impl Debug) -> String { format!("{value:?}") }
""",
    ),
    "typescript": (
        "sample.ts",
        """import { readFile } from "node:fs";

export class Base {
  load(name: string): number {
    return 0;
  }
}

// TODO: handle the empty case
export class Loader extends Base {
  load(name: string): number {
    // const d = read(name);
    // const e = parse(d);

    // retry twice before giving up
    const d = name.length;
    if (d > 0) {
      return d;
    }
    return name.trim().length;
  }
}
""",
    ),
    "c": (
        "sample.c",
        """#include <string.h>

/* TODO: handle the empty case */
struct Loader {
  int limit;
  int (*read)(const char* name);
};

int load(struct Loader* self, const char* name) {
  // int d = read(name);
  // int e = parse(d);

  // retry twice before giving up
  int d = self->read(name);
  if (d > self->limit) {
    return self->limit;
  }
  return d;
}
""",
    ),
    "cpp": (
        "sample.cpp",
        """#include <string>

class Base {
 public:
  int load(const std::string& name) { return 0; }
};

// TODO: handle the empty case
class Loader : public Base {
 public:
  int load(const std::string& name) {
    // int d = read(name);
    // int e = parse(d);

    // retry twice before giving up
    int d = name.size();
    if (d > limit) {
      return limit;
    }
    return d;
  }
 private:
  int limit;
};
""",
    ),
    "cuda": (
        "sample.cu",
        """#include <cuda_runtime.h>

class Base {
 public:
  int load(const Reader& source) { return 0; }
};

// TODO: handle the empty case
class Loader : public Base {
 public:
  int load(const Reader& source) {
    // int d = read(source);
    // int e = parse(d);

    // retry twice before giving up
    int d = source.size();
    if (d > limit) {
      return limit;
    }
    return d;
  }
 private:
  int limit;
};

__global__ void scale(float* data) { data[0] = data[0] * 2.0f; }
""",
    ),
}

# Each fixture's member call keeps its language-specific receiver spelling.

# Returning bare `size` for `name.size()` would make builtin rules match unrelated methods. The
# complete name proves that the receiver survived.
_RECEIVER_CALLS: dict[str, str] = {
    "python": "json.dumps",
    "rust": "name.len",
    "typescript": "name.trim",
    "c": "self.read",
    "cpp": "name.size",
    "cuda": "source.size",
}

_SUFFIXES: dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "rust": (".rs",),
    "typescript": (".ts",),
    "c": (".c", ".h"),
    "cpp": (".cpp", ".hpp"),
    "cuda": (".cu", ".cuh"),
}


def language_fixtures() -> dict[str, tuple[str, str]]:
    """Return the written source fixture for every supported language."""
    return _FIXTURES


def language_suffixes() -> dict[str, tuple[str, ...]]:
    """Return discovery suffixes for every supported language fixture."""
    return _SUFFIXES


# Repository-wide families do not belong to language frontends. Differences in them describe the
# fixture rather than frontend coverage.
_REPOSITORY_WIDE = {
    "CloneGroupFact",
    "DependencyComponentFact",
    "InteropFact",
    "ProjectConfigurationFact",
    "RepositoryHistoryFact",
    "RouteFact",
}

# This ledger records every general-rule family missing from another language and why.

# An empty frontend looks exactly like a clean repository, which is worse than no rule. Every gap
# must therefore be explicit or the coverage test fails.
_GAPS: dict[str, dict[str, str]] = {
    "AttributeAccessFact": {
        "rust": "no frontend but Python resolves an access to the declaration it reaches",
        "typescript": "the same, and the frontend never reaches the repository graph",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "BranchFact": {
        "rust": "the dispatch candidate the family carries is a Python match and if-chain shape",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "CallFact": {
        "typescript": "the frontend fills the four shared families and no others yet",
    },
    "OverrideFact": {
        "c": "the language states no inheritance, so no member ever meets one it replaces",
    },
    "LiteralGroupFact": {
        "rust": "repeated literals are grouped only by the Python frontend",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "MethodGroupFact": {
        "rust": "repeated method bodies are grouped only by the Python frontend",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "ParameterFact": {
        "rust": "the configuration-object shape is read only by the Python frontend",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "ProseSegmentFact": {
        "rust": "prose is read out of Python docstrings and no other frontend collects it",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "StringExpressionFact": {
        "rust": "string expressions are collected only by the Python frontend",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
    "WaiverFact": {
        "rust": "a waiver is read as a Python suppression comment and no other form yet",
        "typescript": "the same",
        "c": "the same",
        "cpp": "the same",
        "cuda": "the same",
    },
}

# These contracted families still lack repository providers. Each entry states the minimum
# evidence needed before their rules can run.

# A nearby fact must satisfy the whole contract. This prevents proxy or empty facts from turning
# unavailable evidence into clean answers.
_PROVIDER_GAPS: dict[str, str] = {
    "AlertFact": "alert definitions, ownership, response actions, and recent outcome evidence",
    "ArchitectureCharacteristicFact": (
        "declared qualities, objectives, checks, retained results, owners, scope, and review mode"
    ),
    "CIConfigurationFact": (
        "workflow triggers, required gates, locks, permissions, cancellation, and "
        "branch protection"
    ),
    "DataAssetFact": "catalog assets with fields, types, descriptions, owners, and domains",
    "DataAssetReferenceFact": (
        "source references resolved to catalog identity, lifecycle, and upstream health"
    ),
    "DataChangeFact": (
        "schema changes resolved to downstream assets and the tests covering their impact"
    ),
    "DataFieldReferenceFact": (
        "source field references resolved to catalog fields and their declared types"
    ),
    "DeploymentFact": (
        "locked build inputs, artifact identity, migrations, configuration, secrets, rollback, "
        "and provenance"
    ),
    "FeatureFlagFact": "flag age, role, owner, tested states, and lifecycle decision date",
    "LineageEdgeFact": "directed data lineage with both endpoints resolved in one catalog",
    "PerformanceDecisionFact": (
        "budgets, limits, workloads, environments, baselines, variance policies, and outcomes"
    ),
    "RunbookFact": (
        "trigger, owner, prerequisites, executable commands, verification, and exercise age"
    ),
    "ServiceObjectiveFact": (
        "service objectives, indicators, targets, measurement windows, and alert linkage"
    ),
}


def gap_reasons() -> dict[str, dict[str, str]]:
    """Return declared frontend gaps by fact family and language."""
    return {family: dict(languages) for family, languages in _GAPS.items()}


def provider_gap_reasons() -> dict[str, str]:
    """Return evidence contracts for deterministic families without providers."""
    return dict(_PROVIDER_GAPS)


def receiver_calls() -> dict[str, str]:
    """Return the receiver-qualified call expected from every frontend."""
    return dict(_RECEIVER_CALLS)


def general_families() -> set[str]:
    """Return every fact family a general deterministic rule reads and the kernel can build."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    buildables = buildable()
    return {
        definition.fact
        for definition in catalog.definitions
        if definition.scope is RuleScope.GENERAL
        and definition.lane == RuleLane.DETERMINISTIC
        and definition.fact in buildables
        and definition.fact not in _REPOSITORY_WIDE
    }


def answered(root: Path, language: str, families: Collection[str]) -> set[str]:
    """Return the families the kernel actually filled for one language's repository."""
    types = buildable()
    kernel = Kernel(binary=kernel_binary(), root=root, suffixes=_SUFFIXES[language])
    workspace = kernel.build(sorted(families), {name: types[name] for name in families})
    return {family.__name__ for family, facts in workspace.streams.items() if facts}
