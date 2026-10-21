//! 表紙判定ルール（TOML）の読み込みと、パスに対するキーワード照合。

use serde::Deserialize;
use unicode_normalization::UnicodeNormalization;

/// 組み込みの既定ルール。
pub const DEFAULT_RULES_TOML: &str = include_str!("rules.toml");

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Rules {
    pub version: u32,
    pub min_score: i32,
    pub base: BaseScores,
    pub adjust: Adjustments,
    /// 判定に迷ったときに出す選択肢の設定（省略時は既定値）。
    #[serde(default)]
    pub choices: ChoiceSettings,
    #[serde(rename = "group", default)]
    pub groups: Vec<KeywordGroup>,
}

/// 判定に迷ったときの選択肢の設定。
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields, default)]
pub struct ChoiceSettings {
    pub min_confident_score: i32,
    pub min_margin: i32,
    pub count: usize,
    pub per_section: usize,
    pub browse_floor: i32,
    pub max_attempts: usize,
}

impl Default for ChoiceSettings {
    fn default() -> Self {
        Self {
            min_confident_score: 50,
            min_margin: 15,
            count: 4,
            per_section: 1,
            browse_floor: -150,
            max_attempts: 16,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BaseScores {
    pub image: i32,
    pub pdf_first_page: i32,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Adjustments {
    pub per_depth: i32,
    pub sequence_first_bonus: i32,
    pub sequence_later_penalty: i32,
    pub extreme_aspect_ratio: f32,
    pub extreme_aspect_penalty: i32,
    pub plain_dominant_ratio: f32,
    pub plain_page_penalty: i32,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct KeywordGroup {
    pub name: String,
    pub score: i32,
    pub words: Vec<String>,
    #[serde(default)]
    pub targets: Option<Vec<Target>>,
    #[serde(default)]
    pub scope: Scope,
    #[serde(default)]
    pub max_per_dir: Option<usize>,
    #[serde(default)]
    pub exclude: bool,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Scope {
    #[default]
    Path,
    Name,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Target {
    Image,
    Pdf,
}

impl KeywordGroup {
    pub fn applies_to(&self, target: Target) -> bool {
        self.targets.as_ref().is_none_or(|t| t.contains(&target))
    }
}

impl Rules {
    pub fn from_toml(text: &str) -> Result<Self, toml::de::Error> {
        toml::from_str(text)
    }
}

impl Default for Rules {
    fn default() -> Self {
        Self::from_toml(DEFAULT_RULES_TOML).expect("built-in rules.toml must be valid")
    }
}

#[derive(Debug, Clone, Default)]
struct SegmentTerms {
    words: Vec<String>,
    text: String,
}

impl SegmentTerms {
    fn new(seg: &str) -> Self {
        let nfkc: String = seg.nfkc().collect();
        let tokens = ascii_tokens(&nfkc);
        let mut words: Vec<String> = tokens
            .windows(2)
            .map(|p| format!("{}{}", p[0], p[1]))
            .collect();
        words.extend(tokens);
        Self {
            words,
            text: nfkc.to_lowercase(),
        }
    }

    fn matches(&self, kw: &str) -> bool {
        let norm = normalize_keyword(kw);
        if norm.is_ascii() {
            self.words.iter().any(|w| w == &norm)
        } else {
            self.text.contains(&norm)
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct PathTerms {
    name: SegmentTerms,
    dirs: Vec<SegmentTerms>,
}

impl PathTerms {
    pub fn new(normalized_path: &str) -> Self {
        let (dirs, name) = match normalized_path.rsplit_once('/') {
            Some((d, n)) => (d.split('/').map(SegmentTerms::new).collect(), n),
            None => (Vec::new(), normalized_path),
        };
        Self {
            name: SegmentTerms::new(strip_extension(name)),
            dirs,
        }
    }

    pub fn matches(&self, keyword: &str) -> bool {
        self.matches_in(keyword, Scope::Path)
    }

    pub fn matches_in(&self, keyword: &str, scope: Scope) -> bool {
        self.matches_name(keyword) || (scope == Scope::Path && self.matches_dirs(keyword))
    }

    pub fn matches_name(&self, keyword: &str) -> bool {
        self.name.matches(keyword)
    }

    pub fn matches_dirs(&self, keyword: &str) -> bool {
        self.dirs.iter().any(|d| d.matches(keyword))
    }
}

fn normalize_keyword(keyword: &str) -> String {
    keyword.nfkc().collect::<String>().to_lowercase()
}

fn strip_extension(name: &str) -> &str {
    match name.rsplit_once('.') {
        Some((stem, _)) if !stem.is_empty() => stem,
        _ => name,
    }
}

pub fn ascii_tokens(s: &str) -> Vec<String> {
    #[derive(PartialEq, Clone, Copy)]
    enum Class {
        Upper,
        Lower,
        Digit,
        Other,
    }
    let class = |c: char| {
        if c.is_ascii_uppercase() {
            Class::Upper
        } else if c.is_ascii_lowercase() {
            Class::Lower
        } else if c.is_ascii_digit() {
            Class::Digit
        } else {
            Class::Other
        }
    };

    let chars: Vec<char> = s.chars().collect();
    let mut tokens = Vec::new();
    let mut current = String::new();
    for (i, &c) in chars.iter().enumerate() {
        let cls = class(c);
        if cls == Class::Other {
            if !current.is_empty() {
                tokens.push(std::mem::take(&mut current).to_ascii_lowercase());
            }
            continue;
        }
        if let Some(prev) = current.chars().last() {
            let pc = class(prev);
            let boundary = (pc == Class::Digit) != (cls == Class::Digit)
                || (pc == Class::Lower && cls == Class::Upper)
                || (pc == Class::Upper
                    && cls == Class::Upper
                    && chars.get(i + 1).is_some_and(|n| n.is_ascii_lowercase()));
            if boundary {
                tokens.push(std::mem::take(&mut current).to_ascii_lowercase());
            }
        }
        current.push(c);
    }
    if !current.is_empty() {
        tokens.push(current.to_ascii_lowercase());
    }
    tokens
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_rules_parse() {
        let r = Rules::default();
        assert!(r.groups.iter().any(|g| g.name == "cover"));
    }

    #[test]
    fn tokenizes_ascii_words() {
        assert_eq!(ascii_tokens("EndCard_GM"), ["end", "card", "gm"]);
        assert_eq!(ascii_tokens("onasora1102_a"), ["onasora", "1102", "a"]);
        assert_eq!(ascii_tokens("GMGuide"), ["gm", "guide"]);
        assert_eq!(ascii_tokens("GMガイド"), ["gm"]);
        assert_eq!(ascii_tokens("HO1"), ["ho", "1"]);
    }

    #[test]
    fn matches_words_and_japanese_substrings() {
        let t = PathTerms::new("忘却レストラン/03_エンドカード&アンケート/EndCard_GM.PNG");
        assert!(t.matches("endcard"));
        assert!(t.matches("エンドカード"));
        assert!(t.matches("gm"));
        assert!(!t.matches("png"), "拡張子は対象外");

        assert!(t.matches("アンケート"));
        assert!(
            !t.matches_in("アンケート", Scope::Name),
            "ファイル名だけなら一致しない"
        );

        let t = PathTerms::new("s/background.png");
        assert!(t.matches("background"));
        assert!(!t.matches("back"), "単語の一部には一致しない");
    }

    #[test]
    fn nfkc_normalizes_full_width_and_half_width_kana() {
        let t = PathTerms::new("ＣＯＶＥＲ.png");
        assert!(t.matches("cover"));
        let t = PathTerms::new("ﾄﾚｰﾗｰ1.png");
        assert!(t.matches("トレーラー"));
    }
}