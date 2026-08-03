pub(super) struct Quote(u8);

impl Quote {
    pub(super) fn new(byte: u8) -> Self {
        Self(byte)
    }

    pub(super) fn byte(&self) -> u8 {
        self.0
    }
}
