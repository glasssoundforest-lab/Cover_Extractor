use std::path::{Path, PathBuf};

use walkdir::WalkDir;

use super::{Entry, SourceAccessor, SourceFingerprint, identity_string, mtime_nanos};
use crate::error::SourceError;
use crate::limits::{MAX_FOLDER_FILES, read_limited};
use crate::names::{is_junk_path, normalize_path};

/// 走査するフォルダの最大深さ。素材フォルダが深くネストしていても
/// 一覧取得が重くならないよう制限する。
const MAX_DEPTH: usize = 8;

/// 通常フォルダを読むソース。
pub struct FolderSource {
    root: PathBuf,
    files: Vec<PathBuf>,
    entries: Vec<Entry>,
    fingerprint: SourceFingerprint,
}

impl FolderSource {
    pub fn open(root: &Path) -> Result<Self, SourceError> {
        let root_meta = std::fs::metadata(root)?;
        let mut files = Vec::new();
        let mut entries = Vec::new();
        let mut total_size: u64 = 0;
        let mut latest_mtime = mtime_nanos(&root_meta);

        let walker = WalkDir::new(root)
            .max_depth(MAX_DEPTH)
            .follow_links(false)
            .sort_by_file_name();

        for item in walker.into_iter().filter_map(Result::ok) {
            if entries.len() >= MAX_FOLDER_FILES {
                break; // ドライブ全体などを渡されても止まるように、一定数で打ち切る
            }
            if !item.file_type().is_file() {
                continue;
            }
            let Ok(rel) = item.path().strip_prefix(root) else {
                continue;
            };
            let path = normalize_path(&rel.to_string_lossy());
            if path.is_empty() || is_junk_path(&path) {
                continue;
            }
            let Ok(meta) = item.metadata() else { continue };

            // フォルダ自体の更新日時は中のファイルの書き換えで変わらないため、
            // 全ファイルの合計サイズと最新更新日時を変更検知に使う。
            total_size = total_size.saturating_add(meta.len());
            latest_mtime = latest_mtime.max(mtime_nanos(&meta));

            entries.push(Entry {
                index: files.len(),
                path,
                size: meta.len(),
            });
            files.push(item.into_path());
        }

        let fingerprint = SourceFingerprint {
            kind: "folder",
            identity: identity_string(root),
            revision: format!("{latest_mtime}:{total_size}:{}", entries.len()),
        };

        Ok(Self {
            root: root.to_path_buf(),
            files,
            entries,
            fingerprint,
        })
    }

    /// 開いたフォルダのパス。
    pub fn root(&self) -> &Path {
        &self.root
    }
}

impl SourceAccessor for FolderSource {
    fn entries(&self) -> &[Entry] {
        &self.entries
    }

    fn read_entry(&mut self, index: usize, max_bytes: u64) -> Result<Vec<u8>, SourceError> {
        let entry = self
            .entries
            .get(index)
            .ok_or(SourceError::NoSuchEntry(index))?;
        // 一覧取得後に FIFO やデバイスに差し替えられていたら開かない（開いた時点で止まることがあるため）
        if !std::fs::symlink_metadata(&self.files[index])?.is_file() {
            return Err(SourceError::Unsupported(format!(
                "not a regular file: {}",
                entry.path
            )));
        }
        let file = std::fs::File::open(&self.files[index])?;
        // 一覧取得後にファイルが差し替えられても上限を超えて読まないよう、上限付きで読む。
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
