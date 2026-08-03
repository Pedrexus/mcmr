use polars::prelude::*;

pub(in crate::bindings) trait LocatedFact {
    fn key(&self) -> &str;
    fn path(&self) -> &str;
    fn start_line(&self) -> u64;
    fn start_column(&self) -> u64;
    fn end_line(&self) -> u64;
    fn end_column(&self) -> u64;
    fn language(&self) -> &str;
}

macro_rules! located_fact {
    ($record:ty) => {
        impl $crate::bindings::frames::located::LocatedFact for $record {
            fn key(&self) -> &str {
                &self.key
            }

            fn path(&self) -> &str {
                &self.span.path
            }

            fn start_line(&self) -> u64 {
                self.span.start_line as u64
            }

            fn start_column(&self) -> u64 {
                self.span.start_column as u64
            }

            fn end_line(&self) -> u64 {
                self.span.end_line as u64
            }

            fn end_column(&self) -> u64 {
                self.span.end_column as u64
            }

            fn language(&self) -> &str {
                &self.language
            }
        }
    };
}

pub(in crate::bindings) use located_fact;

pub(in crate::bindings) fn fact_columns(
    records: &[impl LocatedFact],
) -> PolarsResult<Vec<Column>> {
    Ok(df![
        "fact_order" => (0..records.len() as u64).collect::<Vec<_>>(),
        "fact_id" => records.iter().map(LocatedFact::key).collect::<Vec<_>>(),
        "path" => records.iter().map(LocatedFact::path).collect::<Vec<_>>(),
        "start_line" => records.iter().map(LocatedFact::start_line).collect::<Vec<_>>(),
        "start_column" => records.iter().map(LocatedFact::start_column).collect::<Vec<_>>(),
        "end_line" => records.iter().map(LocatedFact::end_line).collect::<Vec<_>>(),
        "end_column" => records.iter().map(LocatedFact::end_column).collect::<Vec<_>>(),
        "language" => records.iter().map(LocatedFact::language).collect::<Vec<_>>(),
    ]?
    .into_columns())
}

pub(in crate::bindings) fn boolean_fact_frame<Record: LocatedFact>(
    records: &[Record],
    name: &str,
    value: fn(&Record) -> bool,
) -> PolarsResult<DataFrame> {
    let mut columns = fact_columns(records)?;
    columns.push(Column::new(
        name.into(),
        records.iter().map(value).collect::<Vec<_>>(),
    ));
    DataFrame::new(records.len(), columns)
}

pub(in crate::bindings) fn fact_key(record: &impl LocatedFact) -> &str {
    record.key()
}
