from patos import FrozenModel

from ...foundation import ReceiverKind, Visibility


class AttributeAccessFields(FrozenModel):
    """Retain attribute identity, receiver, and visibility evidence."""

    name: str
    receiver_kind: ReceiverKind
    visibility: Visibility = Visibility.PUBLIC
    is_inside_owning_class: bool = False
    is_protocol_name: bool = False
    receiver_text: str = ""
    receiver_type: str = ""
