use crate::source::Source;
use crate::walk::{annotation_name, walk};
use ruff_python_ast::{ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};

mod recognition;

pub(super) use recognition::Uses;

/// Every parameter one file annotates, with the operations its body performs on it.
pub fn parameters(source: &Source, module: &ModModule) -> Value {
    let uses: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item) => Some(item),
            _ => None,
        })
        .flat_map(|item| {
            item.parameters
                .iter()
                .filter_map(|parameter| {
                    let annotation = parameter.annotation()?;
                    let mut read = Uses::default();
                    read.read_body(&item.body, parameter.name());
                    Some(json!({
                        "name": parameter.name().to_string(),
                        "owner": item.name.to_string(),
                        "span": source.span(parameter.range()),
                        "annotation": annotation_name(annotation),
                        "operations": read.operations.iter().collect::<Vec<_>>(),
                        "attribute_reads": read.attributes,
                        "all_uses_known": read.unrecognized == 0,
                        "is_return_value": read.returned,
                    }))
                })
                .collect::<Vec<_>>()
        })
        .collect();
    json!({"parameters": uses})
}
