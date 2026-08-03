use std::collections::BTreeMap;

pub(super) fn assign_components<'a>(
    reverse: &BTreeMap<&'a str, Vec<&'a str>>,
    finished: Vec<&'a str>,
) -> BTreeMap<&'a str, u64> {
    let mut assigned = BTreeMap::new();
    let mut component = 0_u64;
    for start in finished.into_iter().rev() {
        if assigned.contains_key(&start) {
            continue;
        }
        let mut pending = vec![start];
        while let Some(node) = pending.pop() {
            if assigned.contains_key(&node) {
                continue;
            }
            assigned.insert(node, component);
            pending.extend(
                reverse[&node]
                    .iter()
                    .rev()
                    .filter(|target| !assigned.contains_key(*target))
                    .copied(),
            );
        }
        component += 1;
    }
    assigned
}
