use super::runtime::FACT_BATCH_SIZE;
use std::collections::{BTreeMap, BTreeSet};

mod capture;

pub(super) use capture::{CaptureSelection, GenericCapture};

/// Route extracted facts either into retained joins or directly to one consumer.
pub(super) struct Delivery<'a, Emit>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    pub(super) retained: BTreeMap<String, Vec<serde_json::Value>>,
    pub(super) pending: BTreeMap<String, Vec<serde_json::Value>>,
    pub(super) typed_markers: BTreeSet<String>,
    pub(super) emitted_families: BTreeSet<String>,
    pub(super) emitted_count: usize,
    pub(super) generic: GenericCapture,
    pub(super) emit: &'a mut Emit,
}

impl<Emit> Delivery<'_, Emit>
where
    Emit: FnMut(String, Vec<serde_json::Value>) -> Result<(), String>,
{
    pub(super) fn fact_count(&self) -> usize {
        self.emitted_count + self.retained.values().map(Vec::len).sum::<usize>()
    }

    pub(super) fn flush(&mut self) -> Result<(), String> {
        let mut pending = std::mem::take(&mut self.pending);
        let families = pending
            .keys()
            .chain(self.typed_markers.iter())
            .cloned()
            .collect::<BTreeSet<_>>();
        for family in families {
            if self.typed_markers.remove(&family) {
                (self.emit)(format!("@typed:{family}"), Vec::new())?;
            }
            let facts = pending.remove(&family).unwrap_or_default();
            if !facts.is_empty() {
                (self.emit)(family, facts)?;
            }
        }
        Ok(())
    }

    pub(super) fn mark_empty_generic(&mut self) -> Result<(), String> {
        for family in self.generic.unseen() {
            self.generic.marked.insert(family.clone());
            self.generic.rows.entry(family.clone()).or_default();
            (self.emit)(format!("@typed:{family}"), Vec::new())?;
        }
        Ok(())
    }

    pub(super) fn mark_typed(&mut self, family: &str, row_count: usize) -> Result<(), String> {
        if row_count >= FACT_BATCH_SIZE {
            (self.emit)(format!("@typed:{family}"), Vec::new())
        } else {
            self.typed_markers.insert(family.to_string());
            Ok(())
        }
    }

    pub(super) fn send(
        &mut self,
        family: String,
        mut produced: Vec<serde_json::Value>,
    ) -> Result<(), String> {
        let capture = self.generic.accept(&family, &mut produced);
        if capture.newly_marked {
            (self.emit)(format!("@typed:{family}"), Vec::new())?;
        }
        if capture.captured && !capture.mirrored {
            self.emitted_count += capture.row_count;
            self.emitted_families.insert(family);
            return Ok(());
        }
        if let Some(stream) = self.retained.get_mut(&family) {
            stream.append(&mut produced);
        } else if !produced.is_empty() {
            self.emitted_count += produced.len();
            self.emitted_families.insert(family.clone());
            let mut ready = Vec::new();
            {
                let pending = self.pending.entry(family.clone()).or_default();
                pending.append(&mut produced);
                while pending.len() >= FACT_BATCH_SIZE {
                    let remainder = pending.split_off(FACT_BATCH_SIZE);
                    ready.push(std::mem::replace(pending, remainder));
                }
            }
            for batch in ready {
                (self.emit)(family.clone(), batch)?;
            }
        }
        Ok(())
    }

    pub(super) fn send_all(
        &mut self,
        held: BTreeMap<String, Vec<serde_json::Value>>,
    ) -> Result<(), String> {
        for (family, produced) in held {
            self.send(family, produced)?;
        }
        Ok(())
    }
}
