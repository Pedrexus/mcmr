from .groups import DeploymentFields


class DeploymentFact(DeploymentFields):
    """Describe a deployment path through its declared artifacts."""

    secrets_boundary: str = ""
    rollback_command: str = ""
    provenance: str = ""
