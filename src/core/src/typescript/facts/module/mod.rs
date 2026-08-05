use super::declarations::{declared_class, declared_function, declared_name};
use crate::protocol::JsonObject;
use crate::source::{Source, is_test_path};
use crate::typescript::support::base;
use crate::typescript::support::range;
use count::statement_count;
use oxc_ast::ast::Program;
use oxc_span::GetSpan;
use serde_json::{Value, json};

pub(in crate::typescript::facts) use imports::import_facts;

mod count;
mod imports;

pub(in crate::typescript::facts) fn module_fact(source: &Source, program: &Program) -> Value {
    JsonObject::new(base(source, &format!("module:{}", source.relative))).merged(json!({
        "physical_line_count": source.text.lines().count(),
        "statement_count": statement_count(program),
        "class_count": class_count(program),
        "function_count": function_count(program),
        "is_package_initializer": source.relative.ends_with("/index.ts"),
        "is_test": is_test_path(&source.relative),
        "members": members(source, program),
    }))
}

fn class_count(program: &Program) -> usize {
    program
        .body
        .iter()
        .filter(|statement| declared_class(statement).is_some())
        .count()
}

fn function_count(program: &Program) -> usize {
    program
        .body
        .iter()
        .filter(|statement| declared_function(statement).is_some())
        .count()
}

fn members(source: &Source, program: &Program) -> Vec<Value> {
    program
        .body
        .iter()
        .filter_map(|statement| {
            declared_name(statement)
                .map(|name| json!({"name": name, "source": source.slice(range(statement.span()))}))
        })
        .collect()
}
