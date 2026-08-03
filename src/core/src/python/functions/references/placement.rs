use crate::protocol::Node;

/// Where in one file a call sits, which is what decides whether a class owns it.
#[derive(Clone)]
pub(super) struct Placement {
    owner: String,
    owner_definition: Option<Node>,
    is_inside_callable: bool,
}

impl Placement {
    /// Return where the body of one class sits, which is directly inside that class.
    pub(super) fn inside_class(name: &str) -> Self {
        Self {
            owner: name.to_string(),
            owner_definition: None,
            is_inside_callable: false,
        }
    }

    pub(super) fn root() -> Self {
        Self {
            owner: String::new(),
            owner_definition: None,
            is_inside_callable: false,
        }
    }

    /// Return where the body of one callable sits, given where the callable itself sits.
    ///
    /// A method keeps the class that declares it, and a function nested inside that method loses
    /// it, because a class cannot own behavior a closure captured.
    pub(super) fn inside_callable(self, definition: Node) -> Self {
        Self {
            owner: if self.is_inside_callable {
                String::new()
            } else {
                self.owner
            },
            owner_definition: (!self.is_inside_callable).then_some(definition),
            is_inside_callable: true,
        }
    }

    pub(super) fn owner(&self) -> &str {
        &self.owner
    }

    pub(super) fn owner_definition(&self) -> Option<Node> {
        self.owner_definition.clone()
    }
}
