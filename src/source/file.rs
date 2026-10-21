use std::path::{Path, PathBuf};

use super::{Entry, SourceAccessor, SourceFingerprint, identity_string, mtime_nanos};
use crate::error::SourceError;
use crate::limits::read_limited;
use crate::names::normalize_path;

/// ZIP ではない単体のファイル（シナリオ PDF を直接指定した場合など）を、
/// 1件だけ入ったソースとして読む。
pub struct FileSource {
    path: PathBuf,
    entries: Vec<Entry>,
    fingerprint: SourceFingerprint,
}

impl FileSource {
    pub fn open(path: &Path) -> Result<Self, SourceError> {
        let meta = std::fs::metadata(path)?;
        if !meta.is_file() {
            return Err(SourceError::Unsupported(path.display().to_string()));
        }
        let name = path
            .file_name()
            .map(|n| normalize_path(&n.to_string_lossy()))
            .unwrap_or_default();
        Ok(Self {
            path: path.to_path_buf(),
            entries: vec![Entry {
                index: 0,
                path: name,
                size: meta.len(),
            }],
            fingerprint: Self::fingerprint_from_metadata(path, &meta),
        })
    }

    /// ファイルを開かずに、メタデータだけでフィンガープリントを作る。`open` で得られる値と一致する。
    pub fn fingerprint_from_metadata(path: &Path, meta: &std::fs::Metadata) -> SourceFingerprint {
        SourceFingerprint {
            kind: "file",
            identity: identity_string(path),
            revision: format!("{}:{}", mtime_nanos(meta), meta.len()),
        }
    }

    /// 開いたファイルのパス。
    pub fn path(&self) -> &Path {
        &self.path
    }
}

impl SourceAccessor for FileSource {
    fn entries(&self) -> &[Entry] {
        &self.entries
    }

    fn read_entry(&mut self, index: usize, max_bytes: u64) -> Result<Vec<u8>, SourceError> {
        let entry = self
            .entries
            .get(index)
            .ok_or(SourceError::NoSuchEntry(index))?;
        if !std::fs::symlink_metadata(&self.path)?.is_file() && !std::fs::metadata(&self.path)?.is_file() {
            return Err(SourceError::Unsupported(format!(
                "not a regular file: {}",
                entry.path
            )));
        }
        let file = std::fs::File::open(&self.path)?;
        read_limited(file, max_bytes, entry.size)?.map_err(|size| SourceError::TooLarge {
            path: entry.path.clone(),
            size,
            limit: max_bytes,
        })
    }

    fn fingerprint(&self) -> &SourceFingerprint {
        &self.fingerprint
    }
}
