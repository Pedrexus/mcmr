use super::{ClassAddress, Repository, SubclassReference};
use crate::classes::model::Identity;
use crate::classes::records::{ClassAnalysisRecord, ClassRecord};
use crate::functions::FunctionRecord;
use serde_json::{Value, json};

impl<'repository> Repository<'repository> {
    /// Write onto one file's class fact everything only the whole repository knows.
    pub(in crate::classes) fn state(&self, fact: &mut Value) {
        let path = fact["span"]["path"]
            .as_str()
            .expect("ClassFact.span.path must be text")
            .to_string();
        let coupled = self.coupled_groups(&path);
        let holds_models = path
            .rsplit_once('/')
            .is_some_and(|(directory, _)| self.relations.model_packages.contains(directory));
        let object = fact.as_object_mut().expect("ClassFact must be an object");
        object.insert("coupled_groups".to_string(), json!(coupled));
        object.insert(
            "has_approved_model_foundation_policy".to_string(),
            json!(self.states_policy),
        );
        if !holds_models {
            object.insert("model_files".to_string(), json!([] as [Value; 0]));
        }
        let classes = object
            .get_mut("classes")
            .and_then(Value::as_array_mut)
            .expect("ClassFact.classes must be an array");
        for class in classes {
            let name = class["name"]
                .as_str()
                .expect("ClassDeclaration.name must be text")
                .to_string();
            let address = ClassAddress {
                path: &path,
                name: &name,
            };
            if let Some(held) = self.identify(address) {
                let stated = self.judgement(&held, class);
                let record = class
                    .as_object_mut()
                    .expect("ClassDeclaration must be an object");
                for (field, value) in stated {
                    record.insert(field, value);
                }
            }
            let normalized: ClassAnalysisRecord = serde_json::from_value(std::mem::take(class))
                .expect("ClassDeclaration must satisfy its typed record");
            *class = serde_json::to_value(normalized)
                .expect("ClassDeclaration typed record must serialize");
        }
    }

    /// Write repository evidence directly onto one typed class family.
    pub(in crate::classes) fn state_class(&self, fact: &mut ClassRecord) {
        let path = fact.span.path.clone();
        fact.relations.coupled_groups = self.coupled_groups(&path);
        fact.has_approved_model_foundation_policy = self.states_policy;
        let holds_models = path
            .rsplit_once('/')
            .is_some_and(|(directory, _)| self.relations.model_packages.contains(directory));
        if !holds_models {
            fact.relations.model_files.clear();
        }
        for class in &mut fact.classes {
            let address = ClassAddress {
                path: &path,
                name: &class.identity.name,
            };
            let Some(held) = self.identify(address) else {
                continue;
            };
            let subclasses = self
                .index
                .subclasses
                .get(&held)
                .cloned()
                .unwrap_or_default();
            let importing: Vec<String> = self
                .index
                .importers
                .get(&held)
                .map(|found| found.iter().map(|module| (*module).to_string()).collect())
                .unwrap_or_default();
            let importing_refs = importing.iter().map(String::as_str).collect::<Vec<_>>();
            class.shape.direct_subclasses =
                subclasses.iter().map(|(_, name)| name.clone()).collect();
            class.shape.descendant_count = self.descendants(&held).len();
            class.shape.is_instantiated = self.is_built(&held);
            class.shape.is_exported |= self.named_export(&held);
            class.relations.only_cross_module_reference_is_subclass = self
                .only_reference_is_subclass(SubclassReference {
                    held: &held,
                    subclasses: &subclasses,
                    importing: &importing_refs,
                });
            class.relations.base_is_removable_overlap = self.base_is_removable(&held);
            class.relations.has_redundant_direct_base = self.has_redundant_base(&held);
            class.relations.has_noncooperative_concrete_collision =
                self.has_hazardous_collision(&held);
            class.model.is_declarative_model |= self.inherits_declarative_model(&held);
            class.shape.has_inherited_fields = self.inherits_fields(&held);
            class.model.proposed_model_destination =
                self.proposed_destination(&held, &importing_refs);
            class.model.importing_modules = importing;
        }
    }

    /// Write onto one callable fact whether it takes part in dispatch across the repository.
    pub(in crate::classes) fn state_callable(&self, fact: &mut Value) {
        let path = fact["span"]["path"]
            .as_str()
            .expect("FunctionFact.span.path must be text");
        let name = fact["name"]
            .as_str()
            .expect("FunctionFact.name must be text");
        if !self.relations.dispatched.contains(&(path, name)) {
            return;
        }
        fact.as_object_mut()
            .expect("FunctionFact must be an object")
            .insert("is_polymorphic".to_string(), json!(true));
    }

    /// Write repository dispatch evidence directly onto one typed callable row.
    pub(in crate::classes) fn state_function(&self, function: &mut FunctionRecord) {
        if self.relations.dispatched.contains(&(
            function.identity.span.path.as_str(),
            function.identity.name.as_str(),
        )) {
            function.semantics.outcomes.is_polymorphic = true;
        }
    }

    /// Return what the repository concludes about one class, field by field.
    fn judgement(&self, held: &Identity, class: &Value) -> Vec<(String, Value)> {
        let subclasses = self.index.subclasses.get(held).cloned().unwrap_or_default();
        let importing: Vec<&str> = self
            .index
            .importers
            .get(held)
            .map(|found| found.iter().copied().collect())
            .unwrap_or_default();
        vec![
            (
                "direct_subclasses".to_string(),
                json!(subclasses.iter().map(|(_, name)| name).collect::<Vec<_>>()),
            ),
            (
                "descendant_count".to_string(),
                json!(self.descendants(held).len()),
            ),
            ("is_instantiated".to_string(), json!(self.is_built(held))),
            (
                "is_exported".to_string(),
                json!(self.is_exported(held, class)),
            ),
            ("importing_modules".to_string(), json!(importing)),
            (
                "only_cross_module_reference_is_subclass".to_string(),
                json!(self.only_reference_is_subclass(SubclassReference {
                    held,
                    subclasses: &subclasses,
                    importing: &importing,
                })),
            ),
            (
                "base_is_removable_overlap".to_string(),
                json!(self.base_is_removable(held)),
            ),
            (
                "has_redundant_direct_base".to_string(),
                json!(self.has_redundant_base(held)),
            ),
            (
                "has_noncooperative_concrete_collision".to_string(),
                json!(self.has_hazardous_collision(held)),
            ),
            (
                "is_declarative_model".to_string(),
                json!(
                    class["is_declarative_model"].as_bool().unwrap_or_default()
                        || self.inherits_declarative_model(held)
                ),
            ),
            (
                "has_inherited_fields".to_string(),
                json!(self.inherits_fields(held)),
            ),
            (
                "proposed_model_destination".to_string(),
                json!(self.proposed_destination(held, &importing)),
            ),
        ]
    }
}
