//! ストレージアクセス層。
//!
//! フォルダ・ZIP・単体ファイル（将来は Notion）を同じインターフェースで扱い、
//! 後段の判定ロジックが「どこから来たデータか」を意識しなくて済むようにする。

mod file;
mod folder;
mod zip_source;

pub use file::FileSource;
pub use folder::FolderSource;
pub use zip_source::ZipSource;

use std::path::Path;

use crate::error::SourceError;

/// ソース内の1ファイル。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    /// `SourceAccessor::read_entry` に渡すインデックス。
    pub index: usize,
    /// 正規化済みパス（UTF-8 / NFC / `/` 区切り）。
    pub path: String,
    /// 展開後のサイズ（バイト）。ZIPでは中央ディレクトリの申告値。
    pub size: u64,
}

/// キャッシュキーの材料。データ元ごとに「変更を検知できる情報」を返す。
///
/// - フォルダ / ZIP: 絶対パス + 更新日時 + サイズ
/// - Notion（将来）: ページID + `last_edited_time`
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SourceFingerprint {
    /// データ元の種類（"folder" / "zip" / "notion" など）。
    pub kind: &'static str,
    /// データ元を一意に指す文字列（絶対パスやページID）。
    pub identity: String,
    /// 変更検知用の値（更新日時やサイズを文字列化したもの）。
    pub revision: String,
}

/// フォルダ・ZIPなどを統一的に扱うためのインターフェース。
///
/// `entries()` は画像以外も含む全ファイル（ゴミファイルは除外済み）を返す。
/// 画像の絞り込みや優先順位付けは後段（`select` モジュール）の責務。
pub trait SourceAccessor: Send {
    /// ファイル一覧（ゴミファイル除外・パス正規化済み）。
    fn entries(&self) -> &[Entry];

    /// 指定エントリの中身をメモリに読み込む。`max_bytes` を超える場合はエラー。
    fn read_entry(&mut self, index: usize, max_bytes: u64) -> Result<Vec<u8>, SourceError>;

    /// キャッシュキーの材料。
    fn fingerprint(&self) -> &SourceFingerprint;
}

/// パスを見てフォルダ・ZIP・単体ファイルのどれかを判定し、適切なソースを開く。
///
/// ZIP ではないファイル（シナリオ PDF を直接指定した場合など）は、そのファイル1件だけのソースとして開く。
pub fn open_source(path: &Path) -> Result<Box<dyn SourceAccessor>, SourceError> {
    let meta = std::fs::metadata(path)?;
    if meta.is_dir() {
        return Ok(Box::new(FolderSource::open(path)?));
    }
    if meta.is_file() {
        if is_zip_file(path)? {
            return Ok(Box::new(ZipSource::open(path)?));
        }
        return Ok(Box::new(FileSource::open(path)?));
    }
    Err(SourceError::Unsupported(path.display().to_string()))
}

/// ソースを開いた場合と同じフィンガープリントを、なるべく中身を読まずに作る（キャッシュ確認用）。
pub fn fingerprint_for_path(path: &Path) -> Result<SourceFingerprint, SourceError> {
    let meta = std::fs::metadata(path)?;
    if meta.is_dir() {
        return Ok(FolderSource::open(path)?.fingerprint().clone());
    }
    if meta.is_file() && is_zip_file(path)? {
        return Ok(ZipSource::fingerprint_from_metadata(path, &meta));
    }
    Ok(FileSource::fingerprint_from_metadata(path, &meta))
}

/// 先頭のシグネチャで ZIP かどうかを判定する（拡張子に頼らない）。
fn is_zip_file(path: &Path) -> Result<bool, SourceError> {
    use std::io::Read;
    let mut sig = [0u8; 4];
    let mut f = std::fs::File::open(path)?;
    let n = f.read(&mut sig)?;
    // PK\x03\x04（通常） / PK\x05\x06（空のZIP）
    Ok(n == 4 && (sig == *b"PK\x03\x04" || sig == *b"PK\x05\x06"))
}

/// 更新日時（UNIXエポックからのナノ秒）。取得できなければ 0。
pub(crate) fn mtime_nanos(meta: &std::fs::Metadata) -> u128 {
    meta.modified()
        .ok()
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_nanos())
        .unwrap_or(0)
}

/// 絶対パス（取得できなければそのまま）を文字列化する。
pub(crate) fn identity_string(path: &Path) -> String {
    std::fs::canonicalize(path)
        .unwrap_or_else(|_| path.to_path_buf())
        .display()
        .to_string()
}
