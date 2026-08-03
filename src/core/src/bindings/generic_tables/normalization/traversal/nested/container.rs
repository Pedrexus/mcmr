use super::location::NestedLocation;

pub(crate) struct NestedContainer<'a> {
    pub(crate) id: &'a str,
    pub(crate) ordinal: u64,
    pub(crate) length: u64,
    pub(crate) map_key: Option<String>,
}

impl<'a> NestedContainer<'a> {
    pub(crate) fn from_location(id: &'a str, length: u64, location: NestedLocation<'a>) -> Self {
        Self {
            id,
            ordinal: location.container_ordinal,
            length,
            map_key: location.map_key,
        }
    }
}
