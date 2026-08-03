use crate::bindings::frames::combined_frame;
use crate::bindings::frames::located::fact_columns;
use crate::syntax::SyntaxRecord;
use polars::prelude::*;

pub(super) fn syntax_fact_frame(records: &[SyntaxRecord]) -> PolarsResult<DataFrame> {
    combined_frame(
        records.len(),
        [
            DataFrame::new(records.len(), fact_columns(records)?)?,
            syntax_value_frame(records)?,
        ],
    )
}

fn syntax_value_frame(records: &[SyntaxRecord]) -> PolarsResult<DataFrame> {
    df![
        "qualname" => records.iter().map(|record| record.qualname.as_str()).collect::<Vec<_>>(),
        "kind" => records.iter().map(|record| record.kind.as_str()).collect::<Vec<_>>(),
        "source" => records.iter().map(|record| record.source.as_str()).collect::<Vec<_>>(),
    ]
}
