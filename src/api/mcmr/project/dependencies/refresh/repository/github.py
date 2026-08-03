from patos import FrozenModel


class GitHubRepository(FrozenModel):
    """Relevant objective state from one GitHub repository response."""

    archived: bool
