//! URL（BOOTH の商品ページなど）からシナリオ情報と表紙画像を取り出す。
//!
//! サイトごとの取り出し方は [`SiteFetcher`] として分けてあり、上から順に URL に一致するものを使う。
//! - [`booth::BoothFetcher`] — BOOTH の商品ページ（`https://booth.pm/ja/items/123` や `https://xxx.booth.pm/items/123`）。
//!   商品ページの URL の末尾に `.json` を付けたものから、商品名・説明文・画像を読む。
//! - [`generic::GenericFetcher`] — それ以外のサイト。ページの共有用の情報（`og:title` `og:description` `og:image`）と
//!   本文のテキストを読む。
//!
//! pixiv などに対応するときは、`SiteFetcher` を実装した型を作って [`WebExtractor::new`] の一覧の先頭に足す。
//!
//! 取り出したテキストは、PDF などと同じ解析器（[`crate::info::InfoExtractor::extract_text`]）にかけるので、
//! 「▼概要」「▼トレーラー」「プレイ人数：」などの読み取り方は文書の場合と同じになる。

pub mod booth;
pub mod generic;
pub mod http;

use serde::Serialize;

use crate::info::{InfoExtractor, InfoValue, ScenarioInfo, SynopsisCandidate};
use crate::thumbnail::{Thumbnail, ThumbnailConfig, make_thumbnail};

pub use http::Http;

/// サイトから取り出した、解析前の情報。
#[derive(Debug, Clone, Default, PartialEq)]
pub struct WebPage {
    /// 実際に読んだ URL（正規化したもの）。
    pub url: String,
    /// 商品名・ページの題名。
    pub title: Option<String>,
    /// 説明文・本文（1行ずつ）。見出しの判定にかける。
    pub lines: Vec<String>,
    /// 説明の要約（`og:description` など）。本文からあらすじが見つからないときに使う。
    pub summary: Option<String>,
    /// 表紙の候補の画像の URL（先頭ほど優先）。
    pub image_urls: Vec<String>,
    /// サイトのタグ。
    pub tags: Vec<String>,
    /// 成人向けの商品か（サイトが教えてくれる場合）。
    pub is_adult: bool,
}

/// サイトごとの取り出し方。
pub trait SiteFetcher: Send + Sync {
    /// サイトの名前（"booth" など）。結果の JSON に入る。
    fn name(&self) -> &'static str;
    /// この URL を扱えるか。
    fn matches(&self, url: &str) -> bool;
    /// ページを読んで、解析前の情報を返す。
    fn fetch(&self, http: &Http, url: &str) -> Result<WebPage, String>;
}

/// URL から取り出した結果。
#[derive(Debug, Clone, Serialize)]
pub struct WebInfo {
    /// 使ったサイトの取り出し方（"booth" / "generic" など）。
    pub site: &'static str,
    /// 読んだ URL。
    pub url: String,
    /// 題名・あらすじ・概要など。題名からはシステム名などの説明を取り除いてある。
    pub info: ScenarioInfo,
    /// ページの題名（商品名）そのもの。
    pub page_title: Option<String>,
    /// ページの題名に含まれていたシステム名（「マーダーミステリー」「クトゥルフ神話TRPG」など）。タグにする。
    pub title_systems: Vec<String>,
    /// あらすじの候補（見出しごと。優先順位の高い順）。`info.synopsis` は先頭のもの。
    pub synopsis_candidates: Vec<SynopsisCandidate>,
    /// サイトのタグ。
    pub tags: Vec<String>,
    /// 表紙に使った画像の URL。
    pub image_url: Option<String>,
    pub is_adult: bool,
    /// 取り出せなかったものの理由（画像が読めなかった、など）。
    pub warnings: Vec<String>,
    /// 表紙のサムネイル（JPEG）。
    #[serde(skip)]
    pub image: Option<Thumbnail>,
}

/// URL からの情報の取り出し。
pub struct WebExtractor {
    http: Http,
    fetchers: Vec<Box<dyn SiteFetcher>>,
}

impl Default for WebExtractor {
    fn default() -> Self {
        Self::new()
    }
}

impl WebExtractor {
    pub fn new() -> Self {
        Self::with_fetchers(
            Http::new(),
            vec![Box::new(booth::BoothFetcher::default()), Box::new(generic::GenericFetcher)],
        )
    }

    /// サイトごとの取り出し方を差し替える（テストや、サイトを追加するとき）。
    /// 一覧の上から順に、URL に一致するものを使う。
    pub fn with_fetchers(http: Http, fetchers: Vec<Box<dyn SiteFetcher>>) -> Self {
        Self { http, fetchers }
    }

    /// URL から題名・あらすじ・概要・表紙画像を取り出す。
    pub fn extract(&self, url: &str, info_ex: &InfoExtractor, thumb: &ThumbnailConfig) -> Result<WebInfo, String> {
        let url = url.trim();
        if !(url.starts_with("http://") || url.starts_with("https://")) {
            return Err(format!("http:// か https:// で始まる URL を指定してください: {url}"));
        }
        let fetcher = self
            .fetchers
            .iter()
            .find(|f| f.matches(url))
            .ok_or_else(|| format!("この URL を扱える取り出し方がありません: {url}"))?;
        let page = fetcher.fetch(&self.http, url)?;
        let mut warnings = Vec::new();

        let mut info = info_ex.extract_text(&page.url, &page.lines);
        // 題名: 説明文の「タイトル：」「商品名：」の見出し → 商品名・ページの題名。
        // どちらも「マーダーミステリー」「CoC」などのシステム名や「シナリオ」「DL版」などの説明は取り除く。
        if let Some(labeled) = info_ex.labeled_title_in(&page.lines) {
            let clean = info_ex.strip_system_words(&labeled).unwrap_or(labeled.clone());
            info.title = Some(InfoValue { value: clean, source_path: page.url.clone(), raw_text: labeled });
        } else if let Some(name) = page.title.as_deref() {
            let clean = info_ex.strip_system_words(name).or_else(|| info_ex.title_from_name(name));
            info.title = clean.map(|t| InfoValue { value: t, source_path: page.url.clone(), raw_text: name.to_string() });
        }
        let title_systems = page.title.as_deref().map(|t| info_ex.systems_in(t)).unwrap_or_default();
        // あらすじ: 見出しごとの候補（あらすじ・トレーラー・概要の文章・背景・導入）と、ページの説明（og:description など）。
        // 「概要」の下にあらすじと人数が並んでいる場合は、人数などの行を飛ばした文章を候補にする。
        let mut synopsis_candidates = info_ex.synopsis_candidates(&page.lines);
        if let Some(s) = page.summary.as_deref().map(str::trim).filter(|s| s.chars().count() >= 10) {
            if !synopsis_candidates.iter().any(|c| c.text == s) {
                synopsis_candidates.push(SynopsisCandidate { label: "ページの説明".into(), text: s.to_string(), tier: 4 });
            }
        }
        if let Some(first) = synopsis_candidates.first() {
            info.synopsis = Some(InfoValue { value: first.text.clone(), source_path: page.url.clone(), raw_text: first.label.clone() });
        }
        if page.lines.is_empty() && page.summary.is_none() {
            warnings.push(if page.is_adult {
                "成人向けの商品のため、説明文を読めませんでした".to_string()
            } else {
                "説明文が見つかりませんでした".to_string()
            });
        }

        // 表紙: 候補の画像を順に読み、最初に読めたもの
        let mut image = None;
        let mut image_url = None;
        for u in page.image_urls.iter().take(3) {
            match self.http.get_bytes(u, Some(&page.url), http::MAX_IMAGE_BYTES).and_then(|b| make_thumbnail(&b, thumb).map_err(|e| e.to_string())) {
                Ok(t) => {
                    image = Some(t);
                    image_url = Some(u.clone());
                    break;
                }
                Err(e) => warnings.push(format!("画像を読めませんでした（{u}）: {e}")),
            }
        }
        if page.image_urls.is_empty() {
            warnings.push("表紙の画像が見つかりませんでした".to_string());
        }

        Ok(WebInfo {
            site: fetcher.name(),
            url: page.url,
            info,
            page_title: page.title,
            title_systems,
            synopsis_candidates,
            tags: page.tags,
            image_url,
            is_adult: page.is_adult,
            warnings,
            image,
        })
    }
}

/// HTML の本文を行に分ける。見出しのタグ（h1〜h6）の行は `true` を付けて返す。
///
/// クラス名などには頼らず、タグの種類だけを見る（サイトのデザインが変わっても壊れにくいように）。
pub(crate) fn html_lines(html: &str) -> Vec<(String, bool)> {
    const MARK: char = '\u{E000}';
    // 見出しのタグの中身の先頭に目印を入れてから、テキストにする
    let lower = html.to_ascii_lowercase();
    let bytes = lower.as_bytes();
    let mut marked = String::with_capacity(html.len() + 64);
    let mut last = 0;
    let mut i = 0;
    while let Some(p) = lower[i..].find("<h") {
        let at = i + p;
        let level = bytes.get(at + 2).copied();
        let after = bytes.get(at + 3).copied();
        let is_heading = matches!(level, Some(b'1'..=b'6')) && matches!(after, Some(b'>' | b' ' | b'\t' | b'\n' | b'\r' | b'/'));
        if is_heading {
            if let Some(gt) = lower[at..].find('>') {
                let end = at + gt + 1;
                marked.push_str(&html[last..end]);
                marked.push(MARK);
                last = end;
                i = end;
                continue;
            }
        }
        i = at + 2;
    }
    marked.push_str(&html[last..]);
    crate::info::text::html_to_text(&marked)
        .lines()
        .map(|l| {
            let heading = l.contains(MARK);
            (l.replace(MARK, "").trim().to_string(), heading)
        })
        .filter(|(l, _)| !l.is_empty())
        .collect()
}

/// 見出しの行の先頭に、見出しの記号がなければ「■」を付ける（解析器が見出しとして扱えるように）。
pub(crate) fn as_heading(text: &str) -> String {
    const MARKS: &[char] = &['▼', '▽', '◆', '◇', '♢', '♦', '●', '○', '◎', '■', '□', '▲', '△', '★', '☆', '►', '▶', '#', '【', '['];
    if text.starts_with(MARKS) { text.to_string() } else { format!("■{text}") }
}

/// HTML の文字参照（`&amp;` など）と前後の空白を整える。
pub(crate) fn clean_text(s: &str) -> String {
    crate::info::text::html_to_text(&s.replace('<', "&lt;")).trim().to_string()
}
