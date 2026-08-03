use super::streams::Stream;
use super::tokens::WINDOW;

mod group;
mod index;
mod site;

pub(super) use group::Group;
use index::{FingerprintBlock, identical};
use site::{Site, without_overlap};

/// Return every run of normalized tokens that appears in more than one place.
///
/// The whole repository is fingerprinted into one list of window starts, which is sorted so that
/// equal fingerprints sit together. Each block of equal fingerprints is then split by the tokens
/// it actually holds, because a fingerprint is a hash and two unrelated windows may land on one.
/// A group that also matches one token earlier is dropped, since the longer run containing it is
/// reported instead, and what survives is grown to the right for as long as every copy agrees.
pub(super) fn repeated(streams: &[Stream]) -> Vec<Group> {
    let index = window_index(streams);
    repeated_groups(streams, &index)
}

fn window_index(streams: &[Stream]) -> Vec<(u64, Site)> {
    let mut index: Vec<(u64, Site)> = Vec::new();
    for (position, stream) in streams.iter().enumerate() {
        index.extend(
            stream
                .tokens
                .fingerprints
                .iter()
                .enumerate()
                .filter(|(start, _)| stream.inside(*start..*start + WINDOW))
                .map(|(start, fingerprint)| {
                    (
                        *fingerprint,
                        Site {
                            stream: position,
                            start,
                        },
                    )
                }),
        );
    }
    index.sort_unstable();
    index
}

fn repeated_groups(streams: &[Stream], index: &[(u64, Site)]) -> Vec<Group> {
    let mut groups = Vec::new();
    let mut cursor = 0;
    while cursor < index.len() {
        let width = index[cursor..].partition_point(|(seen, _)| *seen == index[cursor].0);
        let block = &index[cursor..cursor + width];
        cursor += width;
        groups.extend(repeated_block(streams, FingerprintBlock { index, block }));
    }
    groups
}

fn repeated_block(streams: &[Stream], candidates: FingerprintBlock<'_>) -> Vec<Group> {
    if candidates.block.len() < 2 {
        return Vec::new();
    }
    identical(streams, candidates.block)
        .into_values()
        .filter_map(|members| repeated_group(streams, candidates.index, &members))
        .collect()
}

fn repeated_group(streams: &[Stream], index: &[(u64, Site)], members: &[Site]) -> Option<Group> {
    if members.len() < 2 || extends_left(streams, index, members) {
        return None;
    }
    // Overlapping windows cannot become distinct fragments. Remove them before extension so
    // repetitive generated bodies do not turn one match into quadratic sites.
    let seeds = without_overlap(members, WINDOW, streams);
    if seeds.len() < 2 {
        return None;
    }
    let length = extent(streams, &seeds);
    let sites = without_overlap(&seeds, length, streams);
    (sites.len() > 1).then_some(Group { length, sites })
}

/// Keep the longest reading of every duplicated region and drop the ones nested inside it.
///
/// One copied region is shared by a different set of files at each of its lengths, since a file
/// that stops matching halfway through still matched the first half. Every one of those readings
/// is a real group, and reporting all of them would bury the finding that matters under the
/// shorter ones it already contains. The longest wins, and a group survives only where at least
/// two of its copies are still somewhere no longer group has claimed.
pub(super) fn maximal(groups: Vec<Group>, streams: &[Stream]) -> Vec<Group> {
    let mut ordered = groups;
    ordered.sort_by(|left, right| {
        right
            .length
            .cmp(&left.length)
            .then_with(|| left.sites.cmp(&right.sites))
    });
    let mut claimed: Vec<Vec<(usize, usize)>> = vec![Vec::new(); streams.len()];
    let mut kept: Vec<Group> = Vec::new();
    for group in ordered {
        let fresh = group
            .sites
            .iter()
            .filter(|site| {
                !claimed[site.stream]
                    .iter()
                    .any(|(from, to)| *from <= site.start && site.start + group.length <= *to)
            })
            .count();
        if fresh < 2 {
            continue;
        }
        for site in &group.sites {
            claimed[site.stream].push((site.start, site.start + group.length));
        }
        kept.push(group);
    }
    kept
}

/// Split one block of equal fingerprints into the sets whose tokens really are the same.
///
/// The language leads the key so that a Python window and a TypeScript window reduced to the same
/// placeholders are never called copies of each other. They share one alphabet and could collide
/// on `$id ( $id )` alone, and a clone across two languages is a claim this detector cannot make.
/// Whether every copy in one group can step a token to the left together.
///
/// A duplicated run of tokens produces one window at every starting position inside it, and
/// reporting all of them would report a single copied function forty times. Only the leftmost
/// window survives, and a window whose whole membership matches one token earlier as well is not
/// the leftmost one. The membership has to match in size too, since a group that loses a copy by
/// stepping left is a longer shared run of its own rather than the tail of the shorter one.
fn extends_left(streams: &[Stream], index: &[(u64, Site)], members: &[Site]) -> bool {
    let Some(head) = members.first() else {
        return false;
    };
    if members.iter().any(|site| site.start == 0) {
        return false;
    }
    if members
        .iter()
        .any(|site| !streams[site.stream].inside(site.start - 1..site.start - 1 + WINDOW))
    {
        return false;
    }
    let earlier = streams[head.stream].tokens.symbols[head.start - 1];
    let together = members
        .iter()
        .all(|site| streams[site.stream].tokens.symbols[site.start - 1] == earlier);
    together
        && occurrences(
            streams,
            index,
            Site {
                stream: head.stream,
                start: head.start - 1,
            },
        ) == members.len()
}

/// Return how many windows in the repository hold exactly what one window holds.
fn occurrences(streams: &[Stream], index: &[(u64, Site)], site: Site) -> usize {
    let stream = &streams[site.stream];
    let fingerprint = stream.tokens.fingerprints[site.start];
    let window = stream.window(site.range(WINDOW));
    let first = index.partition_point(|(seen, _)| *seen < fingerprint);
    index[first..]
        .iter()
        .take_while(|(seen, _)| *seen == fingerprint)
        .filter(|(_, other)| {
            let candidate = &streams[other.stream];
            candidate.language == stream.language
                && candidate.window(other.range(WINDOW)) == window
        })
        .count()
}

/// Grow one match to the right for as long as every copy states the same next token.
fn extent(streams: &[Stream], members: &[Site]) -> usize {
    let head = members[0];
    let mut length = WINDOW;
    while let Some(symbol) = streams[head.stream].tokens.symbols.get(head.start + length) {
        if streams[head.stream].tokens.depths[head.start + length] == 0 {
            break;
        }
        let shared = members[1..].iter().all(|site| {
            streams[site.stream]
                .tokens
                .depths
                .get(site.start + length)
                .copied()
                != Some(0)
                && streams[site.stream].tokens.symbols.get(site.start + length) == Some(symbol)
        });
        if !shared {
            break;
        }
        length += 1;
    }
    let head_pattern = streams[head.stream].identity_pattern(head.range(length));
    members[1..].iter().fold(length, |shared, site| {
        let candidate = streams[site.stream].identity_pattern(site.range(shared));
        head_pattern[..shared]
            .iter()
            .zip(candidate)
            .position(|(left, right)| *left != right)
            .unwrap_or(shared)
    })
}
