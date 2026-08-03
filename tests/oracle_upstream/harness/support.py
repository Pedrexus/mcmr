from ...oracle import Report, Site


def stated(name: str, *sites: Site) -> Report:
    """Return one reader's answer, written out."""
    return Report(reader=name, sites=sites)
