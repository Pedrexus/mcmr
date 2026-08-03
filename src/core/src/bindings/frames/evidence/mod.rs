pub(in crate::bindings) trait EvidenceView {
    fn signal(&self) -> &str;
    fn detail(&self) -> &str;
    fn source(&self) -> &str;
    fn confidence(&self) -> f64;
}
