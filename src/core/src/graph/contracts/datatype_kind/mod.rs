/// State whether one named data type implements behavior, promises it, or enumerates values.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DatatypeKind {
    Concrete,
    Contract,
    Enumeration,
}
