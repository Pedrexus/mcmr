use crate::graph::contracts::EdgeKind;
use ruff_text_size::TextSize;

pub(super) struct ReferenceRequest<'a> {
    pub(super) source: &'a str,
    pub(super) expression: &'a str,
    pub(super) kind: EdgeKind,
    pub(super) offset: TextSize,
}
