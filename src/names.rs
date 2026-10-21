//! エントリ名（ファイルパス）のデコードと正規化。

use encoding_rs::SHIFT_JIS;
use unicode_normalization::UnicodeNormalization;

/// 表紙候補として扱う画像の拡張子（小文字）。
pub const IMAGE_EXTENSIONS: &[&str] = &["jpg", "jpeg", "png", "webp", "gif", "bmp"];

/// ZIPエントリの生バイト列を文字列にデコードする。
pub fn decode_entry_name(raw: &[u8]) -> String {
    if let Ok(s) = std::str::from_utf8(raw) {
        return s.to_owned();
    }
    if let Some(s) = SHIFT_JIS.decode_without_bom_handling_and_without_replacement(raw) {
        return s.into_owned();
    }
    String::from_utf8_lossy(raw).into_owned()
}

/// パスを比較用の正規形に揃える。
pub fn normalize_path(path: &str) -> String {
    let nfc: String = path.nfc().collect();
    nfc.replace('\\', "/")
        .split('/')
        .filter(|seg| !seg.is_empty() && *seg != ".")
        .collect::<Vec<_>>()
        .join("/")
}

/// OSやツールが自動生成する、中身が画像ではないファイルかどうか。
pub fn is_junk_path(normalized: &str) -> bool {
    normalized.split('/').any(|seg| {
        seg == "__MACOSX"
            || seg.starts_with('.')
            || seg.eq_ignore_ascii_case("thumbs.db")
            || seg.eq_ignore_ascii_case("desktop.ini")
    })
}

/// 拡張子から画像ファイルかどうかを判定する。
pub fn is_image_path(normalized: &str) -> bool {
    extension(normalized)
        .map(|ext| IMAGE_EXTENSIONS.contains(&ext.as_str()))
        .unwrap_or(false)
}

/// 小文字化した拡張子。
pub fn extension(normalized: &str) -> Option<String> {
    let name = file_name(normalized);
    let (stem, ext) = name.rsplit_once('.')?;
    if stem.is_empty() {
        return None;
    }
    Some(ext.to_ascii_lowercase())
}

/// パス末尾のファイル名部分。
pub fn file_name(normalized: &str) -> &str {
    normalized.rsplit('/').next().unwrap_or(normalized)
}

/// ディレクトリの深さ（ルート直下のファイルが 0）。
pub fn depth(normalized: &str) -> usize {
    normalized.matches('/').count()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_cp932_names() {
        let (raw, _, _) = SHIFT_JIS.encode("表紙.png");
        assert_eq!(decode_entry_name(&raw), "表紙.png");
    }

    #[test]
    fn cp932_trail_byte_backslash_is_not_a_separator() {
        let (raw, _, _) = SHIFT_JIS.encode("ソード/表紙.jpg");
        let decoded = decode_entry_name(&raw);
        assert_eq!(normalize_path(&decoded), "ソード/表紙.jpg");
    }

    #[test]
    fn keeps_utf8_names() {
        assert_eq!(decode_entry_name("タイトル.jpg".as_bytes()), "タイトル.jpg");
    }

    #[test]
    fn normalizes_nfd_to_nfc() {
        let nfd: String = "ダンジョン/表紙.png".nfd().collect();
        assert_ne!(nfd, "ダンジョン/表紙.png");
        assert_eq!(normalize_path(&nfd), "ダンジョン/表紙.png");
    }

    #[test]
    fn normalizes_separators_and_prefixes() {
        assert_eq!(normalize_path("./a\\b//c.png"), "a/b/c.png");
        assert_eq!(normalize_path("/root.png"), "root.png");
    }

    #[test]
    fn detects_junk() {
        assert!(is_junk_path("__MACOSX/scenario/._cover.png"));
        assert!(is_junk_path("scenario/._cover.png"));
        assert!(is_junk_path("scenario/.DS_Store"));
        assert!(is_junk_path("scenario/Thumbs.db"));
        assert!(is_junk_path("scenario/THUMBS.DB"));
        assert!(!is_junk_path("scenario/cover.png"));
    }

    #[test]
    fn detects_images() {
        assert!(is_image_path("a/COVER.JPG"));
        assert!(is_image_path("表紙.webp"));
        assert!(!is_image_path("readme.txt"));
        assert!(!is_image_path("a/.png"));
        assert!(!is_image_path("noext"));
    }

    #[test]
    fn computes_depth() {
        assert_eq!(depth("cover.png"), 0);
        assert_eq!(depth("a/b/cover.png"), 2);
    }
}