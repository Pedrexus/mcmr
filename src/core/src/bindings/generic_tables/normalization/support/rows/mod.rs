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

pub(crate) use fact::FactRow;
pub(crate) use record::RecordRow;
pub(crate) use value::{ValueContainer, ValueLocation, ValueRow};

mod fact;
mod record;
mod value;
