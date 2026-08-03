mod alphabet;

pub(super) use alphabet::Alphabet;

/// The shortest run of normalized tokens worth calling a duplicate.
///
/// Pylint's Symilar defaults to four similar lines, but those are four lines of exact text, which
/// is a far stronger claim than four lines of shape. Normalization throws every name and every
/// literal away on purpose, so the floor has to buy back what it gave away or the detector starts
/// reporting grammar. Whole-file scanning needed sixty tokens before shared declarations stopped
/// looking like copies. Candidate windows are now confined to implementation blocks, so forty
/// tokens can find a compact pasted body without admitting module scaffolding.
pub(super) const WINDOW: usize = 40;

/// What every identifier is reduced to, which is what lets a rename stay a clone.
pub(super) const IDENTIFIER: &str = "$id";
/// What every string, character, and interpolated text literal is reduced to.
pub(super) const TEXT: &str = "$s";
/// What every integer, float, and complex literal is reduced to.
pub(super) const NUMBER: &str = "$n";
/// What every boolean literal is reduced to.
pub(super) const TRUTH: &str = "$b";
/// What every empty literal is reduced to, whichever word its language spells it with.
pub(super) const NOTHING: &str = "$x";
/// The end of a logical line, kept because a statement boundary is structure rather than trivia.
pub(super) const NEWLINE: &str = "$nl";
/// The opening of an indented block, which is how an off-side language states nesting.
pub(super) const INDENT: &str = "$in";
/// The closing of an indented block.
pub(super) const DEDENT: &str = "$de";
/// One declarative table body whose schema names and projections are data rather than behavior.
pub(super) const TABLE: &str = "$table";

pub(super) struct Token {
    pub(super) symbol: u32,
    pub(super) line: usize,
    pub(super) identity: Option<String>,
}

impl Token {
    pub(super) fn identifier(symbol: u32, line: usize, identity: String) -> Self {
        Self {
            symbol,
            line,
            identity: Some(identity),
        }
    }

    pub(super) fn plain(symbol: u32, line: usize) -> Self {
        Self {
            symbol,
            line,
            identity: None,
        }
    }
}
