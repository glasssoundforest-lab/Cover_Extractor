use thiserror::Error;

/// ソース（フォルダ / ZIP）へのアクセスで起きるエラー。
#[derive(Debug, Error)]
pub enum SourceError {
    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("ZIP error: {0}")]
    Zip(#[from] zip::result::ZipError),

    #[error("unsupported source (not a folder or ZIP file): {0}")]
    Unsupported(String),

    /// 細工の疑いがあるため開かなかった（メモリを使い果たさせる ZIP など）。
    #[error("refused to open: {0}")]
    Refused(String),

    #[error("entry index out of range: {0}")]
    NoSuchEntry(usize),

    #[error("no such entry in source: {0}")]
    NoSuchEntryPath(String),

    #[error("cannot read entry {path}: {reason}")]
    Unreadable { path: String, reason: String },

    #[error("entry is encrypted: {0}")]
    Encrypted(String),

    #[error("entry is too large ({size} bytes, limit {limit}): {path}")]
    TooLarge { path: String, size: u64, limit: u64 },
}

/// 画像のデコード・サムネイル生成で起きるエラー。
#[derive(Debug, Error)]
pub enum ThumbnailError {
    #[error("image error: {0}")]
    Image(#[from] image::ImageError),

    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("image is too small ({width}x{height}, min edge {min_edge})")]
    TooSmall {
        width: u32,
        height: u32,
        min_edge: u32,
    },

    #[error("PDF error: {0}")]
    Pdf(String),
}
