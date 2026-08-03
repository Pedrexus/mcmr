use super::super::tokens::WINDOW;

#[derive(Clone, Copy)]
pub(crate) struct Delimiters {
    pub(crate) open: u32,
    pub(crate) close: u32,
}

pub(crate) fn nesting(symbols: &[u32], delimiters: Delimiters) -> Option<Vec<usize>> {
    let mut depth: usize = 0;
    let depths = symbols
        .iter()
        .map(|symbol| {
            if *symbol == delimiters.close {
                depth = depth.checked_sub(1)?;
            }
            let current = depth;
            if *symbol == delimiters.open {
                depth += 1;
            }
            Some(current)
        })
        .collect::<Option<Vec<_>>>()?;
    (depth == 0).then_some(depths)
}

pub(crate) fn fingerprint(symbols: &[u32]) -> Vec<u64> {
    const BASE: u64 = 0x0000_0100_0000_01b3;
    if symbols.len() < WINDOW {
        return Vec::new();
    }
    let power = BASE
        .wrapping_pow(u32::try_from(WINDOW - 1).expect("clone window length must fit inside u32"));
    let mut rolling = symbols[..WINDOW].iter().fold(0u64, |carried, symbol| {
        carried.wrapping_mul(BASE).wrapping_add(scramble(*symbol))
    });
    let mut fingerprints = vec![rolling];
    for start in 1..=symbols.len() - WINDOW {
        rolling = rolling.wrapping_sub(scramble(symbols[start - 1]).wrapping_mul(power));
        rolling = rolling
            .wrapping_mul(BASE)
            .wrapping_add(scramble(symbols[start + WINDOW - 1]));
        fingerprints.push(rolling);
    }
    fingerprints
}

fn scramble(symbol: u32) -> u64 {
    let mut mixed = u64::from(symbol).wrapping_add(0x9e37_79b9_7f4a_7c15);
    mixed = (mixed ^ (mixed >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    mixed = (mixed ^ (mixed >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
    mixed ^ (mixed >> 31)
}
