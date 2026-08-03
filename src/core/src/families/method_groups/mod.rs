use crate::source::Source;
use crate::walk::{docstring, qualified_name, walk};
use ruff_python_ast::{ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};

/// Every method one file declares, normalized so identical siblings can be found.
pub fn method_groups(source: &Source, module: &ModModule) -> Value {
    let mut groups: Vec<Value> = Vec::new();
    for statement in walk(module) {
        let Stmt::ClassDef(class) = statement else {
            continue;
        };
        let base = class
            .arguments
            .as_ref()
            .and_then(|arguments| arguments.args.first().map(qualified_name))
            .unwrap_or_default();
        for member in &class.body {
            if let Stmt::FunctionDef(method) = member {
                let body = docstring(&method.body)
                    .map_or_else(|| method.body.as_slice(), |_| &method.body[1..]);
                groups.push(json!({
                    "normalized_definition": normalized(source, method, body),
                    "locations": [format!(
                        "{}:{}",
                        source.relative,
                        source.line_of(member.range().start())
                    )],
                    "direct_base": base.clone(),
                }));
            }
        }
    }
    json!({"groups": groups})
}

fn normalized(
    source: &Source,
    method: &ruff_python_ast::StmtFunctionDef,
    body: &[Stmt],
) -> String {
    let statements: String = body
        .iter()
        .map(|statement| {
            source
                .slice(statement.range())
                .split_whitespace()
                .collect::<Vec<_>>()
                .join(" ")
        })
        .collect::<Vec<_>>()
        .join("; ");
    format!(
        "{}({})->{statements}",
        method.name,
        method.parameters.iter().count()
    )
}
