use super::owner::Owner;
use graph::GraphState;
use names::NameState;

mod graph;
mod names;

#[derive(Default)]
pub(in crate::typescript::graph::collector) struct CollectorState {
    pub(in crate::typescript::graph::collector) graph: GraphState,
    pub(in crate::typescript::graph::collector) names: NameState,
    pub(in crate::typescript::graph::collector) owners: Vec<Owner>,
    pub(in crate::typescript::graph::collector) classes: Vec<String>,
    pub(in crate::typescript::graph::collector) exporting: bool,
}

impl CollectorState {
    pub(in crate::typescript::graph::collector) fn owned_by(owner: Owner) -> Self {
        Self {
            owners: vec![owner],
            ..Self::default()
        }
    }
}
