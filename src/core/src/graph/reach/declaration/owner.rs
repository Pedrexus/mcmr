use crate::graph::contracts::Visibility;
use serde::Serialize;

#[derive(Debug, Serialize)]
pub(crate) struct OwnerContract {
    #[serde(rename = "owner_visibility")]
    pub(crate) visibility: Visibility,
    #[serde(rename = "owner_has_inheritance")]
    pub(crate) has_inheritance: bool,
}
