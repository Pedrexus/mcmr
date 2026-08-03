use super::tokens::StreamTokens;
use crate::graph::Language;

/// One file reduced to the normalized tokens a clone is matched on.
pub(crate) struct Stream {
    pub(crate) path: String,
    pub(crate) language: Language,
    pub(crate) tokens: StreamTokens,
    pub(crate) implementation_lines: Vec<(usize, usize)>,
    pub(crate) block_open: u32,
    pub(crate) table_plan: u32,
    pub(crate) line_count: usize,
}
