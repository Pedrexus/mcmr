from ..... import rule
from .....facts import DataAssetFact
from .....models import Percentage


@rule
def data_definition_gap_percentage(subject: DataAssetFact) -> Percentage:
    """Measure cataloged assets and fields lacking a business description.

    Definition
    ----------
    Treat every asset and every field as one object that ought to carry a description, then divide
    the objects whose description is empty once trimmed by the number of objects. A catalog without
    descriptions is a list of names, and the cost lands on whoever has to guess whether `amount` is
    gross or net, in what currency, and as of when.

    Presence is all this measures. Whether a description is accurate or useful is a judgment a
    contextual rule makes, and conflating the two would let a catalog full of restated column names
    score as documented.

    Evidence
    --------
    Each finding names one asset or field whose description is empty. The value is the percentage
    of catalog objects carrying no description, and nothing is inferred from a name that looks
    self-explanatory.

    Exceptions
    ----------
    A description of only whitespace reads as absent, since a field holding a space documents
    nothing. An empty snapshot measures zero rather than one hundred, because there is no
    undocumented object in it to count. A field whose meaning its name genuinely carries still
    counts as undocumented, and a project that disagrees is disagreeing with the rule rather than
    finding an exception to it.

    Examples
    --------
    One asset with an empty description holding two fields, one described and one not, has three
    objects and two gaps, so the value is about `66.7`. An asset described together with its one
    described field returns `0`. An empty snapshot returns `0`.

    References
    ----------
    Cites "DAMA-DMBOK", metadata management principles
    Cites "DataHub documentation", glossary and description metadata
    """
    descriptions = [
        description
        for asset in subject.assets
        for description in [asset.description, *(field.description for field in asset.fields)]
    ]
    if not descriptions:
        return 0.0
    return sum(not description.strip() for description in descriptions) / len(descriptions) * 100.0
