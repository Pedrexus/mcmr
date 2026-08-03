use std::collections::{BTreeMap, BTreeSet};

pub(super) fn finish_order<'a>(forward: &BTreeMap<&'a str, Vec<&'a str>>) -> Vec<&'a str> {
    let mut seen = BTreeSet::new();
    let mut finished = Vec::new();
    for start in forward.keys() {
        if !seen.contains(start) {
            finish_from(start, forward, &mut seen, &mut finished);
        }
    }
    finished
}

fn finish_from<'a>(
    start: &'a str,
    forward: &BTreeMap<&'a str, Vec<&'a str>>,
    seen: &mut BTreeSet<&'a str>,
    finished: &mut Vec<&'a str>,
) {
    let mut pending = vec![(start, false)];
    while let Some((node, closing)) = pending.pop() {
        if closing {
            finished.push(node);
        } else if seen.insert(node) {
            pending.push((node, true));
            pending.extend(
                forward[&node]
                    .iter()
                    .rev()
                    .filter(|target| !seen.contains(*target))
                    .copied()
                    .map(|target| (target, false)),
            );
        }
    }
}
