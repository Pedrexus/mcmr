use super::Callable;
use super::support::{DTYPE_WORDS, is_tensor_annotation, tensor_wrapper};
use crate::walk::docstring;
use ruff_python_ast::Expr;

/// What one callable states about the tensors it takes and hands back.
pub(super) struct TensorSemantics {
    pub(super) roles: Vec<String>,
    pub(super) states_shape: bool,
    pub(super) states_dtype: bool,
}

impl Callable<'_> {
    /// Return which parameters and returns carry a tensor, and what the callable says about them.
    pub(super) fn tensor_roles(&self) -> TensorSemantics {
        let annotated: Vec<(String, &Expr)> = self
            .item
            .parameters
            .iter()
            .filter_map(|declared| {
                declared
                    .annotation()
                    .map(|annotation| (declared.name().to_string(), annotation))
            })
            .chain(
                self.item
                    .returns
                    .as_deref()
                    .map(|annotation| ("return".to_string(), annotation)),
            )
            .filter(|(_, annotation)| is_tensor_annotation(annotation))
            .collect();
        let documentation = docstring(&self.item.body)
            .unwrap_or_default()
            .to_lowercase();
        let wrappers: Vec<String> = annotated
            .iter()
            .filter_map(|(_, annotation)| tensor_wrapper(annotation))
            .collect();
        TensorSemantics {
            states_shape: !annotated.is_empty()
                && (documentation.contains("shape")
                    || documentation.contains("dimension")
                    || !wrappers.is_empty()),
            states_dtype: !annotated.is_empty()
                && (DTYPE_WORDS.iter().any(|word| documentation.contains(word))
                    || wrappers.iter().any(|wrapper| wrapper != "Shaped")),
            roles: annotated.into_iter().map(|(role, _)| role).collect(),
        }
    }
}
