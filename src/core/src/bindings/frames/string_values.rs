use polars::prelude::*;

pub(in crate::bindings) use columns::StringValueColumns;

mod columns;

pub(in crate::bindings) struct StringValueGroup<'record> {
    pub(in crate::bindings) id: String,
    pub(in crate::bindings) values: &'record [String],
}

pub(in crate::bindings) fn string_value_frame(
    names: StringValueColumns<'_>,
    groups: &[StringValueGroup<'_>],
) -> PolarsResult<DataFrame> {
    let length = groups.iter().map(|group| group.values.len()).sum();
    let columns = vec![
        group_id_column(names.id, groups),
        group_ordinal_column(groups),
        group_value_column(names.value, groups),
    ];
    DataFrame::new(length, columns)
}

fn group_id_column(name: &str, groups: &[StringValueGroup<'_>]) -> Column {
    Column::new(
        name.into(),
        groups
            .iter()
            .flat_map(|group| std::iter::repeat_n(group.id.as_str(), group.values.len()))
            .collect::<Vec<_>>(),
    )
}

fn group_ordinal_column(groups: &[StringValueGroup<'_>]) -> Column {
    Column::new(
        "ordinal".into(),
        groups
            .iter()
            .flat_map(|group| 0..group.values.len() as u64)
            .collect::<Vec<_>>(),
    )
}

fn group_value_column(name: &str, groups: &[StringValueGroup<'_>]) -> Column {
    Column::new(
        name.into(),
        groups
            .iter()
            .flat_map(|group| group.values.iter().map(String::as_str))
            .collect::<Vec<_>>(),
    )
}

pub(in crate::bindings) fn selected_string_value_frame<'record, Entity: 'record>(
    names: StringValueColumns<'_>,
    rows: impl IntoIterator<Item = (String, &'record Entity)>,
    values: impl Fn(&'record Entity) -> &'record [String],
) -> PolarsResult<DataFrame> {
    let groups = rows
        .into_iter()
        .map(|(id, entity)| StringValueGroup {
            id,
            values: values(entity),
        })
        .collect::<Vec<_>>();
    string_value_frame(names, &groups)
}
