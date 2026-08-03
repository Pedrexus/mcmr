use super::core::{class_evidence_frame, class_fact_frame, class_frame, method_frame};
use crate::bindings::frames::frame_result;
use crate::classes::ClassRecord;
use polars::prelude::DataFrame;

pub(super) use repository::ClassRepositoryFrames;
pub(super) use values::ClassValueFrames;

mod repository;
mod values;

pub(super) struct ClassCoreFrames {
    pub(super) facts: DataFrame,
    pub(super) classes: DataFrame,
    pub(super) methods: DataFrame,
    pub(super) evidence: DataFrame,
}

impl ClassCoreFrames {
    pub(super) fn build(records: &[ClassRecord]) -> Result<Self, String> {
        Ok(Self {
            facts: frame_result(class_fact_frame(records))?,
            classes: frame_result(class_frame(records))?,
            methods: frame_result(method_frame(records))?,
            evidence: frame_result(class_evidence_frame(records))?,
        })
    }
}
