use crate::bindings::frames::located::{LocatedFact, fact_columns};
use polars::prelude::*;

pub(super) enum FactColumnOrder {
    EvidenceFirst,
    RelationFirst,
}

impl FactColumnOrder {
    fn ordered(self, [relation, evidence]: [[Column; 2]; 2]) -> [[Column; 2]; 2] {
        match self {
            Self::EvidenceFirst => [evidence, relation],
            Self::RelationFirst => [relation, evidence],
        }
    }
}

pub(super) fn coordinate(value: usize) -> i64 {
    i64::try_from(value).expect("a source coordinate fits signed 64-bit storage")
}

pub(super) fn fact_frame<Record: LocatedFact>(
    records: &[Record],
    relation: &str,
    lengths: Vec<i64>,
    order: FactColumnOrder,
) -> PolarsResult<DataFrame> {
    let mut columns = fact_columns(records)?;
    let groups = [
        relation_columns(relation, lengths, records.len()),
        evidence_columns(records.len()),
    ];
    columns.extend(order.ordered(groups).into_iter().flatten());
    DataFrame::new(records.len(), columns)
}

fn relation_columns(relation: &str, lengths: Vec<i64>, count: usize) -> [Column; 2] {
    [
        Column::new(format!("{relation}.length").into(), lengths),
        Column::new(format!("{relation}.present").into(), vec![true; count]),
    ]
}

fn evidence_columns(count: usize) -> [Column; 2] {
    [
        Column::new("evidence.length".into(), vec![0_i64; count]),
        Column::new("evidence.present".into(), vec![true; count]),
    ]
}

pub(super) fn combined_frame<const N: usize>(
    length: usize,
    frames: [DataFrame; N],
) -> PolarsResult<DataFrame> {
    let columns = frames
        .into_iter()
        .flat_map(DataFrame::into_columns)
        .collect();
    DataFrame::new(length, columns)
}

pub(super) fn nested_rows<'record, Parent, Child: 'record, Row>(
    records: &'record [Parent],
    children: impl Fn(&'record Parent) -> &'record [Child] + Copy,
    build: impl Fn(u64, &'record Parent, u64, &'record Child) -> Row + Copy,
) -> Vec<Row> {
    records
        .iter()
        .enumerate()
        .flat_map(|(fact_order, fact)| {
            children(fact)
                .iter()
                .enumerate()
                .map(move |(ordinal, child)| build(fact_order as u64, fact, ordinal as u64, child))
        })
        .collect()
}
