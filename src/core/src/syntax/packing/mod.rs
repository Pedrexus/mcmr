use serde_json::{Value, json};

/// Flatten one semantic tree into compact preorder records for the wire protocol.
pub(super) fn pack(tree: Value) -> Vec<Value> {
    let mut packed: Vec<Value> = Vec::new();
    let mut pending: Vec<(Value, Option<usize>)> = vec![(tree, None)];
    while let Some((mut node, parent)) = pending.pop() {
        let children = match node["children"].take() {
            Value::Array(children) => children,
            _ => Vec::new(),
        };
        let index = packed.len();
        packed.push(json!([
            node["kind"].take(),
            node["name"].take(),
            node["span"]["start_line"].take(),
            node["span"]["start_column"].take(),
            node["span"]["end_line"].take(),
            node["span"]["end_column"].take(),
            Vec::<usize>::new(),
        ]));
        if let Some(parent) = parent {
            packed[parent][6]
                .as_array_mut()
                .expect("a packed syntax record carries child indices")
                .push(json!(index));
        }
        pending.extend(children.into_iter().rev().map(|child| (child, Some(index))));
    }
    packed
}

/// Rebuild a tree in extractor tests so semantic assertions stay independent of the wire.
#[cfg(test)]
pub fn unpack(fact: &Value) -> Value {
    fn node(records: &[Value], path: &Value, index: usize) -> Value {
        let record = &records[index];
        json!({
            "kind": record[0],
            "name": record[1],
            "span": {
                "path": path,
                "start_line": record[2],
                "start_column": record[3],
                "end_line": record[4],
                "end_column": record[5],
            },
            "children": record[6]
                .as_array()
                .expect("a packed record carries child indices")
                .iter()
                .map(|child| node(records, path, child.as_u64().expect("a child index") as usize))
                .collect::<Vec<_>>(),
        })
    }

    node(
        fact["nodes"]
            .as_array()
            .expect("a syntax fact carries nodes"),
        &fact["span"]["path"],
        0,
    )
}
