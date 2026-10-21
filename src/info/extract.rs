//! 文書を読んで、シナリオ情報（題名・システム・人数・時間・概要・あらすじ）を組み立てる。
//!
//! 流れ:
//! 1. ソース内の文書（txt / md / html / json / pdf）を、ファイル名の手がかりで優先度順に並べる
//!    （ネタバレ・ハンドアウトは読まない）
//! 2. 各文書を行に分け、`normalize_line` で正規化した行に対して見出しを照合する
//!    （PDF 特有の「⼈」「︓」や、字間に入った空白をここで吸収する）
//! 3. 文書の途中に「以下ネタバレ」などの境界があれば、そこから先は読まない
//! 4. 項目ごとに、優先度の高い文書で最初に見つかった値を採る

use std::collections::HashMap;
use std::path::Path;

use crate::error::SourceError;
use crate::info::fields::{DurationInfo, InfoValue, PlayerCount, ScenarioInfo};
use crate::info::normalize::{clean_display, normalize_line};
use crate::info::rules::InfoRules;
use crate::info::text::{DocText, MAX_DOCUMENT_BYTES, extract_document, is_document_path};
use crate::limits::run_on_worker;
use crate::names::{depth, extension};
use crate::rules::PathTerms;
use crate::select::common_root_depth;
use crate::source::{SourceAccessor, open_source};

/// 情報抽出のバージョン。出力に影響する変更をしたら上げる（キャッシュ無効化用）。
pub const INFO_EXTRACTOR_VERSION: &str = "info-extractor/2";

/// 題名を探す行数（文書の先頭から）。
const TITLE_SCAN_LINES: usize = 40;
/// システム・人数・時間を探す行数。
const META_SCAN_LINES: usize = 250;
/// 推奨技能が複数行にわたる場合に読む最大行数。
const SKILL_MAX_LINES: usize = 6;
/// あらすじの上限。
const SYNOPSIS_MAX_LINES: usize = 60;
const SYNOPSIS_MAX_CHARS: usize = 2000;
/// 見出しの値の上限（長すぎるものは本文とみなす）。
const VALUE_MAX_CHARS: usize = 120;
const TITLE_MAX_CHARS: usize = 50;

/// 見出し行の先頭によく付く記号。
const HEADING_MARKS: &[char] = &[
    '▼', '▽', '◆', '◇', '♢', '♦', '●', '○', '◎', '■', '□', '▲', '△', '★', '☆', '►', '▶', '#', '[',
];

/// 値の前後から取り除く区切り文字。
const VALUE_TRIM: &[char] = &[' ', '/', '|', '・', ',', '、', ':', ';'];

/// 題名にならない行に含まれる語（正規化・小文字化した行と照合）。
const TITLE_EXCLUDE: &[&str] = &[
    "trpg", "シナリオ", "ルールブック", "権利", "二次創作", "お読み", "読んで", "ご購入", "購入", "ありがとう",
    "注意", "目次", "規約", "更新", "配布", "利用", "使用", "クレジット", "ネタバレ", "http", "www.", "©", "(c)",
    "copyright", "ver.", "version", "著作", "作者", "制作", "製作", "発行", "page", "ページ", "表紙",
];

/// あらすじの区切りになる見出し（項目の見出し語のほかに）。
const SECTION_WORDS: &[&str] = &[
    "背景", "真相", "事件の真相", "登場人物", "npc", "探索者", "探索者について", "pc", "ハンドアウト", "注意事項",
    "注意", "目次", "クレジット", "使用素材", "素材", "更新履歴", "前提", "舞台", "舞台設定", "用語", "用語集",
    "シナリオの流れ", "流れ", "タイムライン", "補足", "その他", "エンディング", "kp情報", "gm情報", "推奨",
    "準推奨技能", "シナリオ情報", "基本情報", "情報", "はじめに", "このシナリオについて", "概要",
];

/// GM なしで遊べることを示す語（人数が書かれていないときの手がかり）。
const GMLESS_WORDS: &[&str] = &["gmレス", "kpレス", "ソロシナリオ", "ソロ用", "ソロプレイ", "ソロ向け", "1人用"];

/// あらすじの見出しの優先順位（小さいほど優先）。
///
/// 0: 「あらすじ」「ストーリー」など、あらすじそのものの見出し
/// 1: 「概要」（人数などの仕様が書かれていない、文章だけの欄に限る）
/// 2: 「背景」
/// 3: 「導入」「イントロ」（GM 向けの進行の説明が多いので最後）
const SYNOPSIS_TIERS: u8 = 4;

fn summary_tier(label: &str) -> u8 {
    if label.contains("概要") {
        1
    } else if label.contains("背景") || label == "background" {
        2
    } else if label.contains("導入") || label.starts_with("イントロ") || label == "introduction" {
        3
    } else {
        0
    }
}

/// あらすじの候補（見出しごと）。
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct SynopsisCandidate {
    /// 見出し（「あらすじ」「トレーラー」「概要」など）。
    pub label: String,
    pub text: String,
    /// 優先順位（0: あらすじ・トレーラーなど、1: 概要、2: 背景、3: 導入）。
    pub tier: u8,
}

/// 正規化済みの1行。
#[derive(Debug, Clone)]
struct Line {
    /// 元の行（前後の空白だけ除いたもの）。見出しと値の間の空白を見るために使う。
    raw: String,
    /// 表示用（PDF の特殊文字だけ直したもの）。
    display: String,
    /// 照合用（NFKC・空白除去済み）。
    norm: String,
    /// 照合用の ASCII 小文字版（`norm` とバイト位置が一致する）。
    lower: String,
    size: f32,
    page: u16,
}

/// 見出しから値を探した結果。
struct Found {
    value: String,
    raw: String,
}

/// 文書をまたいで集める途中の状態。
#[derive(Default)]
struct Pending {
    /// PDF で、本文より大きな文字で書かれていた題名候補（「タイトル：」の見出しがなければ使う）。
    size_title: Option<InfoValue<String>>,
    /// 1行目付近から拾った弱い題名候補。
    weak_title: Option<InfoValue<String>>,
    /// 本文中にシステム名が出てきた場合の候補（見出し付きのものがなければ使う）。
    fallback_system: Option<InfoValue<String>>,
    /// 「GMレス」などの記述（人数の見出しがなければ使う）。
    gmless: Option<InfoValue<PlayerCount>>,
    /// 「概要」「背景」「導入」の見出しから拾ったあらすじと、その優先順位（「あらすじ」見出しがなければ使う）。
    weak_synopsis: Option<InfoValue<String>>,
    weak_synopsis_tier: u8,
}

pub struct InfoExtractor {
    rules: InfoRules,
    /// 見出し語（ASCII 小文字化・長い順）。
    labels: Labels,
}

#[derive(Default)]
struct Labels {
    title: Vec<String>,
    system: Vec<String>,
    players: Vec<String>,
    duration: Vec<String>,
    genre: Vec<String>,
    lost: Vec<String>,
    skills: Vec<String>,
    semi_skills: Vec<String>,
    format: Vec<String>,
    summary: Vec<String>,
    /// すべての見出し語（値の切れ目・見出し行の判定用）。
    all: Vec<String>,
}

fn prepare_labels(list: &[String]) -> Vec<String> {
    let mut v: Vec<String> = list
        .iter()
        .map(|l| normalize_line(l).to_ascii_lowercase())
        .filter(|l| !l.is_empty())
        .collect();
    v.sort_by(|a, b| b.len().cmp(&a.len()).then(a.cmp(b)));
    v.dedup();
    v
}

impl Labels {
    fn new(rules: &InfoRules) -> Self {
        let l = &rules.labels;
        let semi: Vec<String> = ["準推奨技能", "準推奨スキル", "準推奨", "あると良い技能", "あると便利な技能"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let skills: Vec<String> = l.skills.iter().filter(|s| !semi.contains(s)).cloned().collect();
        let mut all_src: Vec<String> = Vec::new();
        for list in [&l.title, &l.system, &l.players, &l.duration, &l.genre, &l.lost, &l.skills, &l.format, &l.summary, &semi] {
            all_src.extend(list.iter().cloned());
        }
        Self {
            title: prepare_labels(&l.title),
            system: prepare_labels(&l.system),
            players: prepare_labels(&l.players),
            duration: prepare_labels(&l.duration),
            genre: prepare_labels(&l.genre),
            lost: prepare_labels(&l.lost),
            skills: prepare_labels(&skills),
            semi_skills: prepare_labels(&semi),
            format: prepare_labels(&l.format),
            summary: prepare_labels(&l.summary),
            all: prepare_labels(&all_src),
        }
    }
}

impl Default for InfoExtractor {
    fn default() -> Self {
        Self::new()
    }
}

impl InfoExtractor {
    pub fn new() -> Self {
        Self::with_rules(InfoRules::default())
    }

    pub fn with_rules(rules: InfoRules) -> Self {
        let labels = Labels::new(&rules);
        Self { rules, labels }
    }

    pub fn from_rules_file(path: &Path) -> Result<Self, SourceError> {
        Ok(Self::with_rules(InfoRules::from_file(path)?))
    }

    pub fn from_toml(toml_str: &str) -> Result<Self, SourceError> {
        Ok(Self::with_rules(InfoRules::from_toml(toml_str)?))
    }

    pub fn rules(&self) -> &InfoRules {
        &self.rules
    }

    /// フォルダ・ZIP・単体ファイル（PDF など）のパスから情報を取り出す。
    pub fn extract(&self, path: &Path) -> Result<ScenarioInfo, SourceError> {
        let mut source = open_source(path)?;
        self.extract_from(source.as_mut())
    }

    /// 読む文書と、そこから取り出した行を返す（調査用）。
    pub fn document_lines(&self, path: &Path) -> Result<Vec<(String, Result<DocText, String>)>, SourceError> {
        let mut source = open_source(path)?;
        let docs = self.ordered_documents(source.entries());
        Ok(docs
            .into_iter()
            .take(self.rules.documents.max_documents)
            .map(|(index, path)| {
                let text = read_document(source.as_mut(), index, &path);
                (path, text)
            })
            .collect())
    }

    /// 文書ではないテキスト（URL から取った説明文など）から情報を取り出す。読み取り方は文書の場合と同じ。
    pub fn extract_text(&self, source_path: &str, lines: &[String]) -> ScenarioInfo {
        let doc = DocText {
            is_pdf: false,
            lines: lines.iter().map(|t| crate::info::text::DocLine { text: t.clone(), size: 0.0, page: 0 }).collect(),
        };
        let mut info = ScenarioInfo::default();
        let mut pending = Pending::default();
        let lines = self.prepare_lines(&doc);
        if !lines.is_empty() {
            self.scan_document(source_path, &lines, false, &mut info, &mut pending);
        }
        if info.title.is_none() {
            info.title = pending.size_title.or(pending.weak_title);
        }
        if info.system.is_none() {
            info.system = pending.fallback_system;
        }
        if info.players.is_none() {
            info.players = pending.gmless;
        }
        if info.synopsis.is_none() {
            info.synopsis = pending.weak_synopsis;
        }
        info
    }

    /// テキストの中の「タイトル：」「商品名：」などの見出し付きの題名だけを探す（推測した題名は返さない）。
    pub fn labeled_title_in(&self, source_lines: &[String]) -> Option<String> {
        let doc = DocText {
            is_pdf: false,
            lines: source_lines.iter().map(|t| crate::info::text::DocLine { text: t.clone(), size: 0.0, page: 0 }).collect(),
        };
        let lines = self.prepare_lines(&doc);
        let ctx = DocContext::new(&lines, false);
        self.labeled_title(&lines, &ctx).map(|(t, _)| t)
    }

    /// 商品名・ページの題名から題名を取り出す（「クトゥルフ神話TRPG「霧の山荘」」→「霧の山荘」）。
    pub fn title_from_name(&self, name: &str) -> Option<String> {
        let name = clean_display(name);
        if let Some(inner) = bracketed(&name) {
            return Some(inner);
        }
        let t = clean_heading(&name).to_string();
        (!t.is_empty()).then_some(t)
    }

    /// 文字列（商品名など）に含まれるシステム名を、出てくる順に返す（`info_rules.toml` の `[[system]]` の `name`）。
    ///
    /// 英数字の語は単語として照合する（"CoC" は "Cocoa" には一致しない）。
    /// 「7版」「7th」のように数字で始まる語や「版」を含む語は、題名の中では誤りやすいので使わない。
    pub fn systems_in(&self, text: &str) -> Vec<String> {
        let hay = normalize_line(text).to_ascii_lowercase();
        // 上の規則から順に照合し、すでに一致した部分と重なる一致は数えない
        // （「新クトゥルフ神話TRPG」の中の「クトゥルフ神話TRPG」を、別のシステムとして数えないように）
        let mut taken: Vec<(usize, usize)> = Vec::new();
        let mut found: Vec<(usize, String)> = Vec::new();
        for rule in &self.rules.system {
            let mut best: Option<(usize, usize)> = None;
            for m in rule.r#match.iter().filter(|m| usable_title_word(m)) {
                let needle = normalize_line(m).to_ascii_lowercase();
                for p in find_words(&hay, &needle) {
                    let span = (p, p + needle.len());
                    if taken.iter().any(|&(a, b)| span.0 < b && a < span.1) {
                        continue;
                    }
                    if best.is_none_or(|(bp, be)| p < bp || (p == bp && span.1 > be)) {
                        best = Some(span);
                    }
                }
            }
            if let Some(span) = best {
                taken.push(span);
                found.push((span.0, rule.name.clone()));
            }
        }
        found.sort();
        found.into_iter().map(|(_, n)| n).collect()
    }

    /// 商品名・ページの題名から、システム名や「シナリオ」「DL版」などの説明を取り除いて題名にする。
    ///
    /// - 「CoCシナリオ集「霧の山荘」【DLデータ付き】」→「霧の山荘」（括弧の外が説明だけなら、括弧の中）
    /// - 「【CoC6】霧の山荘」「霧の山荘（CoC7版対応）」→「霧の山荘」（説明だけの括弧は消す）
    /// - 「マーダーミステリー あやかし夜行奇譚」→「あやかし夜行奇譚」（前後の区切られた説明は消す）
    /// - 「クトゥルフの呼び声」→ そのまま（題名の一部になっている語は消さない）
    pub fn strip_system_words(&self, title: &str) -> Option<String> {
        let mut words: Vec<String> = self
            .rules
            .system
            .iter()
            .flat_map(|r| r.r#match.iter().chain(std::iter::once(&r.name)))
            .filter(|m| usable_title_word(m))
            .map(|m| normalize_line(m).to_ascii_lowercase())
            .collect();
        words.sort_by(|a, b| b.len().cmp(&a.len()));
        words.dedup();
        let is_noise = |s: &str| {
            let mut rest = s.to_ascii_lowercase();
            for w in words.iter().map(String::as_str).chain(TITLE_NOISE_WORDS.iter().copied()) {
                rest = remove_word(&rest, w);
            }
            rest.chars().all(|c| !c.is_alphanumeric() || c.is_ascii_digit() || "第版用集新".contains(c))
        };

        // 1. 説明だけの括弧（【CoC6】（7版対応）[DL版] など）を消す
        // 全角英数字などは半角にするが、題名の中の空白は残す（normalize_line は日本語の前後の空白を消すので使わない）
        let mut t: String = {
            use unicode_normalization::UnicodeNormalization;
            crate::info::normalize::fix_pdf_chars(title).nfkc().collect::<String>().split_whitespace().collect::<Vec<_>>().join(" ")
        };
        for (open, close) in [('【', '】'), ('[', ']'), ('(', ')'), ('〔', '〕'), ('《', '》'), ('≪', '≫'), ('<', '>')] {
            let mut out = String::new();
            let mut rest = t.as_str();
            while let Some(a) = rest.find(open) {
                let Some(b) = rest[a..].find(close).map(|b| a + b) else { break };
                let inner = &rest[a + open.len_utf8()..b];
                let lower = inner.to_ascii_lowercase();
                let noise = is_noise(inner) || BRACKET_NOISE_WORDS.iter().any(|w| lower.contains(w));
                out.push_str(&rest[..a]);
                if !noise {
                    out.push_str(&rest[a..b + close.len_utf8()]);
                }
                rest = &rest[b + close.len_utf8()..];
            }
            out.push_str(rest);
            t = out;
        }

        // 2. 「」『』【】があり、その外が説明だけなら、括弧の中を題名にする（「CoCシナリオ【天使の七日】」→「天使の七日」）
        for (open, close) in [('『', '』'), ('「', '」'), ('【', '】')] {
            if let (Some(a), Some(b)) = (t.find(open), t.rfind(close)) {
                if a < b {
                    let inner = t[a + open.len_utf8()..b].trim();
                    let outside = format!("{} {}", &t[..a], &t[b + close.len_utf8()..]);
                    if !inner.is_empty() && is_noise(&outside) {
                        return Some(inner.to_string());
                    }
                }
            }
        }

        // 3. 空白や「/」「|」で区切られた前後の説明を消す
        let tokens: Vec<&str> = t.split(|c: char| c.is_whitespace() || matches!(c, '/' | '|' | ':')).filter(|x| !x.is_empty()).collect();
        let start = tokens.iter().position(|x| !is_noise(x)).unwrap_or(tokens.len());
        let end = tokens.iter().rposition(|x| !is_noise(x)).map_or(start, |e| e + 1);
        let joined = tokens.get(start..end).map(|x| x.join(" ")).unwrap_or_default();
        let cleaned = clean_heading(&joined).to_string();
        (!cleaned.is_empty()).then_some(cleaned)
    }

    pub fn extract_from(&self, source: &mut dyn SourceAccessor) -> Result<ScenarioInfo, SourceError> {
        let mut info = ScenarioInfo::default();
        let mut pending = Pending::default();

        let docs = self.ordered_documents(source.entries());
        for (index, path) in docs.into_iter().take(self.rules.documents.max_documents) {
            let Ok(doc) = read_document(source, index, &path) else {
                continue;
            };
            let lines = self.prepare_lines(&doc);
            if lines.is_empty() {
                continue;
            }
            self.scan_document(&path, &lines, doc.is_pdf, &mut info, &mut pending);
        }

        if info.title.is_none() {
            info.title = pending.size_title.or(pending.weak_title);
        }
        if info.system.is_none() {
            info.system = pending.fallback_system;
        }
        if info.players.is_none() {
            info.players = pending.gmless;
        }
        if info.synopsis.is_none() {
            info.synopsis = pending.weak_synopsis;
        }
        Ok(info)
    }

    // ------------------------------------------------------------ 文書の選択

    /// 読む文書を優先度順に並べる。ネタバレ・ハンドアウトは除く。
    fn ordered_documents(&self, entries: &[crate::source::Entry]) -> Vec<(usize, String)> {
        let strip = common_root_depth(entries);
        let d = &self.rules.documents;
        let mut docs: Vec<(i32, usize, u8, String, usize)> = Vec::new();
        for e in entries {
            if !is_document_path(&e.path) {
                continue;
            }
            // ZIP 全体を包むルートフォルダの名前は照合に使わない（題名に「真相」などが入っていても読めるように）。
            let rel: String = e.path.split('/').skip(strip).collect::<Vec<_>>().join("/");
            let rel = if rel.is_empty() { e.path.clone() } else { rel };
            let terms = PathTerms::new(&rel);
            if d.spoiler.iter().any(|w| terms.matches(w)) {
                continue;
            }
            let mut score = 0;
            if d.prefer.iter().any(|w| terms.matches(w)) {
                score += 10;
            }
            if d.lower.iter().any(|w| terms.matches(w)) {
                score -= 10;
            }
            let kind = match extension(&e.path).as_deref() {
                Some("pdf") => 0,
                Some("txt" | "text" | "md" | "markdown") => 1,
                Some("html" | "htm" | "xhtml") => 2,
                _ => 3,
            };
            docs.push((score, depth(&rel), kind, e.path.clone(), e.index));
        }
        docs.sort_by(|a, b| b.0.cmp(&a.0).then(a.1.cmp(&b.1)).then(a.2.cmp(&b.2)).then(a.3.cmp(&b.3)));
        docs.into_iter().map(|(_, _, _, path, index)| (index, path)).collect()
    }

    /// 行を正規化し、空行を除き、ネタバレの境界より後ろと行数の上限を超えた分を捨てる。
    fn prepare_lines(&self, doc: &DocText) -> Vec<Line> {
        let mut out = Vec::new();
        for l in &doc.lines {
            let norm = normalize_line(l.text.trim());
            if norm.is_empty() {
                continue;
            }
            let lower = norm.to_ascii_lowercase();
            if self.is_boundary(&lower) {
                break;
            }
            out.push(Line {
                raw: l.text.trim().to_string(),
                display: clean_display(&l.text),
                norm,
                lower,
                size: l.size,
                page: l.page,
            });
            if out.len() >= self.rules.documents.max_lines_per_document {
                break;
            }
        }
        out
    }

    /// 「以下ネタバレ」「KP向け情報」などの境界の行か。
    fn is_boundary(&self, lower: &str) -> bool {
        let d = &self.rules.documents;
        let has = |list: &[String]| list.iter().any(|w| lower.contains(&w.to_lowercase()));
        if !has(&d.boundary_word) || has(&d.boundary_negation) {
            return false;
        }
        has(&d.boundary_marker) || (lower.chars().count() <= d.boundary_short_line && has(&d.boundary_heading))
    }

    // ------------------------------------------------------------ 1文書の解析

    fn scan_document(&self, path: &str, lines: &[Line], is_pdf: bool, info: &mut ScenarioInfo, pending: &mut Pending) {
        let ctx = DocContext::new(lines, is_pdf);
        let value = |v: String, raw: &str| InfoValue { value: v, source_path: path.to_string(), raw_text: raw.to_string() };

        // 1. 題名（「タイトル：」の見出し → 大きな文字 → 先頭付近の行 の順に優先）
        if info.title.is_none() {
            if let Some((t, raw)) = self.labeled_title(lines, &ctx) {
                info.title = Some(value(t, &raw));
            }
        }
        if info.title.is_none() && pending.size_title.is_none() {
            if let Some((t, raw)) = self.strong_title(lines, &ctx) {
                pending.size_title = Some(value(t, &raw));
            }
        }
        if info.title.is_none() && pending.size_title.is_none() && pending.weak_title.is_none() {
            if let Some((t, raw)) = self.weak_title(lines, &ctx) {
                pending.weak_title = Some(value(t, &raw));
            }
        }

        // 2. システム・人数・時間など
        for i in 0..lines.len().min(META_SCAN_LINES) {
            if ctx.noise[i] {
                continue;
            }
            let lower = &lines[i].lower;

            if info.system.is_none() {
                if let Some(f) = self.label_value(lines, &ctx, i, &self.labels.system) {
                    if let Some(name) = self.system_name(&f.value) {
                        info.system = Some(value(name, &f.raw));
                    }
                }
            }
            if pending.fallback_system.is_none() {
                if let Some(name) = self.system_name(&lines[i].norm) {
                    pending.fallback_system = Some(value(name, &lines[i].display));
                }
            }

            if info.players.is_none() {
                if let Some(f) = self.label_value(lines, &ctx, i, &self.labels.players) {
                    if let Some((min, max)) = parse_players(&f.value) {
                        info.players = Some(InfoValue {
                            value: PlayerCount { min, max },
                            source_path: path.to_string(),
                            raw_text: f.raw,
                        });
                    }
                }
            }
            if pending.gmless.is_none() && GMLESS_WORDS.iter().any(|w| lower.contains(w)) {
                pending.gmless = Some(InfoValue {
                    value: PlayerCount { min: 1, max: 1 },
                    source_path: path.to_string(),
                    raw_text: format!("GMレス: {}", lines[i].display),
                });
            }

            if info.duration.is_none() {
                if let Some(f) = self.label_value(lines, &ctx, i, &self.labels.duration) {
                    if let Some((min_hours, max_hours)) = parse_hours(&f.value) {
                        if info.format.is_none() {
                            if let Some(key) = self.format_key(&f.value) {
                                info.format = Some(value(key, &f.raw));
                            }
                        }
                        info.duration = Some(InfoValue {
                            value: DurationInfo { min_hours, max_hours },
                            source_path: path.to_string(),
                            raw_text: f.raw,
                        });
                    }
                }
            }

            if info.genre.is_none() {
                if let Some(f) = self.label_value(lines, &ctx, i, &self.labels.genre) {
                    info.genre = Some(value(f.value, &f.raw));
                }
            }
            if info.lost.is_none() {
                if let Some(f) = self.label_value(lines, &ctx, i, &self.labels.lost) {
                    if let Some(level) = self.lost_level(&f.value) {
                        info.lost = Some(value(level, &f.raw));
                    }
                }
            }
            if info.format.is_none() {
                if let Some(f) = self.label_value(lines, &ctx, i, &self.labels.format) {
                    if let Some(key) = self.format_key(&f.value) {
                        info.format = Some(value(key, &f.raw));
                    }
                }
            }
        }

        // 3. 概要（人数・時間・推奨技能のまとめ）
        if info.overview.is_none() {
            if let Some((text, skills)) = self.overview(lines, &ctx) {
                info.overview = Some(value(text.clone(), &text));
                if info.skills.is_none() && !skills.is_empty() {
                    info.skills = Some(InfoValue {
                        value: skills,
                        source_path: path.to_string(),
                        raw_text: text,
                    });
                }
            }
        }

        // 4. あらすじ
        if info.synopsis.is_none() {
            if let Some(text) = self.synopsis(lines, &ctx, 0) {
                info.synopsis = Some(value(text.clone(), &text));
            } else {
                // 「あらすじ」の見出しがなければ、ほかの文書も含めて最も優先順位の高い見出しのものを使う
                let best = if pending.weak_synopsis.is_some() { pending.weak_synopsis_tier } else { SYNOPSIS_TIERS };
                for tier in 1..best {
                    if let Some(text) = self.synopsis(lines, &ctx, tier) {
                        pending.weak_synopsis = Some(value(text.clone(), &text));
                        pending.weak_synopsis_tier = tier;
                        break;
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------ 題名

    /// 「タイトル：「あやかし夜行奇譚」」のような見出し付きの題名。括弧があれば中身を題名とする。
    fn labeled_title(&self, lines: &[Line], ctx: &DocContext) -> Option<(String, String)> {
        for i in 0..lines.len().min(META_SCAN_LINES) {
            if ctx.noise[i] {
                continue;
            }
            let Some(f) = self.label_value(lines, ctx, i, &self.labels.title) else { continue };
            // 表示用の文字（全角英数字などをそのまま）で取り出す。
            // 見出しと同じ行なら「:」や「】」の後ろ、見出しだけの行なら次の行。
            let display = &lines[i].display;
            let inline = f.raw == *display;
            let shown = if inline {
                display
                    .split_once([':', '：'])
                    .or_else(|| display.split_once(['】', ']']))
                    .map(|(_, after)| after.trim().to_string())
                    .filter(|a| !a.is_empty())
                    .unwrap_or_else(|| f.value.clone())
            } else {
                lines.get(i + 1).map(|l| l.display.clone()).unwrap_or_else(|| f.value.clone())
            };
            let title = match bracketed(&shown) {
                Some(inner) => inner,
                None => clean_heading(&shown).to_string(),
            };
            let n = title.chars().count();
            if (1..=TITLE_MAX_CHARS).contains(&n) {
                return Some((title, f.raw));
            }
        }
        None
    }

    /// PDF で、本文より明らかに大きな文字で書かれた行を題名とする。
    fn strong_title(&self, lines: &[Line], ctx: &DocContext) -> Option<(String, String)> {
        if !ctx.is_pdf || ctx.body_size <= 0.0 {
            return None;
        }
        let first_page = lines.iter().map(|l| l.page).min()?;
        let mut cands: Vec<usize> = (0..lines.len().min(120))
            .filter(|&i| lines[i].page <= first_page + 1 && !ctx.noise[i] && lines[i].size >= ctx.body_size * 1.3)
            .collect();
        cands.sort_by(|&a, &b| {
            lines[b].size.total_cmp(&lines[a].size).then(lines[a].page.cmp(&lines[b].page)).then(a.cmp(&b))
        });
        cands.into_iter().find_map(|i| {
            let t = self.title_candidate(&lines[i])?;
            Some((t, lines[i].display.clone()))
        })
    }

    /// 先頭付近で、見出しでも説明文でもない最初の行を題名候補とする。
    fn weak_title(&self, lines: &[Line], ctx: &DocContext) -> Option<(String, String)> {
        (0..lines.len().min(TITLE_SCAN_LINES)).filter(|&i| !ctx.noise[i]).find_map(|i| {
            let t = self.title_candidate(&lines[i])?;
            Some((t, lines[i].display.clone()))
        })
    }

    fn title_candidate(&self, line: &Line) -> Option<String> {
        // 「CoCシナリオ【天使の七日】」のようにシステム名や「シナリオ」が付いた題名の行は、それを取り除いた題名にする
        if !self.is_heading_line(line) && !self.is_label_line(&line.lower) {
            let has_noise = line.lower.contains("シナリオ") || line.lower.contains("trpg") || !self.systems_in(&line.norm).is_empty();
            if has_noise && line.norm.chars().count() <= TITLE_MAX_CHARS + 20 {
                if let Some(t) = self.strip_system_words(&line.display) {
                    let n = t.chars().count();
                    let lower = normalize_line(&t).to_ascii_lowercase();
                    if (2..=TITLE_MAX_CHARS).contains(&n) && t != line.display && !TITLE_EXCLUDE.iter().any(|w| lower.contains(w)) {
                        return Some(t);
                    }
                }
            }
        }
        // 「クトゥルフ神話TRPGシナリオ『夜の図書館』」→ 括弧の中を題名とする
        if let Some(inner) = bracketed(&line.display) {
            let n = inner.chars().count();
            if (2..=TITLE_MAX_CHARS).contains(&n) && !self.is_label_line(&normalize_line(&inner).to_ascii_lowercase()) {
                return Some(inner);
            }
        }
        if self.is_heading_line(line) || self.is_label_line(&line.lower) {
            return None;
        }
        let cleaned = clean_heading(&line.display);
        let n = cleaned.chars().count();
        if !(2..=TITLE_MAX_CHARS).contains(&n) {
            return None;
        }
        let lower = &line.lower;
        if TITLE_EXCLUDE.iter().any(|w| lower.contains(w)) {
            return None;
        }
        // 文章（句点で終わる、読点が多い）は題名ではない
        if cleaned.ends_with('。') || cleaned.matches('、').count() >= 2 || cleaned.starts_with("それは") {
            return None;
        }
        // 数字や記号だけ（ページ番号・日付）は題名ではない
        if !cleaned.chars().any(|c| c.is_alphabetic()) {
            return None;
        }
        // システム名だけの行（「Call of Cthulhu」など）は題名ではない
        if self.rules.system.iter().any(|r| r.r#match.iter().any(|m| m.chars().count() >= 3 && lower.contains(&m.to_ascii_lowercase())))
            && n <= 30
        {
            return None;
        }
        Some(cleaned.to_string())
    }

    // ------------------------------------------------------------ 見出しと値

    /// `i` 行目から、`labels` のいずれかの見出しに続く値を探す。
    ///
    /// - 「PL人数: 2〜3人」「[PL人数]2〜3人」「PL人数 2〜3人」の形に対応する
    /// - 「PL人数:」「[PL人数]」のように見出しだけの行は、次の行を値とする
    /// - 「PL人数:2人 / 所要時間:3時間」のように1行に複数あれば、次の見出しの手前で切る
    fn label_value(&self, lines: &[Line], ctx: &DocContext, i: usize, labels: &[String]) -> Option<Found> {
        let line = &lines[i];
        let lower = line.lower.as_str();
        for lbl in labels {
            let mut from = 0;
            while let Some(rel) = lower[from..].find(lbl.as_str()) {
                let pos = from + rel;
                let end = pos + lbl.len();
                from = end;
                if !boundary_before(lower, pos) || !boundary_after_label(lower, end) {
                    continue;
                }
                let prefix_is_decoration = clean_heading(&line.norm[..pos]).is_empty();
                let after = &line.norm[end..];
                let after_trim = after.trim_start_matches([' ', ']', ')', '>']);
                let inline = if let Some(v) = after_trim.strip_prefix(':') {
                    Some(v)
                } else if prefix_is_decoration
                    && (after.starts_with(']') || after_trim.starts_with(|c: char| c.is_ascii_digit()))
                {
                    // 「[PL人数]2人」「推奨人数 2〜3人」
                    Some(after_trim)
                } else if prefix_is_decoration && after_trim.is_empty() {
                    Some("")
                } else {
                    None
                };
                let Some(v) = inline else { continue };
                let v = self.cut_at_next_label(v);
                if !v.is_empty() {
                    return Some(Found { value: clip(v, VALUE_MAX_CHARS), raw: line.display.clone() });
                }
                return self.value_on_nearby_lines(lines, ctx, i);
            }
            // 「想定時間 約3時間」（表の左右のセルなど、見出しと値が空白で区切られている）
            if let Some(tail) = spaced_value(&line.raw, lbl) {
                let v = self.cut_at_next_label(&tail);
                if !v.is_empty() {
                    return Some(Found { value: clip(v, VALUE_MAX_CHARS), raw: line.display.clone() });
                }
            }
        }
        None
    }

    /// 見出しだけの行の値を、前後の行から探す。
    ///
    /// 基本は次の行。ただし表のセル内で値が折り返されていると、PDF では見出しが値の2行の間に来る
    /// （「1人（KP1人+PL1人のタイマ」「PL人数」「ン）」）。次の行に数字がなく前の行にある場合は、
    /// 前の行と次の行をつないだものを値とする。
    fn value_on_nearby_lines(&self, lines: &[Line], ctx: &DocContext, i: usize) -> Option<Found> {
        let usable = |k: usize| {
            k < lines.len() && !ctx.noise[k] && !self.is_heading_line(&lines[k]) && !self.is_label_line(&lines[k].lower)
        };
        let has_digit = |s: &str| s.chars().any(|c| c.is_ascii_digit());
        let line = &lines[i];
        let next = usable(i + 1).then(|| &lines[i + 1]);
        let prev = (i > 0 && usable(i - 1)).then(|| &lines[i - 1]);
        if let Some(p) = prev {
            let next_is_fragment = next.is_none_or(|n| !has_digit(&n.norm) && n.norm.chars().count() <= 8);
            let p_open = !p.display.ends_with(['。', '！', '？', '」', '』']) && p.norm.chars().count() <= 40;
            if next_is_fragment && p_open && has_digit(&p.norm) && p.page == line.page {
                let tail = next.map(|n| n.norm.as_str()).unwrap_or("");
                return Some(Found {
                    value: clip(&format!("{}{}", p.norm, tail), VALUE_MAX_CHARS),
                    raw: format!("{} {} {}", line.display, p.display, next.map(|n| n.display.as_str()).unwrap_or("")),
                });
            }
        }
        let n = next?;
        Some(Found { value: clip(&n.norm, VALUE_MAX_CHARS), raw: format!("{} {}", line.display, n.display) })
    }

    /// 値の中に次の見出し（「所要時間:」など）があれば、その手前で切る。
    fn cut_at_next_label<'a>(&self, v: &'a str) -> &'a str {
        let lower = v.to_ascii_lowercase();
        let mut cut = v.len();
        for lbl in &self.labels.all {
            let mut from = 0;
            while let Some(rel) = lower[from..].find(lbl.as_str()) {
                let pos = from + rel;
                from = pos + lbl.len();
                if pos >= cut {
                    break;
                }
                let after = lower[pos + lbl.len()..].trim_start_matches([' ', ']', ')']);
                if boundary_before(&lower, pos) && after.starts_with(':') {
                    cut = pos;
                    break;
                }
            }
        }
        v[..cut].trim_matches(VALUE_TRIM).trim_end_matches('[')
    }

    /// 見出し語だけの行か（「推奨技能」「[あらすじ]」「背景」など）。
    fn is_label_line(&self, lower: &str) -> bool {
        let c = clean_heading(lower).trim_end_matches(':').trim();
        if c.is_empty() {
            return false;
        }
        if self.labels.all.iter().any(|l| c == l) || SECTION_WORDS.contains(&c) {
            return true;
        }
        // 「PL人数:2人」のような「見出し: 値」の行
        self.labels.all.iter().any(|l| {
            c.starts_with(l.as_str()) && c[l.len()..].trim_start_matches([' ', ']']).starts_with(':')
        })
    }

    fn is_heading_line(&self, line: &Line) -> bool {
        line.norm.trim_start().starts_with(HEADING_MARKS)
    }

    // ------------------------------------------------------------ 値の正規化

    fn system_name(&self, text: &str) -> Option<String> {
        let lower = text.to_ascii_lowercase();
        self.rules
            .system
            .iter()
            .find(|r| r.r#match.iter().any(|m| lower.contains(&normalize_line(m).to_ascii_lowercase())))
            .map(|r| r.name.clone())
    }

    fn lost_level(&self, text: &str) -> Option<String> {
        let lower = text.to_ascii_lowercase();
        let words = crate::rules::ascii_tokens(&lower);
        self.rules
            .lost
            .iter()
            .find(|r| {
                r.r#match.iter().any(|m| {
                    let m = m.to_ascii_lowercase();
                    if m.is_ascii() { words.iter().any(|w| *w == m) } else { lower.contains(&m) }
                })
            })
            .map(|r| r.level.clone())
    }

    fn format_key(&self, text: &str) -> Option<String> {
        let lower = text.to_ascii_lowercase();
        let words = crate::rules::ascii_tokens(&lower);
        self.rules
            .format
            .iter()
            .find(|r| {
                r.r#match.iter().any(|m| {
                    let m = m.to_ascii_lowercase();
                    if m.is_ascii() { words.iter().any(|w| *w == m) } else { lower.contains(&m) }
                })
            })
            .map(|r| r.key.clone())
    }

    // ------------------------------------------------------------ 概要

    /// 人数・時間・推奨技能を、1項目1行の「推奨人数：２人」の形でまとめる。推奨技能の一覧も返す。
    ///
    /// 並びは文書の中の順番に関係なく、推奨人数 → プレイ時間 → 推奨技能 → 準推奨技能 とする。
    fn overview(&self, lines: &[Line], ctx: &DocContext) -> Option<(String, Vec<String>)> {
        let (mut players, mut duration, mut skills, mut semi): (Option<String>, Option<String>, Option<String>, Option<String>) =
            (None, None, None, None);
        for i in 0..lines.len().min(META_SCAN_LINES) {
            if ctx.noise[i] {
                continue;
            }
            if players.is_none() {
                if let Some(f) = self.label_value(lines, ctx, i, &self.labels.players) {
                    players = Some(f.value);
                }
            }
            if duration.is_none() {
                if let Some(f) = self.label_value(lines, ctx, i, &self.labels.duration) {
                    duration = Some(f.value);
                }
            }
            if semi.is_none() {
                if let Some(v) = self.list_value(lines, ctx, i, &self.labels.semi_skills) {
                    semi = Some(v);
                    continue;
                }
            }
            if skills.is_none() {
                if let Some(v) = self.list_value(lines, ctx, i, &self.labels.skills) {
                    skills = Some(v);
                }
            }
        }
        let skill_list = skills.as_deref().map(split_top_level).unwrap_or_default();
        let blocks: Vec<String> = [
            ("推奨人数", players),
            ("プレイ時間", duration),
            ("推奨技能", skills),
            ("準推奨技能", semi),
        ]
        .into_iter()
        .filter_map(|(name, v)| v.map(|v| format!("{name}：{}", to_display_value(&v))))
        .collect();
        (!blocks.is_empty()).then(|| (blocks.join("\n"), skill_list))
    }

    /// 技能のように列挙される値。見出しと同じ行に書かれていればそれを、見出しだけの行なら続く数行を値とし、
    /// 1行にまとめて返す。PDF で途中で折り返されている場合（行末が「、」や閉じていない括弧）は次の行につなげる。
    fn list_value(&self, lines: &[Line], ctx: &DocContext, i: usize, labels: &[String]) -> Option<String> {
        let line = &lines[i];
        let lower = line.lower.as_str();
        let (pos, lbl) = labels.iter().find_map(|l| {
            let p = lower.find(l.as_str())?;
            (boundary_before(lower, p) && boundary_after_label(lower, p + l.len())).then_some((p, l))
        })?;
        if !clean_heading(&line.norm[..pos]).is_empty() {
            return None;
        }
        let raw_after = &line.norm[pos + lbl.len()..];
        let after = raw_after.trim_start_matches([' ', ']', ')']);
        let inline = match after.strip_prefix(':') {
            Some(v) => v,
            None if after.is_empty() || raw_after.starts_with(']') => after,
            None => return None,
        };
        let mut value = strip_bullet(self.cut_at_next_label(inline)).to_string();
        // 「目星、心理学、信用、」のように区切りで終わっていれば、次の行に続いている（切り取りで消えた区切りを戻す）
        if !value.is_empty() && inline.trim_end().ends_with(['、', ',', '・', '/', '+']) && !needs_continuation(&value) {
            value.push('、');
        }
        let header_only = value.is_empty();
        for j in i + 1..lines.len().min(i + 1 + SKILL_MAX_LINES) {
            let l = &lines[j];
            if ctx.noise[j] {
                continue;
            }
            let next = strip_bullet(&l.norm);
            // 「対人関係技能」の次の行が「(威圧、…)」のように括弧で始まる場合も、その続きとみなす
            let continues = needs_continuation(&value) || next.starts_with(['(', '（']);
            if !header_only && !continues {
                break;
            }
            let stop = self.is_heading_line(l)
                || self.is_label_line(&l.lower)
                || next.starts_with('※')
                || next.ends_with('。')
                || next.chars().count() > 60;
            if stop || next.is_empty() {
                break;
            }
            if value.is_empty() || continues {
                value.push_str(next);
            } else {
                value.push('、');
                value.push_str(next);
            }
        }
        let value = value.trim_matches(VALUE_TRIM).to_string();
        (!value.is_empty()).then_some(value)
    }

    // ------------------------------------------------------------ あらすじ

    /// 優先順位 `tier` の見出し（`summary_tier`）に続く本文を集める。
    ///
    /// 「概要」などの欄に人数・時間などの仕様が書かれていれば、それは仕様の欄なのであらすじにはしない。
    /// 仕様が別の場所に書かれていて、欄が文章だけなら、その文章をあらすじとする。
    fn synopsis(&self, lines: &[Line], ctx: &DocContext, tier: u8) -> Option<String> {
        let weak = tier > 0;
        let labels: Vec<&String> = self.labels.summary.iter().filter(|l| summary_tier(l) == tier).collect();
        if labels.is_empty() {
            return None;
        }
        let mut i = 0;
        while i < lines.len() {
            let start = self.summary_heading(&lines[i], &labels);
            i += 1;
            let Some(inline) = start else { continue };
            if weak && inline.as_deref().is_some_and(|v| self.is_spec_text(v)) {
                continue;
            }
            if let Some(text) = self.collect_section(lines, ctx, i, inline, weak, false) {
                return Some(text);
            }
        }
        None
    }

    /// 見出しの次の行 `start` から、次の見出しの手前までの本文を集める。
    ///
    /// - `weak`: 「概要」などの欄。人数などの仕様が書かれていれば仕様の欄とみなす
    /// - `split_specs`: 仕様の欄でも捨てずに、仕様の行（人数・時間・「プレイ環境：…」・システム名だけの行・※の注意書き）を
    ///   飛ばして、文章の行だけを集める（「概要」の下にあらすじと人数が並んで書かれている場合の切り分け）
    fn collect_section(
        &self,
        lines: &[Line],
        ctx: &DocContext,
        start: usize,
        inline: Option<String>,
        weak: bool,
        split_specs: bool,
    ) -> Option<String> {
        let mut collected: Vec<&Line> = Vec::new();
        let mut first_inline = inline;
        let mut chars = 0;
        let mut j = start;
        let mut skipping_values = false;
        while j < lines.len() && collected.len() < SYNOPSIS_MAX_LINES && chars < SYNOPSIS_MAX_CHARS {
            let idx = j;
            let l = &lines[j];
            j += 1;
            if ctx.noise[idx] {
                continue;
            }
            if weak && self.is_spec_line(lines, ctx, idx) {
                if !split_specs {
                    // 「概要」の欄に人数などがある → 仕様の欄なので、あらすじにはしない
                    return None;
                }
                // 見出しだけの行（「推奨技能」の次の行に値）なら、続く値の行も飛ばす
                skipping_values = !self.has_value(&l.lower) && !l.lower.contains(']');
                continue;
            }
            if split_specs {
                let short = l.norm.chars().count() <= 40 && !l.norm.ends_with('。');
                if skipping_values && short && !self.is_heading_line(l) {
                    continue;
                }
                skipping_values = false;
                if l.norm.starts_with('※') || self.is_key_value_line(l) || self.is_system_only_line(l) {
                    continue;
                }
            }
            let label_line = self.is_label_line(&l.lower);
            let heading = self.is_heading_line(l)
                || label_line
                || (ctx.is_pdf && ctx.body_size > 0.0 && l.size >= ctx.body_size * 1.2 && l.norm.chars().count() <= 30);
            if heading {
                // 「概要」の直下に仕様（PL人数: 2人 など）が並ぶ場合は、それを飛ばして本文を探す
                if collected.is_empty() && first_inline.is_none() && label_line && self.has_value(&l.lower) {
                    continue;
                }
                break;
            }
            chars += l.display.chars().count();
            collected.push(l);
        }
        let mut parts: Vec<String> = Vec::new();
        if let Some(v) = first_inline.take() {
            parts.push(v);
        }
        let body = join_paragraph(&collected, ctx);
        if !body.is_empty() {
            parts.push(body);
        }
        let text = parts.join("\n");
        (text.chars().count() >= 10).then_some(text)
    }

    /// 「プレイ環境：オンライン推奨」のような「短い見出し：値」の行か。
    fn is_key_value_line(&self, l: &Line) -> bool {
        let Some((key, value)) = l.norm.split_once(':') else { return false };
        let key = clean_heading(key);
        let n = key.chars().count();
        (1..=12).contains(&n) && !key.contains('。') && !key.contains('、') && !value.trim().is_empty()
    }

    /// 「「クトゥルフ神話TRPG」（第６版）」のような、システム名だけの行か。
    fn is_system_only_line(&self, l: &Line) -> bool {
        l.norm.chars().count() <= 30 && !l.norm.ends_with('。') && !self.systems_in(&l.norm).is_empty()
    }

    /// あらすじの候補を、見出しごとにすべて返す（優先順位の高い順。同じ順位なら出てきた順）。
    ///
    /// URL から取り込むときに、どれをあらすじにするか比べて選べるようにするためのもの。
    /// 「概要」の欄は、人数などの仕様の行を飛ばして文章の行だけを候補にする。
    pub fn synopsis_candidates(&self, source_lines: &[String]) -> Vec<SynopsisCandidate> {
        let doc = DocText {
            is_pdf: false,
            lines: source_lines.iter().map(|t| crate::info::text::DocLine { text: t.clone(), size: 0.0, page: 0 }).collect(),
        };
        let lines = self.prepare_lines(&doc);
        let ctx = DocContext::new(&lines, false);
        let all: Vec<&String> = self.labels.summary.iter().collect();
        let mut out: Vec<SynopsisCandidate> = Vec::new();
        for i in 0..lines.len() {
            if ctx.noise[i] {
                continue;
            }
            let Some(inline) = self.summary_heading(&lines[i], &all) else { continue };
            let c = clean_heading(&lines[i].lower);
            let tier = all
                .iter()
                .filter(|l| c.starts_with(l.as_str()))
                .max_by_key(|l| l.len())
                .map_or(0, |l| summary_tier(l));
            let weak = tier > 0;
            let label = clean_heading(lines[i].display.split_once(['：', ':']).map_or(lines[i].display.as_str(), |(k, _)| k))
                .to_string();
            let inline = inline.filter(|v| !(weak && self.is_spec_text(v)));
            if let Some(text) = self.collect_section(&lines, &ctx, i + 1, inline, weak, weak) {
                if !out.iter().any(|o| o.text == text) {
                    out.push(SynopsisCandidate { label, text, tier });
                }
            }
        }
        out.sort_by_key(|c| c.tier);
        out
    }

    /// あらすじの見出し行なら `Some(見出しと同じ行に書かれた本文)` を返す。
    fn summary_heading(&self, line: &Line, labels: &[&String]) -> Option<Option<String>> {
        let c = clean_heading(&line.lower);
        for lbl in labels {
            if c == lbl.as_str() || c.trim_end_matches(':') == lbl.as_str() {
                return Some(None);
            }
            // 「あらすじ: 本文…」
            if let Some(rest) = c.strip_prefix(lbl.as_str()) {
                if let Some(v) = rest.trim_start_matches([' ', ']']).strip_prefix(':') {
                    let v = v.trim();
                    if v.chars().count() >= 10 {
                        // 表示用テキストから、最初の「:」「：」より後ろを取る
                        let shown = line
                            .display
                            .split_once(['：', ':', '︓'])
                            .map(|(_, r)| r.trim().to_string())
                            .unwrap_or_else(|| v.to_string());
                        return Some(Some(shown));
                    }
                }
            }
        }
        None
    }

    /// 人数・時間・技能などの仕様が書かれた行か（見出しだけの行で、次の行が値の場合も含む）。
    fn is_spec_line(&self, lines: &[Line], ctx: &DocContext, i: usize) -> bool {
        let l = &self.labels;
        [&l.players, &l.duration, &l.system, &l.lost, &l.genre, &l.format]
            .iter()
            .any(|labels| self.label_value(lines, ctx, i, labels).is_some())
            || [&l.skills, &l.semi_skills].iter().any(|labels| self.list_value(lines, ctx, i, labels).is_some())
    }

    /// 見出しと同じ行に書かれた本文が、仕様（「PL2人、3時間」など）か。
    fn is_spec_text(&self, text: &str) -> bool {
        let line = Line {
            raw: text.to_string(),
            display: clean_display(text),
            norm: normalize_line(text),
            lower: normalize_line(text).to_ascii_lowercase(),
            size: 0.0,
            page: 0,
        };
        let short_spec = line.norm.chars().count() <= 40 && looks_like_spec(&line.lower);
        let one = [line];
        let ctx = DocContext::new(&one, false);
        short_spec || self.is_spec_line(&one, &ctx, 0)
    }

    fn has_value(&self, lower: &str) -> bool {
        lower.split_once(':').is_some_and(|(_, v)| !v.trim().is_empty())
    }
}

// ------------------------------------------------------------ 文書ごとの補助情報

struct DocContext {
    is_pdf: bool,
    /// 本文の文字の大きさ（PDF のみ。中央値）。
    body_size: f32,
    /// 1行の典型的な文字数（PDF の折り返しを判定するため）。
    typical_len: usize,
    /// ページ番号やヘッダー・フッター（ページごとに繰り返される行）。
    noise: Vec<bool>,
}

impl DocContext {
    fn new(lines: &[Line], is_pdf: bool) -> Self {
        let mut sizes: Vec<f32> = lines.iter().map(|l| l.size).filter(|s| *s > 0.0).collect();
        sizes.sort_by(|a, b| a.total_cmp(b));
        let body_size = sizes.get(sizes.len() / 2).copied().unwrap_or(0.0);

        let mut lens: Vec<usize> = lines.iter().map(|l| l.display.chars().count()).filter(|n| *n >= 10).collect();
        lens.sort_unstable();
        let typical_len = lens.get(lens.len() * 3 / 4).copied().unwrap_or(40);

        let pages = lines.iter().map(|l| l.page).max().unwrap_or(0) as usize + 1;
        let mut counts: HashMap<&str, usize> = HashMap::new();
        for l in lines {
            *counts.entry(l.norm.as_str()).or_default() += 1;
        }
        let noise = lines
            .iter()
            .map(|l| {
                let page_number = l.norm.chars().all(|c| c.is_ascii_digit() || " -/.()pP".contains(c));
                let repeated = is_pdf && pages >= 3 && counts[l.norm.as_str()] >= 3 && l.norm.chars().count() <= 40;
                page_number || repeated
            })
            .collect();
        Self { is_pdf, body_size, typical_len, noise }
    }
}

// ------------------------------------------------------------ 補助関数

fn read_document(source: &mut dyn SourceAccessor, index: usize, path: &str) -> Result<DocText, String> {
    let bytes = source.read_entry(index, MAX_DOCUMENT_BYTES).map_err(|e| e.to_string())?;
    let path = path.to_string();
    // PDF の解析は入力によって深い再帰が起きうるので、スタックを大きく取った専用スレッドで行う
    run_on_worker(move || extract_document(&path, &bytes))
}

/// 商品名で、システム名と一緒に付くことが多い説明の語（小文字）。
const TITLE_NOISE_WORDS: &[&str] = &[
    "trpg", "rpg", "シナリオ集", "シナリオ", "対応", "向け", "用", "dl", "pdf", "ダウンロード", "パッケージ", "データ", "付き",
];

/// 括弧の中にあれば、その括弧ごと消す語（小文字）。「【DLデータ付き】」「（PDF版）」など。
const BRACKET_NOISE_WORDS: &[&str] = &[
    "dl", "ダウンロード", "データ", "版", "特典", "付き", "付", "セット", "pdf", "パッケージ", "無料", "r18", "r-18", "ver",
    "更新", "シナリオ", "trpg",
];

/// 題名の中でシステム名として探してよい語か（数字で始まる語・「版」を含む語・1文字の語は使わない）。
fn usable_title_word(m: &str) -> bool {
    let m = m.trim();
    m.chars().count() >= 2 && !m.starts_with(|c: char| c.is_ascii_digit()) && !m.contains('版') && !m.starts_with('第')
}

/// `hay` の中の `needle` の位置。英数字で始まる・終わる語は、前後が英数字でないところだけ一致させる。
fn find_word(hay: &str, needle: &str) -> Option<usize> {
    if needle.is_empty() {
        return None;
    }
    let mut from = 0;
    while let Some(p) = hay[from..].find(needle) {
        let pos = from + p;
        let end = pos + needle.len();
        let before_ok = !needle.starts_with(|c: char| c.is_ascii_alphanumeric())
            || hay[..pos].chars().next_back().is_none_or(|c| !c.is_ascii_alphanumeric());
        let after_ok = !needle.ends_with(|c: char| c.is_ascii_alphanumeric())
            || hay[end..].chars().next().is_none_or(|c| !c.is_ascii_alphabetic());
        if before_ok && after_ok {
            return Some(pos);
        }
        from = pos + needle.chars().next().map_or(1, char::len_utf8);
    }
    None
}

/// `hay` の中の `needle` のすべての位置（照合の規則は `find_word` と同じ）。
fn find_words(hay: &str, needle: &str) -> Vec<usize> {
    let mut out = Vec::new();
    let mut from = 0;
    while from <= hay.len() {
        let Some(p) = find_word(&hay[from..], needle) else { break };
        // find_word は部分文字列の先頭からの境界を見るので、元の文字列で境界を確かめ直す
        let pos = from + p;
        if find_word(&hay[pos..], needle) == Some(0)
            && (!needle.starts_with(|c: char| c.is_ascii_alphanumeric())
                || hay[..pos].chars().next_back().is_none_or(|c| !c.is_ascii_alphanumeric()))
        {
            out.push(pos);
        }
        from = pos + needle.chars().next().map_or(1, char::len_utf8);
    }
    out
}

/// `s` から `word` をすべて取り除く（照合の規則は `find_word` と同じ）。
fn remove_word(s: &str, word: &str) -> String {
    let mut out = s.to_string();
    while let Some(p) = find_word(&out, word) {
        out.replace_range(p..p + word.len(), " ");
    }
    out
}

/// 見出しの飾り（記号・括弧・空白・コロン）を前後から取り除く。
///
/// 長音「ー」は飾りの線（「ーーー」）として取り除くが、かなの直後のもの（「トレーラー」「ストーリー」）は語の一部なので残す。
fn clean_heading(text: &str) -> &str {
    let mut t = trim_decoration(text);
    loop {
        let before = t;
        t = trim_decoration(t.trim_start_matches('ー'));
        // 末尾の「ー」の並び。かなの直後に1つだけなら長音（語の一部）、それ以外は飾りの線
        let rest = t.trim_end_matches('ー');
        let run = t[rest.len()..].chars().count();
        let after_kana = rest.chars().next_back().is_some_and(|c| matches!(c as u32, 0x3041..=0x30FA | 0xFF66..=0xFF9F));
        if run > 1 || (run == 1 && !after_kana) {
            t = rest;
        }
        t = trim_decoration(t);
        if t == before {
            return t;
        }
    }
}

fn trim_decoration(text: &str) -> &str {
    text.trim_matches(|c: char| {
        c.is_whitespace()
            || HEADING_MARKS.contains(&c)
            || matches!(
                c,
                '】' | '【' | ']' | '(' | ')' | '（' | '）' | '〔' | '〕' | ':' | '：' | '-' | '—' | '―' | '一' | '='
                    | '~' | '〜' | '・' | '*' | '<' | '>' | '≪' | '≫' | '《' | '》' | '〈' | '〉' | '|'
            )
    })
}

/// 見出し語の直前が語の切れ目か（「推奨人数」の中の「人数」には一致させない）。
fn boundary_before(s: &str, pos: usize) -> bool {
    s[..pos].chars().next_back().is_none_or(|c| !c.is_alphanumeric())
}

/// 英字の見出し語の直後が語の切れ目か（"type" が "typeface" に一致しないように）。
fn boundary_after_label(s: &str, end: usize) -> bool {
    match (s[..end].chars().next_back(), s[end..].chars().next()) {
        (Some(p), Some(n)) if p.is_ascii_alphanumeric() => !n.is_ascii_alphanumeric(),
        _ => true,
    }
}

/// 「…『題名』…」「「題名」」のような括弧の中身（題名らしい場合のみ）。
fn bracketed(text: &str) -> Option<String> {
    for (open, close) in [('『', '』'), ('「', '」'), ('《', '》'), ('≪', '≫')] {
        let Some(a) = text.find(open) else { continue };
        let rest = &text[a + open.len_utf8()..];
        let Some(b) = rest.find(close) else { continue };
        let inner = rest[..b].trim();
        let before = text[..a].trim();
        let after = rest[b + close.len_utf8()..].trim();
        // 括弧だけの行、または「…シナリオ『題名』」の形のときだけ採る（台詞の「」を拾わないように）
        let lower = normalize_line(before).to_ascii_lowercase();
        let framed = before.is_empty() || lower.contains("シナリオ") || lower.contains("trpg");
        if framed && after.chars().count() <= 10 && !inner.is_empty() {
            return Some(clean_display(inner));
        }
    }
    None
}

/// 空白で区切られた「見出し 値」の値（見出しの文字の間に空白が入っていてもよい）。
fn spaced_value(raw: &str, label: &str) -> Option<String> {
    let raw = raw.trim();
    for (k, c) in raw.char_indices() {
        if !c.is_whitespace() {
            continue;
        }
        let head = normalize_line(clean_heading(&raw[..k])).to_ascii_lowercase();
        if head.len() > label.len() {
            return None;
        }
        if head == label {
            let tail = normalize_line(&raw[k..]);
            return (!tail.is_empty() && !tail.starts_with(':')).then_some(tail);
        }
    }
    None
}

fn clip(s: &str, max: usize) -> String {
    s.chars().take(max).collect::<String>().trim().to_string()
}

/// PDF の折り返し行をつなげて段落にする（txt などは改行をそのまま残す）。
fn join_paragraph(lines: &[&Line], ctx: &DocContext) -> String {
    let mut out = String::new();
    let mut prev: Option<&Line> = None;
    for l in lines {
        let cur = l.display.as_str();
        match prev {
            None => out.push_str(cur),
            Some(p) => {
                let p_text = p.display.as_str();
                let ends_sentence = p_text.ends_with(['。', '！', '？', '!', '?', '」', '』', '）', ')', '…', '.']);
                let starts_new = cur.starts_with(['「', '『', '※', '・', '―', '—', '（', '(']);
                let wrapped = ctx.is_pdf
                    && !ends_sentence
                    && !starts_new
                    && p_text.chars().count() * 10 >= ctx.typical_len * 8;
                if wrapped {
                    let need_space = p_text.chars().next_back().is_some_and(|c| c.is_ascii_alphanumeric())
                        && cur.chars().next().is_some_and(|c| c.is_ascii_alphanumeric());
                    if need_space {
                        out.push(' ');
                    }
                } else {
                    out.push('\n');
                }
                out.push_str(cur);
            }
        }
        prev = Some(l);
    }
    out
}

/// 数値の範囲（「2〜4」「3」）を読む。`skip` が真を返す位置の数字は飛ばす。
fn first_range(text: &str, skip: impl Fn(&str) -> bool) -> Option<(u32, u32, usize, bool)> {
    let b = text.as_bytes();
    let mut i = 0;
    while i < b.len() {
        if !b[i].is_ascii_digit() || (i > 0 && b[i - 1].is_ascii_digit()) {
            i += 1;
            continue;
        }
        let (n1, mut j) = read_number(text, i);
        if skip(&text[..i]) {
            i = j;
            continue;
        }
        let mut decimal = false;
        if text[j..].starts_with('.') && text[j + 1..].starts_with(|c: char| c.is_ascii_digit()) {
            decimal = true;
            j = read_number(text, j + 1).1;
        }
        let rest = &text[j..];
        let after_sep = rest
            .trim_start()
            .strip_prefix(['〜', '-', '~', '～', '−'])
            .map(str::trim_start);
        if let Some(r) = after_sep {
            if r.starts_with(|c: char| c.is_ascii_digit()) {
                let off = text.len() - r.len();
                let (n2, mut k) = read_number(text, off);
                if text[k..].starts_with('.') && text[k + 1..].starts_with(|c: char| c.is_ascii_digit()) {
                    decimal = true;
                    k = read_number(text, k + 1).1;
                }
                return Some((n1.min(n2), n1.max(n2), k, decimal));
            }
        }
        return Some((n1, n1, j, decimal));
    }
    None
}

fn read_number(text: &str, start: usize) -> (u32, usize) {
    let digits: String = text[start..].chars().take_while(|c| c.is_ascii_digit()).collect();
    let end = start + digits.len();
    (digits.parse().unwrap_or(u32::MAX).min(9999), end)
}

/// 人数の値を読む（「PL7名+GM1人」の GM の人数は無視する）。
fn parse_players(value: &str) -> Option<(u32, u32)> {
    let v = normalize_line(value).to_ascii_lowercase();
    let skip = |before: &str| {
        let b = before.trim_end_matches([' ', '+', '×', 'x', '・', '/']);
        b.ends_with("gm") || b.ends_with("kp") || b.ends_with("dm") || b.ends_with("st")
    };
    if let Some((min, max, _, _)) = first_range(&v, skip) {
        return Some((min, max));
    }
    // 漢数字（「二人」）とタイマン
    let kanji = ['一', '二', '三', '四', '五', '六', '七', '八', '九'];
    let chars: Vec<char> = v.chars().collect();
    for (k, c) in chars.iter().enumerate() {
        if let Some(n) = kanji.iter().position(|x| x == c) {
            if chars.get(k + 1).is_some_and(|n| matches!(n, '人' | '名')) {
                return Some((n as u32 + 1, n as u32 + 1));
            }
        }
    }
    if v.contains("タイマン") || v.contains("ソロ") {
        return Some((1, 1));
    }
    None
}

/// 時間の値を読む（「4〜5時間」「約3時間」「90分」「3.5時間」）。単位が日・週などのものは読まない。
fn parse_hours(value: &str) -> Option<(u32, u32)> {
    let v = normalize_line(value).to_ascii_lowercase();
    let (min, max, end, decimal) = first_range(&v, |_| false)?;
    let unit = v[end..].trim_start();
    if unit.starts_with('分') || unit.starts_with("min") {
        let h = |m: u32| ((m + 30) / 60).max(1);
        return Some((h(min), h(max)));
    }
    if unit.starts_with(['日', '週', '月', '年', '回', '人', '名', 'p']) {
        return None;
    }
    Some((min, if decimal { max + 1 } else { max }))
}

/// 概要に表示する値の整形。数字を全角に、範囲の「~」「〜」「-」を「～」に、括弧を全角の「（）」にする。
fn to_display_value(s: &str) -> String {
    let chars: Vec<char> = s.trim().chars().collect();
    let digit = |k: Option<&char>| k.is_some_and(|c| c.is_ascii_digit());
    let mut out = String::with_capacity(s.len() * 2);
    for (k, &c) in chars.iter().enumerate() {
        let between_digits = k > 0 && digit(chars.get(k - 1)) && digit(chars.get(k + 1));
        out.push(match c {
            '0'..='9' => char::from_u32(c as u32 + 0xFEE0).unwrap_or(c),
            '~' | '〜' | '∼' => '～',
            '-' if between_digits => '～',
            '(' => '（',
            ')' => '）',
            ':' => '：',
            ',' if !between_digits => '、',
            _ => c,
        });
    }
    out
}

/// 見出しがなくても仕様とわかる書き方か（「PL2人」「2〜3人」「4〜6時間」「90分」など、数字の直後に人数・時間の単位）。
fn looks_like_spec(lower: &str) -> bool {
    let units = ["人", "名", "時間", "分", "h", "pl"];
    let b = lower.as_bytes();
    let mut i = 0;
    while i < b.len() {
        if b[i].is_ascii_digit() {
            let mut j = i;
            while j < b.len() && b[j].is_ascii_digit() {
                j += 1;
            }
            let rest = lower[j..].trim_start_matches(['〜', '-', '~', ' ']);
            let rest = rest.trim_start_matches(|c: char| c.is_ascii_digit());
            if units.iter().any(|u| rest.starts_with(u)) {
                return true;
            }
            i = j;
        } else {
            i += 1;
        }
    }
    lower.contains("gmレス") || lower.contains("kpレス") || lower.contains("タイマン")
}

/// 行頭の箇条書きの記号（「・」「-」「*」など）を取り除く。
fn strip_bullet(s: &str) -> &str {
    s.trim().trim_start_matches(['・', '-', '*', '•', '‣', '◦']).trim()
}

/// 値が途中で折り返されている（行末が区切り、または括弧が閉じていない）か。
fn needs_continuation(s: &str) -> bool {
    let s = s.trim_end();
    if s.ends_with(['、', ',', '・', '/', '(', '（', '「', '+']) {
        return true;
    }
    let open = s.chars().filter(|c| matches!(c, '(' | '（')).count();
    let close = s.chars().filter(|c| matches!(c, ')' | '）')).count();
    open > close
}

/// 「目星、心理学、対人関係技能（威圧、説得）」を、括弧の外の区切りで分ける。
fn split_top_level(s: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut depth = 0i32;
    let mut cur = String::new();
    for c in s.chars() {
        match c {
            '(' | '（' => depth += 1,
            ')' | '）' => depth = (depth - 1).max(0),
            _ => {}
        }
        if depth == 0 && matches!(c, '、' | ',' | '/' | '・') {
            let t = cur.trim().to_string();
            if !t.is_empty() {
                out.push(t);
            }
            cur.clear();
        } else {
            cur.push(c);
        }
    }
    let t = cur.trim().to_string();
    if !t.is_empty() {
        out.push(t);
    }
    out.into_iter().map(|t| to_display_value(&t).replace('　', "")).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::info::text::DocLine;

    fn doc(lines: &[(&str, f32, u16)]) -> DocText {
        DocText {
            is_pdf: lines.iter().any(|l| l.1 > 0.0),
            lines: lines.iter().map(|(t, s, p)| DocLine { text: t.to_string(), size: *s, page: *p }).collect(),
        }
    }

    fn run(d: DocText) -> ScenarioInfo {
        let ex = InfoExtractor::new();
        let lines = ex.prepare_lines(&d);
        let mut info = ScenarioInfo::default();
        let mut pending = Pending::default();
        ex.scan_document("s.pdf", &lines, d.is_pdf, &mut info, &mut pending);
        if info.title.is_none() {
            info.title = pending.size_title.or(pending.weak_title);
        }
        if info.system.is_none() {
            info.system = pending.fallback_system;
        }
        if info.players.is_none() {
            info.players = pending.gmless;
        }
        if info.synopsis.is_none() {
            info.synopsis = pending.weak_synopsis;
        }
        info
    }

    #[test]
    fn pdf_artifacts_do_not_break_extraction() {
        // hayro から出てくる行（康熙部首の「⼈」、縦書き用の「︓」、字間の空白）
        let info = run(doc(&[
            ("クトゥルフ神話TRPG シナリオ", 14.0, 0),
            ("夜 ⾊ の 図 書 館", 32.0, 0),
            ("作︓テスト", 10.0, 0),
            ("◆ 概 要", 16.0, 1),
            ("シ ス テ ム ︓ 新クトゥルフ神話TRPG", 10.0, 1),
            ("プ レ イ ⼈ 数 ︓ ２ 〜 ３ ⼈", 10.0, 1),
            ("プレイ時間︓ボイセ４〜５時間", 10.0, 1),
            ("推奨技能︓", 10.0, 1),
            ("⽬星、図書館、聞き⽿", 10.0, 1),
            ("◆ あ ら す じ", 16.0, 1),
            ("ある雨の夜、探索者たちは古い図書館に閉じ込められてしまう。", 10.0, 1),
            ("閉館時間を過ぎた館内には、誰もいないはずの足音が響いていた", 10.0, 1),
            ("。", 10.0, 1),
            ("◆ 背景", 16.0, 1),
            ("ここから先は秘密", 10.0, 1),
        ]));
        assert_eq!(info.title.unwrap().value, "夜色の図書館");
        assert_eq!(info.system.unwrap().value, "新クトゥルフ神話TRPG");
        let p = info.players.unwrap().value;
        assert_eq!((p.min, p.max), (2, 3));
        let d = info.duration.unwrap().value;
        assert_eq!((d.min_hours, d.max_hours), (4, 5));
        let ov = info.overview.unwrap().value;
        assert_eq!(ov, "推奨人数：２～３人\nプレイ時間：ボイセ４～５時間\n推奨技能：目星、図書館、聞き耳");
        let syn = info.synopsis.unwrap().value;
        assert!(syn.starts_with("ある雨の夜、探索者たち"), "{syn}");
        assert!(!syn.contains("秘密"), "{syn}");
        assert!(!syn.contains("背景"), "{syn}");
        assert_eq!(info.format.unwrap().value, "voice");
    }

    #[test]
    fn several_labels_on_one_line_are_split() {
        let info = run(doc(&[("【PL人数】2人 / 所要時間:3時間 / ロスト率:低", 0.0, 0)]));
        let p = info.players.unwrap().value;
        assert_eq!((p.min, p.max), (2, 2));
        let d = info.duration.unwrap().value;
        assert_eq!((d.min_hours, d.max_hours), (3, 3));
        assert_eq!(info.lost.unwrap().value, "low");
    }

    #[test]
    fn overview_is_one_line_per_item() {
        let want = "推奨人数：２人\nプレイ時間：４～６時間\n推奨技能：目星、心理学、信用、対人関係技能（威圧、言いくるめ、説得もしくは魅惑）\n準推奨技能：自然、サバイバル";
        // 1行ずつ書かれている場合（順番が違っても、決まった順に並べる）
        let info = run(doc(&[
            ("準推奨技能：自然、サバイバル", 0.0, 0),
            ("推奨技能：目星、心理学、信用、対人関係技能（威圧、言いくるめ、説得もしくは魅惑）", 0.0, 0),
            ("PL人数：2人", 0.0, 0),
            ("プレイ時間：4~6時間", 0.0, 0),
        ]));
        assert_eq!(info.overview.unwrap().value, want);
        // PDF で見出しだけの行・折り返し・箇条書きになっている場合
        let info = run(doc(&[
            ("推 奨 ⼈ 数 ︓ ２ ⼈", 10.0, 0),
            ("プレイ時間︓", 10.0, 0),
            ("４〜６時間", 10.0, 0),
            ("【推奨技能】", 10.0, 0),
            ("目星、心理学、信用、", 10.0, 0),
            ("対人関係技能", 10.0, 0),
            ("（威圧、言いくるめ、", 10.0, 0),
            ("説得もしくは魅惑）", 10.0, 0),
            ("【準推奨技能】", 10.0, 0),
            ("・自然", 10.0, 0),
            ("・サバイバル", 10.0, 0),
            ("◆あらすじ", 14.0, 0),
        ]));
        let info_ov = info.overview.unwrap().value;
        assert_eq!(info_ov, want);
        assert_eq!(
            info.skills.unwrap().value,
            ["目星", "心理学", "信用", "対人関係技能（威圧、言いくるめ、説得もしくは魅惑）"]
        );
    }

    #[test]
    fn skills_continue_after_trailing_comma_and_parenthesis() {
        // 「星の吸血鬼にさよならを」の概要ページ（2段組みを段ごとに読んだ後の並び）
        let info = run(doc(&[
            ("星の吸血鬼にさよならを", 14.0, 0),
            ("♢推奨人数：２人", 9.0, 0),
            ("♢プレイ時間：４～６時間", 9.0, 0),
            ("♢推奨技能：目星、心理学、信用、 ", 9.0, 0),
            ("対人関係技能 ", 9.0, 0),
            ("（威圧、言いくるめ、説得もしくは魅惑） ", 9.0, 0),
            ("♢準推奨技能：自然、サバイバル ", 9.0, 0),
            ("※基本的な表記は新版（７版） ", 9.0, 0),
            ("♢探索者について ", 10.0, 0),
            ("探索者たちは高校二年生、学生である。", 9.0, 0),
            ("▼概要 ", 10.0, 0),
            ("学園の裏山に流れ星が落ちたのを見た。", 9.0, 0),
            ("▼背景 ", 10.0, 0),
            ("物語は過去に遡る。", 9.0, 0),
        ]));
        assert_eq!(
            info.overview.unwrap().value,
            "推奨人数：２人\nプレイ時間：４～６時間\n推奨技能：目星、心理学、信用、対人関係技能（威圧、言いくるめ、説得もしくは魅惑）\n準推奨技能：自然、サバイバル"
        );
        assert_eq!(info.synopsis.unwrap().value, "学園の裏山に流れ星が落ちたのを見た。");
    }

    #[test]
    fn table_cells_in_pdf() {
        // 表の左右のセル（見出しと値が空白で区切られる）と、セル内で折り返された値
        let info = run(doc(&[
            ("灯台守の手記", 28.0, 0),
            ("1人（KP1人+PL1人のタイマ", 10.0, 0),
            ("PL人数", 10.0, 0),
            ("ン）", 10.0, 0),
            ("想定時間 約3時間", 10.0, 0),
            ("ロ ス ト 率   中", 10.0, 0),
        ]));
        let p = info.players.unwrap().value;
        assert_eq!((p.min, p.max), (1, 1));
        let d = info.duration.unwrap().value;
        assert_eq!((d.min_hours, d.max_hours), (3, 3));
        assert_eq!(info.lost.unwrap().value, "medium");
    }

    #[test]
    fn gm_count_is_not_player_count() {
        assert_eq!(parse_players("PL7名+GM1人"), Some((7, 7)));
        assert_eq!(parse_players("KP1人+PL2〜4人"), Some((2, 4)));
        assert_eq!(parse_players("タイマン"), Some((1, 1)));
        assert_eq!(parse_hours("約90分"), Some((2, 2)));
        assert_eq!(parse_hours("3.5時間"), Some((3, 4)));
        assert_eq!(parse_hours("テキセ2週間"), None);
    }

    #[test]
    fn title_with_system_and_short_skill_labels() {
        // 「天使の七日」の1ページ目（題名が【】、「推奨：」「準推奨：」の短い見出し）
        let info = run(doc(&[
            ("CoCシナリオ【天使の七日】", 20.0, 0),
            ("●シナリオ概要", 14.0, 0),
            ("人数：1人", 9.6, 0),
            ("時間：4～6時間", 9.6, 0),
            ("推奨：目星、聞き耳、図書館", 9.6, 0),
            ("準推奨：地質学、生物学", 9.6, 0),
            ("注意：KPCロスト率高、架空の病あり", 9.6, 0),
            ("【あらすじ】", 9.6, 0),
            ("探索者は大切な人が体調を崩したと聞き、お見舞いへ行く。", 9.6, 0),
            ("【背景】", 9.6, 0),
            ("ある男がいた。", 9.6, 0),
        ]));
        assert_eq!(info.title.unwrap().value, "天使の七日");
        assert_eq!(
            info.overview.unwrap().value,
            "推奨人数：１人\nプレイ時間：４～６時間\n推奨技能：目星、聞き耳、図書館\n準推奨技能：地質学、生物学"
        );
        assert_eq!(info.synopsis.unwrap().value, "探索者は大切な人が体調を崩したと聞き、お見舞いへ行く。");
        // 「推奨人数」の「推奨」を技能の見出しと取り違えない
        let info = run(doc(&[("推奨人数：2人", 0.0, 0)]));
        assert!(info.skills.is_none());
        assert_eq!(info.overview.unwrap().value, "推奨人数：２人");
        // 題名の一部の「シナリオ」は消さない（括弧の外が説明だけのときだけ）
        let ex = InfoExtractor::new();
        assert_eq!(ex.strip_system_words("【天使の七日】").as_deref(), Some("天使の七日"));
        assert_eq!(ex.strip_system_words("【新装版】ガラスの館").as_deref(), Some("ガラスの館"));
    }

    #[test]
    fn title_label_wins() {
        // 「あやかし夜行奇譚」のルールブック（PDF から出てくる文字のまま）
        let info = run(doc(&[
            ("マーダーミステリー「あやかし夜⾏奇譚」︓ルールブック（GM⽤）", 8.0, 0),
            ("【はじめに】", 16.0, 0),
            ("この度は拙作マーダーミステリー「あやかし夜⾏奇譚」をダウンロードいただきまして誠に", 11.0, 0),
            ("ありがとうございます。", 11.0, 0),
            ("【ゲーム概要】", 16.0, 0),
            ("タイトル︓「あやかし夜⾏奇譚」", 11.0, 0),
            ("ジャンル︓あやかし×列⾞×マーダーミステリー", 11.0, 0),
            ("プレイ⼈数︓PL７名+GM１⼈", 11.0, 0),
            ("プレイ時間︓４〜５時間を想定しています", 11.0, 0),
        ]));
        assert_eq!(info.title.unwrap().value, "あやかし夜行奇譚");
        assert_eq!(info.genre.unwrap().value, "あやかし×列車×マーダーミステリー");
        let p = info.players.unwrap().value;
        assert_eq!((p.min, p.max), (7, 7));

        // 大きな文字の題名より、「タイトル：」の見出しを優先する。括弧がなければ値そのもの、次の行に書かれていてもよい
        let info = run(doc(&[("表紙の大きな文字", 30.0, 0), ("本文です。", 10.0, 0), ("シナリオ名：霧の山荘", 10.0, 0)]));
        assert_eq!(info.title.unwrap().value, "霧の山荘");
        let info = run(doc(&[("【タイトル】", 10.0, 0), ("『霧の山荘』", 10.0, 0), ("本文です。", 10.0, 0)]));
        assert_eq!(info.title.unwrap().value, "霧の山荘");

        // 「タイトルロゴ：」などは題名の見出しではない
        let info = run(doc(&[("霧の山荘", 30.0, 0), ("タイトルロゴ：山田", 10.0, 0), ("本文です。", 10.0, 0)]));
        assert_eq!(info.title.unwrap().value, "霧の山荘");
    }

    #[test]
    fn heading_decoration_keeps_long_vowel() {
        assert_eq!(clean_heading("▼トレーラー"), "トレーラー");
        assert_eq!(clean_heading("【ストーリー】"), "ストーリー");
        assert_eq!(clean_heading("ーーー あらすじ ーーー"), "あらすじ");
        assert_eq!(clean_heading("―あらすじ―"), "あらすじ");
        assert_eq!(clean_heading("ーー"), "");
    }

    #[test]
    fn system_words_in_titles() {
        let ex = InfoExtractor::new();
        let strip = |t: &str| ex.strip_system_words(t);
        assert_eq!(strip("CoCシナリオ集「オキュランス オブ オカルト」【DLデータ付き!】").as_deref(), Some("オキュランス オブ オカルト"));
        assert_eq!(strip("クトゥルフ神話TRPG「なりかわり様」").as_deref(), Some("なりかわり様"));
        assert_eq!(strip("マーダーミステリー「あやかし夜⾏奇譚」").as_deref(), Some("あやかし夜行奇譚"));
        assert_eq!(strip("【CoC6】霧の山荘").as_deref(), Some("霧の山荘"));
        assert_eq!(strip("霧の山荘（CoC7版対応）").as_deref(), Some("霧の山荘"));
        assert_eq!(strip("マーダーミステリー あやかし夜行奇譚").as_deref(), Some("あやかし夜行奇譚"));
        assert_eq!(strip("新クトゥルフ神話TRPGシナリオ 霧の山荘 / DL版").as_deref(), Some("霧の山荘"));
        assert_eq!(strip("クトゥルフの呼び声").as_deref(), Some("クトゥルフの呼び声"));
        assert_eq!(strip("「霧」の殺人").as_deref(), Some("「霧」の殺人"));
        assert_eq!(strip("Cocoa Night").as_deref(), Some("Cocoa Night"));
        assert_eq!(strip("CoC").as_deref(), None);

        assert_eq!(ex.systems_in("CoCシナリオ集「霧」"), ["クトゥルフ神話TRPG"]);
        assert_eq!(ex.systems_in("新クトゥルフ神話TRPG / マーダーミステリー"), ["新クトゥルフ神話TRPG", "マーダーミステリー"]);
        assert_eq!(ex.systems_in("CoC7対応「霧」"), ["新クトゥルフ神話TRPG"]);
        assert_eq!(ex.systems_in("Cocoa Night"), Vec::<String>::new());
        assert_eq!(ex.systems_in("【マダミス】あやかし夜行奇譚"), ["マーダーミステリー"]);
    }

    #[test]
    fn synopsis_candidates_split_overview() {
        let ex = InfoExtractor::new();
        let lines: Vec<String> = [
            "■シナリオデータ",
            "▼概要",
            "「クトゥルフ神話TRPG」（第６版）",
            "プレイ人数：２人",
            "プレイ時間：４～６時間",
            "プレイ環境：オンライン推奨",
            "推奨技能",
            "目星、心理学",
            "山奥の山荘に招かれた二人は、霧に閉ざされた館で一夜を過ごすことになる。",
            "夜が明けたとき、館の主人の姿はどこにもなかった。",
            "※流血表現があります",
            "▼トレーラー",
            "霧の夜。",
            "館の扉が、静かに閉じた。",
            "▼背景",
            "館の主人は二十年前に失踪している。",
            "▼ハンドアウト",
            "HO1 招待客",
        ]
        .iter()
        .map(|s| s.to_string())
        .collect();
        let c = ex.synopsis_candidates(&lines);
        let got: Vec<(&str, &str)> = c.iter().map(|c| (c.label.as_str(), c.text.as_str())).collect();
        assert_eq!(
            got,
            [
                ("トレーラー", "霧の夜。\n館の扉が、静かに閉じた。"),
                ("概要", "山奥の山荘に招かれた二人は、霧に閉ざされた館で一夜を過ごすことになる。\n夜が明けたとき、館の主人の姿はどこにもなかった。"),
                ("背景", "館の主人は二十年前に失踪している。"),
            ]
        );
        // 概要が仕様だけなら、概要は候補にならない
        let lines: Vec<String> = ["▼概要", "プレイ人数：４人", "プレイ時間：８～９時間", "▼舞台", "現代日本"].iter().map(|s| s.to_string()).collect();
        assert!(ex.synopsis_candidates(&lines).is_empty());
    }

    #[test]
    fn web_description_text() {
        let ex = InfoExtractor::new();
        let lines: Vec<String> = [
            "■制作",
            "【商品名】クトゥルフ神話TRPG「霧の山荘」",
            "■シナリオデータ",
            "▼概要",
            "「クトゥルフ神話TRPG」（第６版）",
            "プレイ人数：２人",
            "プレイ時間：４～６時間（ボイスセッション基準）",
            "▼トレーラー",
            "山奥の山荘に招かれた二人。",
            "霧の夜が明けたとき、館の主人の姿はなかった。",
            "▼ハンドアウト",
            "HO1 招待客",
        ]
        .iter()
        .map(|s| s.to_string())
        .collect();
        let info = ex.extract_text("https://booth.pm/ja/items/1", &lines);
        assert_eq!(info.title.unwrap().value, "霧の山荘");
        assert_eq!(info.overview.unwrap().value, "推奨人数：２人\nプレイ時間：４～６時間（ボイスセッション基準）");
        assert_eq!(info.synopsis.unwrap().value, "山奥の山荘に招かれた二人。\n霧の夜が明けたとき、館の主人の姿はなかった。");
        assert_eq!(info.system.unwrap().value, "クトゥルフ神話TRPG");
        assert_eq!(ex.title_from_name("【パッケージ版】新クトゥルフ神話TRPG 入門シナリオセット「霧の山荘」").as_deref(), Some("霧の山荘"));
        assert_eq!(ex.title_from_name("CoCシナリオ集「霧の山荘」【DLデータ付き!】").as_deref(), Some("霧の山荘"));
        assert_eq!(ex.title_from_name("灯台守の手記").as_deref(), Some("灯台守の手記"));
    }

    #[test]
    fn title_in_brackets_and_weak_title_from_text() {
        let info = run(doc(&[("クトゥルフ神話TRPGシナリオ『灯台守の手記』", 0.0, 0), ("システム:CoC6版", 0.0, 0)]));
        assert_eq!(info.title.unwrap().value, "灯台守の手記");
        let info = run(doc(&[("【はじめにお読みください】", 0.0, 0), ("灯台守の手記", 0.0, 0)]));
        assert_eq!(info.title.unwrap().value, "灯台守の手記");
    }

    #[test]
    fn synopsis_under_overview_skips_spec_lines() {
        let info = run(doc(&[
            ("■概要", 0.0, 0),
            ("PL人数:2人", 0.0, 0),
            ("プレイ時間:3時間", 0.0, 0),
            ("■導入", 0.0, 0),
            ("探索者は友人から奇妙な手紙を受け取る。", 0.0, 0),
            ("■NPC", 0.0, 0),
        ]));
        assert_eq!(info.synopsis.unwrap().value, "探索者は友人から奇妙な手紙を受け取る。");
    }

    #[test]
    fn overview_section_without_specs_becomes_synopsis() {
        // 仕様は別の欄にあり、「概要」の欄は文章だけ → 概要の文章をあらすじにする
        let info = run(doc(&[
            ("霧の山荘", 0.0, 0),
            ("【シナリオ情報】", 0.0, 0),
            ("推奨人数：2人", 0.0, 0),
            ("プレイ時間：4～6時間", 0.0, 0),
            ("【概要】", 0.0, 0),
            ("山奥の山荘に招かれた二人は、霧に閉ざされた館で一夜を過ごすことになる。", 0.0, 0),
            ("【注意事項】", 0.0, 0),
            ("このシナリオには流血表現があります。", 0.0, 0),
        ]));
        assert_eq!(info.synopsis.unwrap().value, "山奥の山荘に招かれた二人は、霧に閉ざされた館で一夜を過ごすことになる。");
        assert!(info.overview.unwrap().value.starts_with("推奨人数：２人\nプレイ時間：４～６時間"));

        // 仕様が書かれた「概要」の欄は、あらすじにしない（後ろに文章が続いていても）
        let info = run(doc(&[
            ("霧の山荘", 0.0, 0),
            ("◆概要", 0.0, 0),
            ("推奨人数：2人", 0.0, 0),
            ("プレイ時間：4～6時間", 0.0, 0),
            ("山奥の山荘に招かれた二人は、霧に閉ざされた館で一夜を過ごす。", 0.0, 0),
        ]));
        assert!(info.synopsis.is_none(), "{:?}", info.synopsis);

        // 仕様の「概要」と、文章の「概要」が別々にあれば、文章のほうをあらすじにする
        let info = run(doc(&[
            ("シナリオ概要：PL2人、4～6時間", 0.0, 0),
            ("■概要", 0.0, 0),
            ("山奥の山荘に招かれた二人。", 0.0, 0),
        ]));
        assert_eq!(info.synopsis.unwrap().value, "山奥の山荘に招かれた二人。");

        // 「あらすじ」の見出しがあれば、そちらを優先する
        let info = run(doc(&[
            ("推奨人数：2人", 0.0, 0),
            ("【概要】", 0.0, 0),
            ("館を舞台にしたクローズドサークルのシナリオです。", 0.0, 0),
            ("【あらすじ】", 0.0, 0),
            ("山奥の山荘に招かれた二人。", 0.0, 0),
        ]));
        assert_eq!(info.synopsis.unwrap().value, "山奥の山荘に招かれた二人。");
    }

    #[test]
    fn synopsis_heading_priority() {
        // 「コネリ」: 仕様の書かれた「シナリオ概要」、GM 向けの「導入」より、「背景」を優先する
        let info = run(doc(&[
            ("『コネリ』", 20.0, 0),
            ("▼シナリオ概要", 15.0, 0),
            ("PL人数：1人", 11.0, 0),
            ("プレイ時間：ボイセで1時間前後", 11.0, 0),
            ("あなたは無心で練り上げる。", 11.0, 0),
            ("▼背景", 15.0, 1),
            ("探索者は大切な人を失った。", 11.0, 1),
            ("それは両親や兄弟、友人、恋人かもしれない。", 11.0, 1),
            ("▼NPC・呪文", 15.0, 1),
            ("・医者", 11.0, 1),
            ("▽導入", 12.0, 2),
            ("※SANを1D6減らす", 10.0, 2),
        ]));
        assert_eq!(info.synopsis.unwrap().value, "探索者は大切な人を失った。\nそれは両親や兄弟、友人、恋人かもしれない。");

        // 文章だけの「概要」があれば、「背景」より優先する（「星の吸血鬼にさよならを」）
        let info = run(doc(&[
            ("♢推奨人数：２人", 9.0, 0),
            ("▼概要", 10.0, 0),
            ("学園の裏山に流れ星が落ちたのを見た。", 9.0, 0),
            ("▼背景", 10.0, 0),
            ("物語は過去に遡る。", 9.0, 0),
        ]));
        assert_eq!(info.synopsis.unwrap().value, "学園の裏山に流れ星が落ちたのを見た。");

        // 「導入」しかなければ「導入」を使う
        let info = run(doc(&[("■導入", 0.0, 0), ("探索者は友人から奇妙な手紙を受け取る。", 0.0, 0)]));
        assert_eq!(info.synopsis.unwrap().value, "探索者は友人から奇妙な手紙を受け取る。");
    }

    #[test]
    fn spoiler_boundary_stops_reading() {
        let info = run(doc(&[("灯台守の手記", 0.0, 0), ("ここから先はKPのみ閲覧してください", 0.0, 0), ("あらすじ", 0.0, 0), ("秘密の本文がここにあります。", 0.0, 0)]));
        assert!(info.synopsis.is_none());
    }

    #[test]
    fn documents_are_ordered_and_spoilers_skipped() {
        let ex = InfoExtractor::new();
        let es: Vec<crate::source::Entry> = [
            "pkg/03_ending/ED.pdf",
            "pkg/02_handout/HO1.pdf",
            "pkg/更新履歴.txt",
            "pkg/edited_photo.png",
            "pkg/01_scenario/本文_edited.pdf",
            "pkg/readme.txt",
        ]
        .iter()
        .enumerate()
        .map(|(i, p)| crate::source::Entry { index: i, path: p.to_string(), size: 0 })
        .collect();
        let order: Vec<String> = ex.ordered_documents(&es).into_iter().map(|(_, p)| p).collect();
        if cfg!(feature = "pdf") {
            assert_eq!(order, ["pkg/readme.txt", "pkg/01_scenario/本文_edited.pdf", "pkg/更新履歴.txt"]);
        } else {
            assert_eq!(order, ["pkg/readme.txt", "pkg/更新履歴.txt"], "pdf feature なしでは PDF は読まない");
        }
    }
}
