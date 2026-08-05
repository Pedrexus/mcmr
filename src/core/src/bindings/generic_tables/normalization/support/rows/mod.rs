use super::{fact::FactRow, record::RecordRow, value::ValueRow};

pub(crate) trait NormalizedRow {
    fn fact_order(&self) -> u64;
    fn fact_id(&self) -> &str;
}

macro_rules! normalized_row {
    ($row:ty) => {
        impl NormalizedRow for $row {
            fn fact_order(&self) -> u64 {
                self.fact_order
            }

            fn fact_id(&self) -> &str {
                &self.fact_id
            }
        }
    };
}

normalized_row!(FactRow);
normalized_row!(RecordRow);
normalized_row!(ValueRow);
