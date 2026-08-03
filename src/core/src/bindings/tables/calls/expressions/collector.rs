use super::place::ExpressionPlace;
use super::relations::ExpressionEdge;
use super::relations::ancestry::ExpressionAncestryRow;
use super::relations::mapping::MappingRow;
use super::rows::ExpressionRow;
use crate::calls::Expression;

pub(in crate::bindings::tables::calls::expressions) struct ExpressionCollector<'a> {
    call_id: String,
    next: usize,
    pub(super) expressions: Vec<ExpressionRow<'a>>,
    pub(super) ancestry: Vec<ExpressionAncestryRow>,
    pub(super) mappings: Vec<MappingRow>,
}

impl<'a> ExpressionCollector<'a> {
    pub(super) fn new(call_id: String) -> Self {
        Self {
            call_id,
            next: 0,
            expressions: Vec::new(),
            ancestry: Vec::new(),
            mappings: Vec::new(),
        }
    }

    pub(super) fn add(
        &mut self,
        expression: &'a Expression,
        place: ExpressionPlace,
        lineage: &[ExpressionEdge],
    ) -> String {
        let expression_id = format!("{}:expression:{}", self.call_id, self.next);
        self.next += 1;
        self.record_expression(expression, &place, &expression_id);
        let path = self.record_ancestry(&place, lineage, &expression_id);
        self.add_children(expression, &place, &path, &expression_id);
        expression_id
    }

    fn add_arguments(
        &mut self,
        expression: &'a Expression,
        place: &ExpressionPlace,
        path: &[ExpressionEdge],
        expression_id: &str,
    ) {
        for (ordinal, nested) in expression.arguments.iter().enumerate() {
            let child = place.child(expression_id.to_string(), "argument", ordinal);
            self.add(nested, child, path);
        }
    }

    fn add_children(
        &mut self,
        expression: &'a Expression,
        place: &ExpressionPlace,
        path: &[ExpressionEdge],
        expression_id: &str,
    ) {
        self.add_arguments(expression, place, path, expression_id);
        self.add_mapping_values(expression, place, path, expression_id);
    }

    fn add_mapping_values(
        &mut self,
        expression: &'a Expression,
        place: &ExpressionPlace,
        path: &[ExpressionEdge],
        expression_id: &str,
    ) {
        for (ordinal, entry) in expression.entries.iter().enumerate() {
            let value_id = self.add(
                &entry.value,
                place.child(expression_id.to_string(), "mapping_value", ordinal),
                path,
            );
            self.mappings.push(MappingRow {
                expression_id: expression_id.to_string(),
                ordinal: ordinal as u64,
                key: entry.key.clone(),
                value_expression_id: value_id,
            });
        }
    }

    fn record_ancestry(
        &mut self,
        place: &ExpressionPlace,
        lineage: &[ExpressionEdge],
        expression_id: &str,
    ) -> Vec<ExpressionEdge> {
        let mut path = lineage.to_vec();
        path.push(ExpressionEdge::at(
            place,
            [expression_id, self.call_id.as_str()],
        ));
        self.record_ancestry_steps(&path, expression_id);
        path
    }

    fn record_ancestry_steps(&mut self, path: &[ExpressionEdge], expression_id: &str) {
        self.ancestry.extend(
            path.iter()
                .enumerate()
                .map(|(step, edge)| ExpressionAncestryRow {
                    call_id: self.call_id.clone(),
                    descendant_expression_id: expression_id.to_string(),
                    step: step as u64,
                    edge: edge.clone(),
                }),
        );
    }

    fn record_expression(
        &mut self,
        expression: &'a Expression,
        place: &ExpressionPlace,
        expression_id: &str,
    ) {
        self.expressions.push(ExpressionRow {
            id: expression_id.to_string(),
            call_id: self.call_id.clone(),
            place: place.clone(),
            expression,
        });
    }
}
