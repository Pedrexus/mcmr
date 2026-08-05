from pathlib import Path

import anyio

from ....contextual.corpus import ContextualCorpus
from ....contextual.evaluation import BackendProfile, ContextualExperiment, ContextualSweep
from ....project import ContextBackend, MCMRConfiguration
from ....rulebook.catalog import Catalog
from ....rulebook.discovery import RuleModuleDiscovery
from ...interface import app, console, readable_table
from .reporting import ContextualPresentation


@app.command
def backends(root: Path = Path()) -> None:
    """Show the contextual backend an ordinary check will use, without starting it.

    root: repository whose `tool.mcmr.contextual` table should be inspected.
    """
    configuration = MCMRConfiguration.read(root)
    configured = configuration.contextual
    table = readable_table("MCMR contextual backend")
    table.add_column("State")
    table.add_column("Backend")
    table.add_column("Model")
    table.add_column("Reasoning")
    table.add_column("Timeout")
    table.add_row(
        "enabled" if configuration.execution.contextual else "disabled",
        configured.backend,
        configured.model,
        configured.reasoning_effort,
        f"{configured.timeout_seconds} s",
    )
    console.print(table)


@app.command
def contextual_experiment(
    labels: Path,
    *,
    root: Path = Path(),
    workers: int = 8,
    include_sol: bool = False,
    output: Path | None = None,
) -> None:
    """Compare contextual backends against one complete reviewed label corpus.

    labels: versioned JSON corpus containing reviewed candidates and exact answers.
    root: project whose contextual backend settings apply.
    workers: maximum isolated model operations active at once.
    include_sol: add the slower Sol medium profile after Luna high.
    output: optional path that receives the complete machine-readable experiment.
    """
    configuration = MCMRConfiguration.read(root)
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    corpus = ContextualCorpus.read(labels)
    experiment = ContextualExperiment(
        profiles=BackendProfile.routine(include_sol=include_sol),
        workers=workers,
    )
    with console.status("Running the labeled contextual experiment", spinner="dots"):
        report = anyio.run(
            experiment.run,
            catalog,
            corpus,
            configuration.contextual,
            configuration.settings(catalog.definitions, rules=catalog.rules),
        )
    ContextualPresentation(output).experiment(report)


@app.command
def model_sweep(
    root: Path = Path(),
    *,
    workers: int = 8,
    backend: str = "",
    model: str = "",
    reasoning_effort: str = "",
    output: Path | None = None,
) -> None:
    """Exercise every contextual rule through the configured live backend.

    root: project whose contextual backend and rule settings apply.
    backend: one registered backend name, such as `codex`, `claude`, or `openrouter`, that replaces
    the configured one for this stateless sweep and nothing else.
    model: the model to sweep.
    reasoning_effort: how hard that model should think.
    workers: maximum isolated model operations active at once.
    output: optional destination that receives the complete machine-readable report for later
    review.
    """
    configuration = MCMRConfiguration.read(root)
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    configured = configuration.contextual
    profile = BackendProfile(
        name="configured",
        backend=ContextBackend(backend) if backend else configured.backend,
        model=model or configured.model,
        reasoning_effort=reasoning_effort or configured.reasoning_effort,
    )
    sweep = ContextualSweep(
        backend=profile.build(configured, workers),
        workers=workers,
    )
    with console.status("Running every contextual rule", spinner="dots"):
        report = anyio.run(
            sweep.run,
            catalog,
            configuration.settings(catalog.definitions, rules=catalog.rules),
        )
    ContextualPresentation(output).sweep(report)
