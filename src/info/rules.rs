use std::path::Path;
use serde::Deserialize;

use crate::error::SourceError;

/// 組み込みの既定ルール。
pub const DEFAULT_INFO_RULES_TOML: &str = include_str!("../info_rules.toml");

#[derive(Debug, Clone, Deserialize)]
pub struct LabelsConfig {
    /// 題名の見出し（「タイトル：」など）。見つかれば、文字の大きさなどから推測した題名より優先する。
    #[serde(default = "default_title_labels")]
    pub title: Vec<String>,
    #[serde(default)]
    pub system: Vec<String>,
    #[serde(default)]
    pub players: Vec<String>,
    #[serde(default)]
    pub duration: Vec<String>,
    #[serde(default)]
    pub genre: Vec<String>,
    #[serde(default)]
    pub lost: Vec<String>,
    #[serde(default)]
    pub skills: Vec<String>,
    #[serde(default)]
    pub format: Vec<String>,
    #[serde(default)]
    pub summary: Vec<String>,
}

fn default_title_labels() -> Vec<String> {
    ["タイトル", "シナリオ名", "シナリオタイトル", "作品名", "作品タイトル", "題名", "商品名", "title"]
        .iter()
        .map(|s| s.to_string())
        .collect()
}

#[derive(Debug, Clone, Deserialize)]
pub struct SystemRule {
    pub name: String,
    pub r#match: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct LostRule {
    pub level: String,
    pub r#match: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct FormatRule {
    pub key: String,
    pub r#match: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct DocumentsConfig {
    pub max_documents: usize,
    pub max_lines_per_document: usize,
    #[serde(default)]
    pub prefer: Vec<String>,
    #[serde(default)]
    pub lower: Vec<String>,
    #[serde(default)]
    pub spoiler: Vec<String>,
    #[serde(default)]
    pub boundary_word: Vec<String>,
    #[serde(default)]
    pub boundary_marker: Vec<String>,
    #[serde(default)]
    pub boundary_heading: Vec<String>,
    pub boundary_short_line: usize,
    #[serde(default)]
    pub boundary_negation: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct InfoRules {
    pub version: u32,
    pub labels: LabelsConfig,
    #[serde(default)]
    pub system: Vec<SystemRule>,
    #[serde(default)]
    pub lost: Vec<LostRule>,
    #[serde(default)]
    pub format: Vec<FormatRule>,
    pub documents: DocumentsConfig,
}

impl Default for InfoRules {
    fn default() -> Self {
        toml::from_str(DEFAULT_INFO_RULES_TOML).expect("built-in info_rules.toml is valid")
    }
}

impl InfoRules {
    pub fn from_file(path: &Path) -> Result<Self, SourceError> {
        let text = std::fs::read_to_string(path)?;
        Self::from_toml(&text)
    }

    pub fn from_toml(toml_str: &str) -> Result<Self, SourceError> {
        toml::from_str(toml_str).map_err(|e| SourceError::Unsupported(format!("TOML error: {e}")))
    }
}