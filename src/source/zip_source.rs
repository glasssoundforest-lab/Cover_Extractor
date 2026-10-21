use std::fs::File;
use std::io::{BufReader, Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use zip::ZipArchive;

use super::{Entry, SourceAccessor, SourceFingerprint, identity_string, mtime_nanos};
use crate::error::SourceError;
use crate::limits::{MAX_ZIP_ENTRIES, read_limited};
use crate::names::{decode_entry_name, is_junk_path, normalize_path};

/// ZIPファイルをディスクに展開せずに読むソース。
///
/// 一覧取得は中央ディレクトリだけを読む（各エントリの本体には触れない）。
/// `read_entry` で指定されたエントリだけをメモリ上に展開する。
pub struct ZipSource {
    path: PathBuf,
    archive: ZipArchive<BufReader<File>>,
    /// `entries[i]` に対応する ZIP 内のインデックス。
    zip_indices: Vec<usize>,
    /// 暗号化されているエントリ（`entries` と同じ並び）。
    encrypted: Vec<bool>,
    entries: Vec<Entry>,
    fingerprint: SourceFingerprint,
}

impl ZipSource {
    pub fn open(path: &Path) -> Result<Self, SourceError> {
        let meta = std::fs::metadata(path)?;
        let mut file = File::open(path)?;
        check_declared_entry_count(&mut file, meta.len())?;
        file.seek(SeekFrom::Start(0))?;
        let archive = ZipArchive::new(BufReader::new(file))?;

        let mut zip_indices = Vec::new();
        let mut encrypted = Vec::new();
        let mut entries = Vec::new();

        for i in 0..archive.len() {
            // by_index_data は中央ディレクトリの情報だけを返す（本体のシークなし）。
            let Ok(data) = archive.by_index_data(i) else {
                continue;
            };
            if data.is_dir() || data.is_symlink() {
                continue;
            }
            let path = normalize_path(&decode_entry_name(data.name_raw()));
            if path.is_empty() || is_junk_path(&path) {
                continue;
            }
            entries.push(Entry {
                index: entries.len(),
                path,
                size: data.size(),
            });
            zip_indices.push(i);
            encrypted.push(data.encrypted());
        }

        let fingerprint = Self::fingerprint_from_metadata(path, &meta);

        Ok(Self {
            path: path.to_path_buf(),
            archive,
            zip_indices,
            encrypted,
            entries,
            fingerprint,
        })
    }

    /// ZIPを開かずに、ファイルのメタデータだけでフィンガープリントを作る。
    /// キャッシュ確認を高速に行うためのもの。`open` で得られる値と一致する。
    pub fn fingerprint_from_metadata(path: &Path, meta: &std::fs::Metadata) -> SourceFingerprint {
        SourceFingerprint {
            kind: "zip",
            identity: identity_string(path),
            revision: format!("{}:{}", mtime_nanos(meta), meta.len()),
        }
    }

    /// 開いたZIPファイルのパス。
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// 指定エントリが暗号化されているか（パスワード付きZIP）。
    pub fn is_encrypted(&self, index: usize) -> bool {
        self.encrypted.get(index).copied().unwrap_or(false)
    }
}

impl SourceAccessor for ZipSource {
    fn entries(&self) -> &[Entry] {
        &self.entries
    }

    fn read_entry(&mut self, index: usize, max_bytes: u64) -> Result<Vec<u8>, SourceError> {
        let entry = self
            .entries
            .get(index)
            .ok_or(SourceError::NoSuchEntry(index))?;
        if self.encrypted[index] {
            return Err(SourceError::Encrypted(entry.path.clone()));
        }
        if entry.size > max_bytes {
            return Err(SourceError::TooLarge {
                path: entry.path.clone(),
                size: entry.size,
                limit: max_bytes,
            });
        }

        let file = self.archive.by_index(self.zip_indices[index])?;
        // 申告サイズが偽装されたZIP（ZIP bomb）に備え、実際の展開量でも上限をかける。
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

/// ZIP の終端レコードが申告するファイル数を、ZIP ライブラリに渡す前に確認する。
fn check_declared_entry_count(file: &mut File, len: u64) -> Result<(), SourceError> {
    const EOCD: &[u8; 4] = b"PK\x05\x06";
    const LOCATOR: &[u8; 4] = b"PK\x06\x07";
    const EOCD64: &[u8; 4] = b"PK\x06\x06";
    const TAIL: u64 = 22 + 65_535;
    const MAX_EOCD64_GAP: u64 = 1 << 20;

    let too_many = |n: u64| {
        SourceError::Refused(format!(
            "ZIP declares {n} entries (limit {MAX_ZIP_ENTRIES})"
        ))
    };
    let u64_at = |b: &[u8], i: usize| {
        b.get(i..i + 8)
            .map(|s| u64::from_le_bytes(s.try_into().expect("8 bytes")))
    };

    let tail_start = len.saturating_sub(TAIL + 20);
    let mut tail = Vec::new();
    file.seek(SeekFrom::Start(tail_start))?;
    file.take(TAIL + 20).read_to_end(&mut tail)?;

    for p in find_all(&tail, EOCD) {
        let Some(loc) = p.checked_sub(20) else {
            continue;
        };
        if tail.get(loc..loc + 4) != Some(LOCATOR.as_slice()) {
            continue;
        }
        let Some(claimed) = u64_at(&tail, loc + 8) else {
            continue;
        };
        let locator_abs = tail_start + loc as u64;
        if claimed >= locator_abs {
            continue;
        }
        let gap = locator_abs - claimed;
        if gap > MAX_EOCD64_GAP {
            return Err(SourceError::Refused(format!(
                "ZIP64 end record is {gap} bytes before its locator"
            )));
        }
        let mut region = Vec::new();
        file.seek(SeekFrom::Start(claimed))?;
        file.take(gap).read_to_end(&mut region)?;
        for q in find_all(&region, EOCD64) {
            for field in [q + 24, q + 32] {
                if let Some(n) = u64_at(&region, field) {
                    if n > MAX_ZIP_ENTRIES {
                        return Err(too_many(n));
                    }
                }
            }
        }
    }
    Ok(())
}

fn find_all<'a>(hay: &'a [u8], needle: &'a [u8]) -> impl Iterator<Item = usize> + 'a {
    hay.windows(needle.len())
        .enumerate()
        .filter(move |(_, w)| *w == needle)
        .map(|(i, _)| i)
}