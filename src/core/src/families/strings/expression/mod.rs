use serde::Serialize;

/// One literal or fixed repetition that produces a string.
#[derive(Clone, Debug, Serialize)]
#[serde(tag = "kind")]
pub enum StringExpression {
    #[serde(rename = "literal")]
    Literal {
        node: crate::protocol::Node,
        runtime_value: String,
        literal_fragment_count: usize,
        wraps_single_runtime_line: bool,
    },
    #[serde(rename = "fixed-repetition")]
    FixedRepetition {
        node: crate::protocol::Node,
        literal: String,
        repetition_count: usize,
    },
}
