use super::super::runtime::FACT_BATCH_SIZE;
use std::collections::BTreeMap;
use std::io::{BufRead, BufReader, BufWriter, Seek, Write};

/// Keep deferred fact streams outside memory until the join that consumes each one.
pub(crate) struct FactSpools {
    files: BTreeMap<String, BufWriter<std::fs::File>>,
}

impl FactSpools {
    pub(crate) fn new(families: impl IntoIterator<Item = String>) -> Result<Self, String> {
        #[cfg(test)]
        super::FORBID_FACT_SPOOLS.with(|forbidden| {
            assert!(
                !forbidden.get(),
                "the native analysis session must not open a compatibility fact spool"
            );
        });
        let files = families
            .into_iter()
            .map(|family| {
                tempfile::tempfile()
                    .map(|file| (family, BufWriter::with_capacity(1024 * 1024, file)))
                    .map_err(|failure| format!("a fact spool could not be opened: {failure}"))
            })
            .collect::<Result<_, _>>()?;
        Ok(Self { files })
    }

    /// Drain one retained family in bounded batches rather than rebuilding it in memory.
    pub(crate) fn drain<Visit>(&mut self, family: &str, mut visit: Visit) -> Result<(), String>
    where
        Visit: FnMut(Vec<serde_json::Value>) -> Result<(), String>,
    {
        let mut file = self.take(family)?;
        file.rewind().map_err(|failure| {
            format!("the {family} fact spool could not be rewound: {failure}")
        })?;
        let mut batch = Vec::with_capacity(FACT_BATCH_SIZE);
        for line in BufReader::new(file).lines() {
            let line =
                line.map_err(|failure| format!("the {family} fact spool failed: {failure}"))?;
            batch
                .push(serde_json::from_str(&line).map_err(|failure| {
                    format!("a spooled {family} fact is invalid: {failure}")
                })?);
            if batch.len() == FACT_BATCH_SIZE {
                visit(std::mem::take(&mut batch))?;
            }
        }
        if !batch.is_empty() {
            visit(batch)?;
        }
        Ok(())
    }

    pub(super) fn holds(&self, family: &str) -> bool {
        self.files.contains_key(family)
    }

    pub(super) fn read(&mut self, family: &str) -> Result<Vec<serde_json::Value>, String> {
        let mut file = self.take(family)?;
        file.rewind().map_err(|failure| {
            format!("the {family} fact spool could not be rewound: {failure}")
        })?;
        BufReader::new(file)
            .lines()
            .map(|line| {
                let line =
                    line.map_err(|failure| format!("the {family} fact spool failed: {failure}"))?;
                serde_json::from_str(&line)
                    .map_err(|failure| format!("a spooled {family} fact is invalid: {failure}"))
            })
            .collect()
    }

    pub(crate) fn write(
        &mut self,
        family: &str,
        facts: Vec<serde_json::Value>,
    ) -> Result<(), String> {
        let output = self
            .files
            .get_mut(family)
            .ok_or_else(|| format!("no fact spool was opened for {family}"))?;
        for fact in facts {
            serde_json::to_writer(&mut *output, &fact)
                .map_err(|failure| format!("a {family} fact could not be spooled: {failure}"))?;
            writeln!(output)
                .map_err(|failure| format!("a {family} fact could not be spooled: {failure}"))?;
        }
        Ok(())
    }

    fn take(&mut self, family: &str) -> Result<std::fs::File, String> {
        self.files
            .remove(family)
            .ok_or_else(|| format!("no fact spool was opened for {family}"))?
            .into_inner()
            .map_err(|failure| format!("the {family} fact spool could not be flushed: {failure}"))
    }
}
