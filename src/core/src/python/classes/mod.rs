use crate::protocol::JsonObject;
use crate::source::{Source, is_test_path};
use crate::walk::{class_instance_fields, expressions, qualified_name, statements, walk};
use ruff_python_ast::token::Tokens;
use ruff_python_ast::{Expr, ModModule, Stmt, StmtClassDef, StmtFunctionDef};
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::BTreeSet;

use super::fact::base;
use super::functions::support::{
    MODEL_FOUNDATIONS, PythonName, base_name, base_names, decorator_name, decorator_texts,
    descend, executable, is_protocol_name, receiver_state,
};
use super::imports::{exported_names, import_bindings};

mod analysis;
mod binding_origin;
mod declared;

use crate::classes::is_approved_foundation_module;

use analysis::{
    assignments, binds, forwards_to_super, is_placeholder, literal_text, pairs, projection_groups,
    region_lines, states_registry_name,
};
use binding_origin::BindingOrigin;
use declared::Declared;

pub(super) fn class_fact(source: &Source, module: &ModModule, tokens: &Tokens) -> Value {
    Declared::new(source, module, tokens).fact()
}

impl<'a> Declared<'a> {
    fn new(source: &'a Source, module: &'a ModModule, tokens: &Tokens) -> Self {
        Self {
            source,
            module,
            regions: region_lines(source, tokens),
            exported: exported_names(module),
            bindings: import_bindings(module),
        }
    }

    /// State every class this file declares, together with what the file itself is.
    fn fact(&self) -> Value {
        let mut classes = Vec::new();
        self.collect(&self.module.body, "module", &mut classes);
        let key = format!("classes:{}", self.source.relative);
        JsonObject::new(base(self.source, &key, self.module.range())).merged(json!({
            "classes": classes,
            "projection_groups": self.projections(),
            "model_files": self.model_file(),
            "has_approved_model_foundation_policy": self
                .bindings
                .values()
                .any(|module| is_approved_foundation_module(module)),
        }))
    }

    fn collect(&self, body: &[Stmt], scope: &str, classes: &mut Vec<Value>) {
        for statement in body {
            match statement {
                Stmt::ClassDef(item) => {
                    classes.push(self.class(item, scope));
                    self.collect(&item.body, "nested", classes);
                }
                Stmt::FunctionDef(item) => self.collect(&item.body, "nested", classes),
                _ => {}
            }
        }
    }

    fn class(&self, item: &StmtClassDef, scope: &str) -> Value {
        let name = item.name.to_string();
        let bases = base_names(self.source, item);
        let is_protocol = item.arguments.as_ref().is_some_and(|arguments| {
            arguments.args.iter().any(|argument| {
                let stated = self.source.slice(argument.range());
                let held = base_name(stated);
                stated == "typing.Protocol"
                    || stated == "typing_extensions.Protocol"
                    || self.resolves(BindingOrigin {
                        name: held,
                        module: "typing",
                    })
                    || self.resolves(BindingOrigin {
                        name: held,
                        module: "typing_extensions",
                    })
            })
        });
        let methods: Vec<Value> = item
            .body
            .iter()
            .filter_map(|member| self.method(item, member))
            .collect();
        let fields = class_instance_fields(item);
        let is_dataclass = decorator_texts(self.source, &item.decorator_list)
            .iter()
            .any(|decorator| decorator_name(decorator) == "dataclass");
        json!({
            "name": name,
            "path": self.source.relative.clone(),
            "span": self.source.span(item.range()),
            "is_test": is_test_path(&self.source.relative),
            "source": self.source.slice(item.range()),
            "scope": scope,
            "visibility": name.visibility_in(scope),
            "direct_bases": item
                .arguments
                .as_ref()
                .map(|arguments| arguments
                    .args
                    .iter()
                    .map(|argument| self.source.slice(argument.range()).to_string())
                    .collect::<Vec<_>>())
                .unwrap_or_default(),
            "is_protocol": is_protocol,
            "class_keywords": item
                .arguments
                .as_ref()
                .map(|arguments| arguments
                    .keywords
                    .iter()
                    .map(|keyword| self.source.slice(keyword.range()).to_string())
                    .collect::<Vec<_>>())
                .unwrap_or_default(),
            "decorators": decorator_texts(self.source, &item.decorator_list),
            "methods": methods,
            "field_count": fields.len(),
            "has_instance_fields": !fields.is_empty(),
            "is_exported": self.exported.contains(&name),
            "has_explicit_registry_name": states_registry_name(&item.body),
            "is_pass_through_layer": self.is_pass_through_layer(item),
            "duplicate_component_alias_count": self.duplicate_component_aliases(item),
            "is_declarative_model": self.is_declarative_model(item, &bases),
            "is_dataclass": is_dataclass,
            "has_ordinary_behavior": self.has_ordinary_behavior(item),
            "states_model_configuration": states_model_configuration(item),
            // The foundation itself is the one class allowed to derive Pydantic directly, since
            // it is what every other class is being asked to derive instead.
            "directly_inherits_pydantic_base_model": !is_model_configuration_base(item)
                && bases
                    .iter()
                    .any(|held| {
                        held == "BaseModel"
                            && self.resolves(BindingOrigin {
                                name: held,
                                module: "pydantic",
                            })
                    }),
            "inherits_approved_model_foundation": bases.iter().any(|held| {
                self.bindings
                    .get(held)
                    .is_some_and(|module| is_approved_foundation_module(module))
            }),
        })
    }

    fn method(&self, owner: &StmtClassDef, statement: &Stmt) -> Option<Value> {
        let Stmt::FunctionDef(item) = statement else {
            return None;
        };
        let name = item.name.to_string();
        let decorators = decorator_texts(self.source, &item.decorator_list);
        let named = |wanted: &str| {
            decorators
                .iter()
                .any(|decorator| decorator_name(decorator) == wanted)
        };
        let kind = if name == "__init__" || name == "__new__" {
            "constructor"
        } else if named("property") || named("cached_property") {
            "property"
        } else if named("staticmethod") {
            "static_method"
        } else if named("classmethod") {
            "class_method"
        } else {
            "method"
        };
        Some(json!({
            "name": name,
            "span": self.source.span(item.range()),
            "source": self.source.slice(item.range()),
            "kind": kind,
            "visibility": name.visibility_in("method"),
            "is_protocol_name": is_protocol_name(&name),
            "reads_receiver": self.method_reads_receiver(item, &decorators),
            "reads_receiver_state": self.method_reads_receiver_state(owner, item, &decorators),
            "decorators": decorators,
            "region": self.region_of(statement),
            "owner_qualified_calls": self.owner_qualified_calls(owner, item),
        }))
    }

    /// Whether one ordinary or class-bound method reads the receiver it declares.
    fn method_reads_receiver(&self, item: &StmtFunctionDef, decorators: &[String]) -> bool {
        if decorators
            .iter()
            .any(|decorator| decorator_name(decorator) == "staticmethod")
        {
            return false;
        }
        let receiver = item
            .parameters
            .posonlyargs
            .first()
            .or_else(|| item.parameters.args.first())
            .map(|parameter| parameter.parameter.name.as_str());
        receiver.is_some_and(|name| {
            statements(&item.body).iter().any(|statement| {
                expressions(statement).iter().any(
                    |expression| matches!(expression, Expr::Name(held) if held.id.as_str() == name),
                )
            })
        })
    }

    /// Whether a method reads receiver-owned data rather than calling a sibling method.
    fn method_reads_receiver_state(
        &self,
        owner: &StmtClassDef,
        item: &StmtFunctionDef,
        decorators: &[String],
    ) -> bool {
        if decorators
            .iter()
            .any(|decorator| decorator_name(decorator) == "staticmethod")
        {
            return false;
        }
        let receiver = item
            .parameters
            .posonlyargs
            .first()
            .or_else(|| item.parameters.args.first())
            .map(|parameter| parameter.parameter.name.as_str());
        let Some(receiver) = receiver else {
            return false;
        };
        let methods: BTreeSet<&str> = owner
            .body
            .iter()
            .filter_map(|member| match member {
                Stmt::FunctionDef(method) => Some(method.name.as_str()),
                _ => None,
            })
            .collect();
        statements(&item.body).iter().any(|statement| {
            expressions(statement)
                .iter()
                .any(|expression| receiver_state(expression, receiver, &methods))
        })
    }

    /// Return every field one class declares or stores through an instance receiver.
    /// Return which independently ordered section of its class one member sits in.
    fn region_of(&self, statement: &Stmt) -> usize {
        let line = self.source.line_of(statement.range().start());
        self.regions.iter().filter(|opened| **opened < line).count()
    }

    /// Return every sibling one method calls through the literal name of the class holding it.
    ///
    /// A call inside a nested function is left out, since a closure can rebind the name, and so is
    /// a method that binds the owner name itself, which is the same shadowing one step earlier.
    fn owner_qualified_calls(&self, owner: &StmtClassDef, item: &StmtFunctionDef) -> Vec<String> {
        let held = executable(&item.body);
        let direct: Vec<&Stmt> = statements(held)
            .into_iter()
            .filter(|statement| !matches!(statement, Stmt::FunctionDef(_)))
            .collect();
        let mut found = Vec::new();
        for statement in &direct {
            if binds(statement, owner.name.as_str()) {
                return Vec::new();
            }
            for expression in expressions(statement) {
                descend(expression, &mut found);
            }
        }
        found
            .into_iter()
            .filter_map(|expression| match expression {
                Expr::Call(call) => Some(qualified_name(&call.func)),
                _ => None,
            })
            .filter(|called| called.starts_with(&format!("{}.", owner.name)))
            .collect()
    }

    /// Whether one class adds a name and a forwarding frame rather than behavior.
    ///
    /// A body of nothing but a docstring is not empty. The class said why it exists, which is the
    /// difference between a layer nobody meant to add and a distinct type somebody named.
    fn is_pass_through_layer(&self, item: &StmtClassDef) -> bool {
        if item.body.iter().all(is_placeholder) {
            return true;
        }
        let held = executable(&item.body);
        !held.is_empty()
            && held.iter().all(|member| match member {
                Stmt::FunctionDef(method) => forwards_to_super(method),
                _ => false,
            })
    }

    /// Count fields one constructor copies off a component the same constructor already retained.
    fn duplicate_component_aliases(&self, item: &StmtClassDef) -> usize {
        item.body
            .iter()
            .filter_map(|member| match member {
                Stmt::FunctionDef(method)
                    if matches!(method.name.as_str(), "__init__" | "model_post_init") =>
                {
                    Some(method)
                }
                _ => None,
            })
            .map(|method| {
                let taken: Vec<&str> = method
                    .parameters
                    .iter()
                    .map(|declared| declared.name().as_str())
                    .collect();
                let stored: Vec<&str> = assignments(&method.body)
                    .into_iter()
                    .filter_map(|(field, value)| match value {
                        Expr::Name(held) if taken.contains(&held.id.as_str()) => {
                            Some((field, held.id.as_str()))
                        }
                        _ => None,
                    })
                    .map(|(_, component)| component)
                    .collect();
                assignments(&method.body)
                    .into_iter()
                    .filter(|(_, value)| match value {
                        Expr::Attribute(read) => matches!(
                            read.value.as_ref(),
                            Expr::Name(held) if stored.contains(&held.id.as_str())
                        ),
                        _ => false,
                    })
                    .count()
            })
            .sum()
    }

    /// Whether one class declares data a library validates rather than behavior it runs.
    fn is_declarative_model(&self, item: &StmtClassDef, bases: &[String]) -> bool {
        !is_model_configuration_base(item)
            && (bases.iter().any(|held| {
                MODEL_FOUNDATIONS.contains(&held.as_str()) || held == "DeclarativeBase"
            }) || decorator_texts(self.source, &item.decorator_list)
                .iter()
                .any(|decorator| decorator_name(decorator) == "dataclass"))
    }

    /// Whether one class declares a method a model library would not have called for it.
    fn has_ordinary_behavior(&self, item: &StmtClassDef) -> bool {
        item.body.iter().any(|member| match member {
            Stmt::FunctionDef(method) => {
                let name = method.name.as_str();
                let decorators = decorator_texts(self.source, &method.decorator_list);
                !is_protocol_name(name)
                    && name != "model_post_init"
                    && !decorators.iter().any(|decorator| {
                        matches!(
                            decorator_name(decorator),
                            "computed_field"
                                | "field_serializer"
                                | "field_validator"
                                | "model_serializer"
                                | "model_validator"
                                | "root_validator"
                                | "validator"
                        )
                    })
            }
            _ => false,
        })
    }

    /// Whether one name this file binds came from one module.
    fn resolves(&self, binding: BindingOrigin<'_>) -> bool {
        self.bindings.get(binding.name).is_some_and(|origin| {
            origin == binding.module || origin.starts_with(&format!("{}.", binding.module))
        })
    }

    /// Return this file as an entry of a shared models package, when it sits inside one.
    fn model_file(&self) -> Vec<Value> {
        let relative = &self.source.relative;
        if !relative
            .split('/')
            .rev()
            .skip(1)
            .any(|part| part == "models")
        {
            return Vec::new();
        }
        let declared: Vec<&Stmt> = self
            .module
            .body
            .iter()
            .filter(|statement| matches!(statement, Stmt::ClassDef(_)))
            .collect();
        let models = declared
            .iter()
            .filter_map(|statement| match statement {
                Stmt::ClassDef(item) => Some(item),
                _ => None,
            })
            .filter(|item| self.is_declarative_model(item, &base_names(self.source, item)))
            .count();
        vec![json!({
            "path": relative,
            "span": self.source.span(self.module.range()),
            "top_level_class_count": declared.len(),
            "model_class_count": models,
            "is_package_initializer": relative.ends_with("__init__.py"),
        })]
    }

    /// Return every structure in this file that repeats the fields of one object it reads.
    fn projections(&self) -> Vec<Value> {
        let mut found = Vec::new();
        let mut held = Vec::new();
        for statement in walk(self.module) {
            for expression in expressions(statement) {
                descend(expression, &mut held);
            }
        }
        for expression in held {
            let span = self.source.span(expression.range());
            let (keys, reads) = match expression {
                Expr::Dict(item) => (
                    item.items
                        .iter()
                        .filter_map(|entry| entry.key.as_ref().and_then(literal_text))
                        .collect::<Vec<_>>(),
                    item.items.iter().map(|entry| &entry.value).collect(),
                ),
                Expr::Call(item) => (
                    item.arguments
                        .keywords
                        .iter()
                        .filter_map(|keyword| keyword.arg.as_ref().map(ToString::to_string))
                        .collect(),
                    item.arguments
                        .keywords
                        .iter()
                        .map(|keyword| &keyword.value)
                        .collect::<Vec<_>>(),
                ),
                Expr::Tuple(item) => pairs(&item.elts),
                Expr::List(item) => pairs(&item.elts),
                _ => continue,
            };
            found.extend(projection_groups(&keys, &reads, &span));
        }
        found
    }
}

/// Whether one class states the configuration a model library reads rather than fields of its own.
fn states_model_configuration(item: &StmtClassDef) -> bool {
    item.body.iter().any(|member| match member {
        Stmt::ClassDef(nested) => nested.name.as_str() == "Config",
        statement => binds(statement, "model_config"),
    })
}

/// Whether one class carries the model policy everything below it derives rather than data.
///
/// A base whose whole body is `model_config` exists to fix validation, mutability, and extra key
/// handling for its subclasses. Reading it as a model of its own reports the one class that is
/// answering the question every other class is being asked, which is why it is recognized from
/// what the body states rather than from the file the body sits in.
fn is_model_configuration_base(item: &StmtClassDef) -> bool {
    class_instance_fields(item).is_empty() && states_model_configuration(item)
}
