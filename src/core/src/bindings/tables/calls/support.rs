use polars::prelude::DataFrame;

/// Fact identity and evidence frames surrounding call relations.
pub(super) struct CallSupportFrames {
    pub(super) facts: DataFrame,
    pub(super) evidence: DataFrame,
}
