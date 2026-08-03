use polars::prelude::PolarsResult;

pub(super) mod evidence;
pub(super) mod located;
pub(super) mod string_values;

use evidence::EvidenceView;

pub(super) fn combined_frame<const N: usize>(
    length: usize,
    frames: [polars::prelude::DataFrame; N],
) -> PolarsResult<polars::prelude::DataFrame> {
    let columns = frames
        .into_iter()
        .flat_map(polars::prelude::DataFrame::into_columns)
        .collect();
    polars::prelude::DataFrame::new(length, columns)
}

pub(super) fn frame_result<T>(result: PolarsResult<T>) -> Result<T, String> {
    result.map_err(|failure| failure.to_string())
}

pub(super) fn evidence_relation<Record, Evidence: EvidenceView>(
    records: &[Record],
    id_column: &str,
    identity: for<'a> fn(&'a Record) -> &'a str,
    evidence: for<'a> fn(&'a Record) -> &'a [Evidence],
) -> PolarsResult<polars::prelude::DataFrame> {
    let rows = evidence_rows(records, identity, evidence);
    polars::df![
        id_column => rows.iter().map(|row| row.0).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.1).collect::<Vec<_>>(),
        "signal" => rows.iter().map(|row| row.2.signal()).collect::<Vec<_>>(),
        "detail" => rows.iter().map(|row| row.2.detail()).collect::<Vec<_>>(),
        "source" => rows.iter().map(|row| row.2.source()).collect::<Vec<_>>(),
        "confidence" => rows.iter().map(|row| row.2.confidence()).collect::<Vec<_>>(),
    ]
}

fn evidence_rows<Record, Evidence>(
    records: &[Record],
    identity: for<'a> fn(&'a Record) -> &'a str,
    evidence: for<'a> fn(&'a Record) -> &'a [Evidence],
) -> Vec<(&str, u64, &Evidence)> {
    records
        .iter()
        .flat_map(|record| {
            let owner_id = identity(record);
            evidence(record)
                .iter()
                .enumerate()
                .map(move |(ordinal, item)| (owner_id, ordinal as u64, item))
        })
        .collect()
}
