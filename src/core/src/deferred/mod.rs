use super::runtime::FACT_BATCH_SIZE;
use std::collections::BTreeMap;

mod mode;
mod spools;

pub(super) use mode::DeferredMode;
pub(crate) use spools::FactSpools;

#[cfg(test)]
thread_local! {
    pub(crate) static FORBID_FACT_SPOOLS: std::cell::Cell<bool> = const { std::cell::Cell::new(false) };
}

/// Hold repository-join inputs in memory for native sessions or on disk for streamed diagnostics.
pub(super) enum DeferredFacts {
    Memory(BTreeMap<String, Vec<serde_json::Value>>),
    Spools(FactSpools),
}

impl DeferredFacts {
    pub(super) fn new(
        families: impl IntoIterator<Item = String>,
        mode: DeferredMode,
    ) -> Result<Self, String> {
        match mode {
            DeferredMode::Memory => Ok(Self::Memory(
                families
                    .into_iter()
                    .map(|family| (family, Vec::new()))
                    .collect(),
            )),
            DeferredMode::Spools => FactSpools::new(families).map(Self::Spools),
        }
    }

    pub(super) fn drain<Visit>(&mut self, family: &str, mut visit: Visit) -> Result<(), String>
    where
        Visit: FnMut(Vec<serde_json::Value>) -> Result<(), String>,
    {
        match self {
            Self::Memory(held) => {
                let facts = held
                    .remove(family)
                    .ok_or_else(|| format!("no deferred fact family was opened for {family}"))?;
                let mut batch = Vec::with_capacity(FACT_BATCH_SIZE);
                for fact in facts {
                    batch.push(fact);
                    if batch.len() == FACT_BATCH_SIZE {
                        visit(std::mem::take(&mut batch))?;
                    }
                }
                if !batch.is_empty() {
                    visit(batch)?;
                }
                Ok(())
            }
            Self::Spools(spools) => spools.drain(family, visit),
        }
    }

    pub(super) fn holds(&self, family: &str) -> bool {
        match self {
            Self::Memory(facts) => facts.contains_key(family),
            Self::Spools(spools) => spools.holds(family),
        }
    }

    pub(super) fn read(&mut self, family: &str) -> Result<Vec<serde_json::Value>, String> {
        match self {
            Self::Memory(held) => held
                .remove(family)
                .ok_or_else(|| format!("no deferred fact family was opened for {family}")),
            Self::Spools(spools) => spools.read(family),
        }
    }

    pub(super) fn write(
        &mut self,
        family: &str,
        mut facts: Vec<serde_json::Value>,
    ) -> Result<(), String> {
        match self {
            Self::Memory(held) => {
                held.get_mut(family)
                    .ok_or_else(|| format!("no deferred fact family was opened for {family}"))?
                    .append(&mut facts);
                Ok(())
            }
            Self::Spools(spools) => spools.write(family, facts),
        }
    }
}
