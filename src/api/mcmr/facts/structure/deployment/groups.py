from ...foundation import Fact


class DeploymentFields(Fact):
    """Retain applicability, inputs, build, environment, artifact, migration, and configuration."""

    is_applicable: bool = True
    locked_inputs: list[str] = []
    build_command: str = ""
    environment: str = ""
    artifact_identity: str = ""
    migrations: list[str] = []
    configuration_sources: list[str] = []
