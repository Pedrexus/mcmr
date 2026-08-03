use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
pub struct ReceiverEvidence {
    #[serde(rename = "receiver_kind")]
    pub kind: String,
    #[serde(rename = "receiver_text")]
    pub text: String,
    #[serde(rename = "receiver_type")]
    pub type_name: String,
    #[serde(rename = "receiver_type_bases")]
    pub type_bases: Vec<String>,
}
