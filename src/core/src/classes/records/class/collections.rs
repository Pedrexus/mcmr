use super::super::model_file::ModelFileRecord;
use super::super::relations::{AttributeProjectionRecord, CoupledTypeGroupRecord};
use serde::{Deserialize, Serialize};

/// Repository relationships attached to one class fact.
#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct ClassRelations {
    #[serde(default)]
    pub coupled_groups: Vec<CoupledTypeGroupRecord>,
    #[serde(default)]
    pub model_files: Vec<ModelFileRecord>,
    #[serde(default)]
    pub projection_groups: Vec<AttributeProjectionRecord>,
}
