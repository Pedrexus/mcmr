mod class;
mod model_file;
mod relations;

pub use class::{
    ClassAnalysisRecord, ClassRecord, ClassRelations, MethodBehavior, MethodIdentity, MethodRecord,
};
pub use model_file::ModelFileRecord;
pub use relations::{AttributeProjectionRecord, CoupledTypeGroupRecord};
