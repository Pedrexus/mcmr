pub(crate) struct NestedRow<'a, Value> {
    pub(crate) id: String,
    pub(crate) fact_id: &'a str,
    pub(crate) ordinal: u64,
    pub(crate) value: &'a Value,
}

pub(crate) fn nested_rows<'a, Record, Value>(
    records: &'a [Record],
    relation: &str,
    key: for<'record> fn(&'record Record) -> &'record str,
    values: for<'record> fn(&'record Record) -> &'record [Value],
) -> Vec<NestedRow<'a, Value>> {
    records
        .iter()
        .flat_map(|record| {
            let fact_id = key(record);
            values(record)
                .iter()
                .enumerate()
                .map(move |(ordinal, value)| NestedRow {
                    id: format!("{fact_id}:{relation}:{ordinal}"),
                    fact_id,
                    ordinal: ordinal as u64,
                    value,
                })
        })
        .collect()
}
