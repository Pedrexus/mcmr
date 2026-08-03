use super::super::values::{
    ClassValue, MethodValue, class_value_frame as class_values,
    method_value_frame as method_values,
};
use crate::bindings::frames::frame_result;
use crate::classes::ClassRecord;
use polars::prelude::DataFrame;

pub(in crate::bindings::tables::classes) struct ClassValueFrames {
    pub(in crate::bindings::tables::classes) direct_bases: DataFrame,
    pub(in crate::bindings::tables::classes) class_decorators: DataFrame,
    pub(in crate::bindings::tables::classes) class_keywords: DataFrame,
    pub(in crate::bindings::tables::classes) direct_subclasses: DataFrame,
    pub(in crate::bindings::tables::classes) importing_modules: DataFrame,
    pub(in crate::bindings::tables::classes) method_decorators: DataFrame,
    pub(in crate::bindings::tables::classes) owner_qualified_calls: DataFrame,
}

impl ClassValueFrames {
    pub(in crate::bindings::tables::classes) fn build(
        records: &[ClassRecord],
    ) -> Result<Self, String> {
        Ok(Self {
            direct_bases: frame_result(class_values(records, ClassValue::DirectBase))?,
            class_decorators: frame_result(class_values(records, ClassValue::Decorator))?,
            class_keywords: frame_result(class_values(records, ClassValue::Keyword))?,
            direct_subclasses: frame_result(class_values(records, ClassValue::DirectSubclass))?,
            importing_modules: frame_result(class_values(records, ClassValue::ImportingModule))?,
            method_decorators: frame_result(method_values(records, MethodValue::Decorator))?,
            owner_qualified_calls: frame_result(method_values(
                records,
                MethodValue::OwnerQualifiedCall,
            ))?,
        })
    }
}
