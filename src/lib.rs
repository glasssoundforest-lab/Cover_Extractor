//! TRPGシナリオなどのフォルダ / ZIP から表紙を探し、カタログ用のサムネイルを作るライブラリ。
//!
//! ```no_run
//! use cover_extractor::CoverExtractor;
//!
//! let extractor = CoverExtractor::default();
//! let cover = extractor.extract("scenario.zip".as_ref());
//! std::fs::write("cover.jpg", &cover.jpeg).unwrap();
//! ```
//!
//! # 構成
//! - [`source`] — フォルダ / ZIP を同じインターフェースで読む（ZIPはディスクに展開しない）
//! - [`names`] — ファイル名のデコード（CP932 / UTF-8）と正規化（NFC、区切り文字、ゴミファイル除外）
//! - [`rules`] — 表紙判定ルール（TOML）とキーワード照合
//! - [`select`] — 表紙候補（画像・PDFの1ページ目）の列挙と点数付け
//! - [`thumbnail`] — デコード → EXIF向き補正 → 縮小 → JPEG
//! - [`pdf`] — PDF の1ページ目の描画（`pdf` feature）
//! - [`placeholder`] — 取得失敗時の書籍風プレースホルダー
//! - [`web`] — URL（BOOTH の商品ページなど）からシナリオ情報と表紙画像を取り出す（`web` feature）
//! - [`ffi`] — DLL（C ABI）として他の言語から呼ぶためのインターフェース

pub mod error;
pub mod extractor;
pub mod info;
pub mod ffi;
pub mod limits;
pub mod names;
pub mod pdf;
pub mod placeholder;
pub mod rules;
pub mod select;
pub mod source;
pub mod thumbnail;
pub mod web;
pub mod gfx;

pub use error::{SourceError, ThumbnailError};
pub use info::{InfoExtractor, InfoRules, ScenarioInfo};
pub use extractor::{
    Choice, Confidence, Cover, CoverExtractor, CoverOrigin, EXTRACTOR_VERSION, ExtractorConfig,
    FailedAttempt, FallbackReason,
};
pub use rules::{ChoiceSettings, DEFAULT_RULES_TOML, Rules};
pub use select::{
    Candidate, CandidateKind, CandidateRanker, Evidence, ScoringRanker, ShallowFirstRanker,
};
pub use source::{
    Entry, FileSource, FolderSource, SourceAccessor, SourceFingerprint, ZipSource, fingerprint_for_path,
    open_source,
};
pub use thumbnail::{Thumbnail, ThumbnailConfig, make_thumbnail, probe_dimensions};
pub use web::{SiteFetcher, WebExtractor, WebInfo, WebPage};
