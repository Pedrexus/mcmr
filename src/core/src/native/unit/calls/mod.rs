use super::super::support::{child, children, dialect, walk};
use super::Unit;
use crate::calls::{CallRecord, CallSite};
use crate::comments;
use crate::protocol::JsonObject;
use serde_json::{Value, json};
use tree_sitter::Node as Syntax;

impl Unit {
    pub(in crate::native) fn call_fact(&self, root: Syntax) -> CallRecord {
        let calls: Vec<CallSite> = walk(root)
            .into_iter()
            .filter(|node| node.kind() == "call_expression")
            .filter_map(|node| {
                let function = node.child_by_field_name("function")?;
                let mut call = CallSite::new(
                    self.callee(function),
                    self.source
                        .node("call", comments::at(node.start_byte()..node.end_byte())),
                );
                call.result_is_discarded = node
                    .parent()
                    .is_some_and(|parent| parent.kind() == "expression_statement");
                Some(call)
            })
            .collect();
        let mut record = CallRecord::new(
            format!("callfact:{}", self.source.relative),
            self.source
                .span(comments::at(root.start_byte()..root.end_byte())),
            dialect(self.language),
        );
        record.calls = calls;
        record
    }

    /// Return every kernel launch this translation unit states, with the configuration it sets.
    ///
    /// A launch carries four things between its brackets and only the first two are required, so
    /// the two that are usually left out are exactly the two worth reporting: a launch with no
    /// stream runs on the default stream and serializes against everything, and one with no
    /// dynamic shared memory that a kernel expects is a silent misconfiguration.
    pub(in crate::native) fn launch_facts(&self, root: Syntax) -> Vec<Value> {
        let held = walk(root);
        let streamed = held.iter().any(|node| self.names_a_stream(*node));
        held.iter()
            .filter(|node| node.kind() == "call_expression")
            .filter_map(|node| {
                let configuration = child(*node, "kernel_call_syntax")?;
                let function = node.child_by_field_name("function")?;
                let arguments: Vec<&str> = children(configuration)
                    .into_iter()
                    .map(|item| self.text(item))
                    .collect();
                Some(
                    JsonObject::new(self.base(
                        &format!("launch:{}:{}", self.source.relative, self.text(function)),
                        *node,
                    ))
                    .merged(json!({
                        "kernel": self.text(function),
                        "grid": arguments
                            .first()
                            .copied()
                            .expect("a CUDA launch must state its grid"),
                        "block": arguments
                            .get(1)
                            .copied()
                            .expect("a CUDA launch must state its block"),
                        "dynamic_shared_bytes": arguments.get(2).copied().unwrap_or_default(),
                        "stream": arguments.get(3).copied().unwrap_or_default(),
                        "enclosing_function": self.enclosing_name(*node),
                        "unit_uses_streams": streamed,
                    })),
                )
            })
            .collect()
    }

    /// Whether one written name is a stream this unit creates, is handed, or waits on.
    ///
    /// A launch that takes the default stream costs nothing where no other stream exists to
    /// serialize against, and only the whole translation unit can answer that. Being handed a
    /// stream counts as much as creating one, since a function that receives a `cudaStream_t` and
    /// launches without it drains exactly the overlap its caller set up.
    fn names_a_stream(&self, node: Syntax) -> bool {
        if !matches!(
            node.kind(),
            "identifier" | "type_identifier" | "qualified_identifier"
        ) {
            return false;
        }
        let written = self.text(node);
        written.starts_with("cudaStream") || written.ends_with("stream_ref")
    }

    /// Return the name of the function one node sits inside, when it sits inside one.
    fn enclosing_name(&self, node: Syntax) -> String {
        let mut walker = node.parent();
        while let Some(found) = walker {
            if found.kind() == "function_definition"
                && let Some(declarator) = found.child_by_field_name("declarator")
                && let Some(named) = self.declarator_name(declarator)
            {
                return named;
            }
            walker = found.parent();
        }
        String::new()
    }

    /// Return the name one call reaches for, which is the whole path when it goes through a
    /// receiver.
    ///
    /// A member call names its receiver as much as its member, and dropping the receiver leaves
    /// `state.exec` reading as the bare `exec` that several languages spell a scope builtin with.
    /// Every general rule matching a builtin by name then answers yes for any object holding a
    /// method of that name. The reference frontend keeps the path, so this one does too, and a
    /// receiver no lexical reader can name leaves the call unnamed rather than named after its
    /// member alone.
    pub(super) fn callee(&self, function: Syntax) -> String {
        match function.kind() {
            "field_expression" => {
                let Some(field) = function.child_by_field_name("field") else {
                    return String::new();
                };
                let reached = function
                    .child_by_field_name("argument")
                    .map(|receiver| self.callee(receiver))
                    .unwrap_or_default();
                match reached.is_empty() {
                    true => String::new(),
                    false => format!("{reached}.{}", self.text(field)),
                }
            }
            // A call reached through another call names the callable that produced it, which is
            // the same reduction the reference frontend performs on the same shape.
            "call_expression" => function
                .child_by_field_name("function")
                .map(|inner| self.callee(inner))
                .unwrap_or_default(),
            _ => self.text(function).to_string(),
        }
    }
}
