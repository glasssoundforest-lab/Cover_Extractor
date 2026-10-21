//! シナリオ情報（システム・人数・時間など）の抽出。
//!
//! 2段構成:
//! 1. 形式ごとのテキスト抽出器（`text`）が、文書（txt / md / html / json / pdf）を行にする
//! 2. 共通の解析器（`fields`）が、正規化した行から「見出し: 値」を探して項目を読み取る
//!
//! 見出しの言い換えやシステム名は `info_rules.toml` で変えられる。
//! ネタバレの文書は読まず、文書の途中の「以下ネタバレ」などより後ろも読まない。

mod extract;
pub mod fields;
pub mod normalize;
pub mod rules;
pub mod text;

pub use extract::{INFO_EXTRACTOR_VERSION, InfoExtractor, SynopsisCandidate};
pub use fields::{DurationInfo, InfoValue, PlayerCount, ScenarioInfo};
pub use rules::{DEFAULT_INFO_RULES_TOML, InfoRules};
pub use text::{DocLine, DocText, TextExtractor};
