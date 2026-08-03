use crate::bindings::rows::syntax::{NodeTraversal, SyntaxBytes, SyntaxNodeRow};
use crate::syntax::{PackedSyntaxRecord, SyntaxRecord};

struct SyntaxTraversal {
    parents: Vec<Option<u64>>,
    depths: Vec<u64>,
    subtree_ends: Vec<u64>,
    lines: Vec<usize>,
}

impl SyntaxTraversal {
    fn new(record: &SyntaxRecord) -> Self {
        let (parents, depths) = ancestry(&record.nodes);
        Self {
            parents,
            depths,
            subtree_ends: subtree_ends(&record.nodes),
            lines: line_offsets(&record.source),
        }
    }

    fn offsets(&self, record: &SyntaxRecord, node: &PackedSyntaxRecord) -> (u64, u64) {
        let start = self.source_offset(record, [node.2, node.3]);
        let end = self.source_offset(record, [node.4, node.5]);
        let byte_start = start.min(end);
        (byte_start as u64, end.saturating_sub(byte_start) as u64)
    }

    fn row<'record>(
        &self,
        fact_order: u64,
        record: &'record SyntaxRecord,
        ordinal: usize,
        node: &'record PackedSyntaxRecord,
    ) -> SyntaxNodeRow<'record, PackedSyntaxRecord> {
        let (byte_start, byte_length) = self.offsets(record, node);
        SyntaxNodeRow {
            fact_order,
            fact_id: &record.key,
            path: &record.span.path,
            node,
            traversal: NodeTraversal {
                ordinal: ordinal as u64,
                parent: self.parents[ordinal],
                depth: self.depths[ordinal],
                subtree_end: self.subtree_ends[ordinal],
            },
            bytes: SyntaxBytes {
                start: byte_start,
                length: byte_length,
            },
        }
    }

    fn rows<'record>(
        &self,
        fact_order: u64,
        record: &'record SyntaxRecord,
    ) -> Vec<SyntaxNodeRow<'record, PackedSyntaxRecord>> {
        record
            .nodes
            .iter()
            .enumerate()
            .map(|(ordinal, node)| self.row(fact_order, record, ordinal, node))
            .collect()
    }

    fn source_offset(&self, record: &SyntaxRecord, position: [usize; 2]) -> usize {
        let relative = position[0].saturating_sub(record.span.start_line);
        let line_start = self
            .lines
            .get(relative)
            .copied()
            .unwrap_or(record.source.len());
        let column = match relative {
            0 => position[1].saturating_sub(record.span.start_column),
            _ => position[1],
        };
        (line_start + column).min(record.source.len())
    }
}

pub(super) fn syntax_node_rows(
    records: &[SyntaxRecord],
) -> Vec<SyntaxNodeRow<'_, PackedSyntaxRecord>> {
    records
        .iter()
        .enumerate()
        .flat_map(|(fact_order, record)| record_rows(fact_order as u64, record))
        .collect()
}

fn record_rows(
    fact_order: u64,
    record: &SyntaxRecord,
) -> Vec<SyntaxNodeRow<'_, PackedSyntaxRecord>> {
    SyntaxTraversal::new(record).rows(fact_order, record)
}

fn ancestry(nodes: &[PackedSyntaxRecord]) -> (Vec<Option<u64>>, Vec<u64>) {
    let mut parents = vec![None; nodes.len()];
    let mut depths = vec![1_u64; nodes.len()];
    for (parent, node) in nodes.iter().enumerate() {
        for child in &node.6 {
            parents[*child] = Some(parent as u64);
            depths[*child] = depths[parent] + 1;
        }
    }
    (parents, depths)
}

fn subtree_ends(nodes: &[PackedSyntaxRecord]) -> Vec<u64> {
    let mut ends = (1..=nodes.len() as u64).collect::<Vec<_>>();
    for (parent, node) in nodes.iter().enumerate().rev() {
        for child in &node.6 {
            ends[parent] = ends[parent].max(ends[*child]);
        }
    }
    ends
}

fn line_offsets(source: &str) -> Vec<usize> {
    std::iter::once(0)
        .chain(
            source
                .as_bytes()
                .iter()
                .enumerate()
                .filter_map(|(offset, byte)| (*byte == b'\n').then_some(offset + 1)),
        )
        .collect()
}
