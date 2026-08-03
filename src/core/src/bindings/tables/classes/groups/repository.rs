use super::super::repository::{
    ProjectionValue, coupled_group_frame, coupled_group_suffix_frame, model_file_frame,
    projection_frame, projection_value_frame as projection_values,
};
use crate::bindings::frames::frame_result;
use crate::classes::ClassRecord;
use polars::prelude::DataFrame;

pub(in crate::bindings::tables::classes) struct ClassRepositoryFrames {
    pub(in crate::bindings::tables::classes) coupled_groups: DataFrame,
    pub(in crate::bindings::tables::classes) coupled_group_suffixes: DataFrame,
    pub(in crate::bindings::tables::classes) model_files: DataFrame,
    pub(in crate::bindings::tables::classes) projections: DataFrame,
    pub(in crate::bindings::tables::classes) projection_attributes: DataFrame,
    pub(in crate::bindings::tables::classes) projection_output_keys: DataFrame,
}

impl ClassRepositoryFrames {
    pub(in crate::bindings::tables::classes) fn build(
        records: &[ClassRecord],
    ) -> Result<Self, String> {
        Ok(Self {
            coupled_groups: frame_result(coupled_group_frame(records))?,
            coupled_group_suffixes: frame_result(coupled_group_suffix_frame(records))?,
            model_files: frame_result(model_file_frame(records))?,
            projections: frame_result(projection_frame(records))?,
            projection_attributes: frame_result(projection_values(
                records,
                ProjectionValue::Attribute,
            ))?,
            projection_output_keys: frame_result(projection_values(
                records,
                ProjectionValue::OutputKey,
            ))?,
        })
    }
}
