//! BOOTH の商品ページ。

use serde::Deserialize;

use super::{Http, SiteFetcher, WebPage, clean_text};

/// BOOTH の商品ページ（`https://booth.pm/ja/items/123456`、`https://shop.booth.pm/items/123456`）。
///
/// 商品ページの URL に `.json` を付けたもの（`https://booth.pm/ja/items/123456.json`）から、
/// 商品名・説明文・画像・タグを読む。
pub struct BoothFetcher {
    /// 取得先（テストでは手元のサーバーに差し替える）。
    pub base: String,
}

impl Default for BoothFetcher {
    fn default() -> Self {
        Self { base: "https://booth.pm".into() }
    }
}

#[derive(Debug, Deserialize)]
struct Item {
    #[serde(default)]
    name: String,
    #[serde(default)]
    description: String,
    #[serde(default)]
    factory_description: Option<String>,
    #[serde(default)]
    images: Vec<Image>,
    #[serde(default)]
    tags: Vec<Tag>,
    #[serde(default)]
    is_adult: bool,
    #[serde(default)]
    url: Option<String>,
    #[serde(default)]
    shop: Option<Shop>,
}

#[derive(Debug, Deserialize)]
struct Shop {
    #[serde(default)]
    name: String,
}

/// BOOTH の商品の JSON から、ショップ名を取り出す。
pub fn shop_name(json: &str) -> Option<String> {
    serde_json::from_str::<Item>(json).ok()?.shop.map(|s| s.name).filter(|n| !n.trim().is_empty())
}

#[derive(Debug, Deserialize)]
struct Image {
    #[serde(default)]
    original: Option<String>,
    #[serde(default)]
    resized: Option<String>,
}

#[derive(Debug, Deserialize)]
struct Tag {
    #[serde(default)]
    name: String,
}

/// BOOTH の商品の URL から商品番号を取り出す。
pub fn item_id(url: &str) -> Option<u64> {
    let rest = url.split_once("://")?.1;
    let (host, path) = rest.split_once('/').unwrap_or((rest, ""));
    let host = host.split(':').next()?.to_ascii_lowercase();
    if host != "booth.pm" && !host.ends_with(".booth.pm") {
        return None;
    }
    let path = path.split(['?', '#']).next().unwrap_or("");
    let segs: Vec<&str> = path.split('/').filter(|s| !s.is_empty()).collect();
    let pos = segs.iter().position(|s| *s == "items")?;
    segs.get(pos + 1)?.trim_end_matches(".json").parse().ok()
}

/// BOOTH の商品の JSON を読む。
pub fn parse_item(json: &str, page_url: &str) -> Result<WebPage, String> {
    let item: Item = serde_json::from_str(json).map_err(|e| format!("BOOTH の商品情報を読めませんでした: {e}"))?;
    let mut text = item.description.replace("\r\n", "\n");
    if let Some(f) = item.factory_description.filter(|f| !f.trim().is_empty()) {
        text.push('\n');
        text.push_str(&f.replace("\r\n", "\n"));
    }
    let lines: Vec<String> = text.lines().map(|l| l.trim_end().to_string()).collect();
    let image_urls = item
        .images
        .iter()
        .filter_map(|i| i.original.clone().or_else(|| i.resized.clone()))
        .filter(|u| u.starts_with("http"))
        .collect();
    Ok(WebPage {
        url: item.url.filter(|u| u.starts_with("http")).unwrap_or_else(|| page_url.to_string()),
        title: Some(clean_text(&item.name)).filter(|t| !t.is_empty()),
        lines: if lines.iter().all(|l| l.trim().is_empty()) { Vec::new() } else { lines },
        summary: None,
        image_urls,
        tags: item.tags.into_iter().map(|t| t.name).filter(|t| !t.is_empty()).collect(),
        is_adult: item.is_adult,
    })
}

impl SiteFetcher for BoothFetcher {
    fn name(&self) -> &'static str {
        "booth"
    }

    fn matches(&self, url: &str) -> bool {
        item_id(url).is_some()
    }

    fn fetch(&self, http: &Http, url: &str) -> Result<WebPage, String> {
        let id = item_id(url).ok_or_else(|| format!("BOOTH の商品の URL ではありません: {url}"))?;
        let base = self.base.trim_end_matches('/');
        let json = http.get_text(&format!("{base}/ja/items/{id}.json"))?;
        let mut page = parse_item(&json, &format!("https://booth.pm/ja/items/{id}"))?;
        // 説明文の下の見出し付きの欄（「▼あらすじ」など）は JSON に入っていないので、商品ページから読む。
        // 読めなくても、JSON の情報だけで続ける。
        if let Ok(html) = http.get_text(&format!("{base}/ja/items/{id}")) {
            let shop = shop_name(&json);
            let sections = description_sections(&html, &page.lines, page.title.as_deref(), shop.as_deref());
            page.lines.extend(sections);
        }
        Ok(page)
    }
}

/// BOOTH の商品ページの見出しのうち、ここから先は BOOTH 自体の案内（説明文ではない）とみなす語。
const FOOTER_HEADINGS: &[&str] = &[
    "boothで", "サポート", "お問い合わせ", "ギフト", "関連", "おすすめ", "新着", "このショップ", "閲覧履歴", "ボード", "シェア",
    "通報", "ショップの",
];

/// タグの外にある改行を `<br>` にする（タグの属性の中の改行はそのまま）。
fn newlines_to_br(html: &str) -> String {
    let mut out = String::with_capacity(html.len() + 256);
    let mut in_tag = false;
    let mut quote: Option<char> = None;
    for c in html.chars() {
        match (in_tag, quote, c) {
            (false, _, '<') => {
                in_tag = true;
                out.push(c);
            }
            (false, _, '\n') => out.push_str("<br>"),
            (true, None, '"' | '\'') => {
                quote = Some(c);
                out.push(c);
            }
            (true, Some(q), _) if c == q => {
                quote = None;
                out.push(c);
            }
            (true, None, '>') => {
                in_tag = false;
                out.push(c);
            }
            _ => out.push(c),
        }
    }
    out
}

/// 商品ページの HTML から、説明文の下にある見出し付きの欄（「▼あらすじ」「▼本作品について」など）の行を取り出す。
///
/// 説明文（JSON の `description`）の最後の行より後ろから読み、次のどれかの手前で止める。
/// - BOOTH 自体の案内の見出し（「BOOTHで「売りたい」」など）
/// - ショップ名だけの行（説明欄の下の「このショップの商品」の始まり）
/// - 価格だけの行（「¥ 370」。ほかの商品の一覧）
///
/// 見出しのタグの行には、見出しとして扱えるよう「■」を付ける（見出しの記号が付いていればそのまま）。
/// BOOTH の説明欄は改行文字で行を区切っている（`whitespace-pre-line`）ので、改行をそのまま行の区切りとする。
pub fn description_sections(html: &str, description: &[String], name: Option<&str>, shop: Option<&str>) -> Vec<String> {
    // BOOTH の HTML はタグの間に改行を入れないので、本文の中の改行だけが残っている。それを <br> にする
    let html = newlines_to_br(&html.replace("\r\n", "\n"));
    let lines = super::html_lines(&html);
    let key = |s: &str| -> String { crate::info::normalize::normalize_line(s).chars().take(20).collect() };
    let desc: Vec<String> = description.iter().map(|l| key(l)).filter(|l| l.chars().count() >= 4).collect();
    let norm: Vec<String> = lines.iter().map(|(l, _)| key(l)).collect();

    // 始まり: 説明文の最後の行が出てきた行の次（なければ、商品名の見出しの次）
    let after_desc = desc.last().and_then(|last| norm.iter().position(|n| n.contains(last.as_str()) || last.contains(n.as_str()) && n.chars().count() >= 4));
    let after_name = name.map(key).and_then(|n| lines.iter().zip(&norm).position(|((_, h), l)| *h && *l == n));
    let Some(start) = after_desc.or(after_name).map(|i| i + 1) else { return Vec::new() };

    let shop_key = shop.map(key);
    let is_price = |t: &str| {
        let t = crate::info::normalize::normalize_line(t);
        t.starts_with('¥') && t[t.find('¥').map_or(0, |i| i + '¥'.len_utf8())..].trim().chars().all(|c| c.is_ascii_digit() || c == ',' || c == '~' || c == '〜')
    };
    let mut out = Vec::new();
    for (text, heading) in &lines[start..] {
        if shop_key.as_deref().is_some_and(|s| key(text) == s) || is_price(text) {
            break;
        }
        if *heading {
            let lower = text.to_lowercase();
            if FOOTER_HEADINGS.iter().any(|w| lower.contains(w)) {
                break;
            }
            out.push(super::as_heading(text));
        } else {
            out.push(text.clone());
        }
        if out.len() >= 600 {
            break;
        }
    }
    // 見出しが1つもなければ、説明文の下の欄ではない（ページの別の部分）とみなす
    if out.iter().any(|l| l.starts_with('■') || l.starts_with('▼')) { out } else { Vec::new() }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn item_ids_from_urls() {
        assert_eq!(item_id("https://booth.pm/ja/items/2728142"), Some(2728142));
        assert_eq!(item_id("https://booth.pm/en/items/2728142?foo=1#top"), Some(2728142));
        assert_eq!(item_id("https://shop-name.booth.pm/items/4378160"), Some(4378160));
        assert_eq!(item_id("https://booth.pm/ja/items/2728142.json"), Some(2728142));
        assert_eq!(item_id("https://booth.pm/ja/browse/TRPG"), None);
        assert_eq!(item_id("https://example.com/items/1"), None);
        assert_eq!(item_id("https://notbooth.pm/items/1"), None);
    }

    #[test]
    fn description_sections_from_item_page() {
        // 実際の BOOTH の商品ページと同じ形（タグの間に改行がなく、説明欄の中だけ改行文字で行を区切る。
        // 説明欄の下には、見出しのないままショップ名・ほかの商品が続く）。文章は試験用のもの。
        let html = concat!(
            "<!DOCTYPE html><html><head><title>マーダーミステリー『夏の約束』 - ショップA - BOOTH</title>",
            "<script type=\"application/ld+json\">{\"description\":\"マーダーミステリー『夏の約束』\\n2人用のシナリオです。\"}</script></head><body>",
            "<header><a>BOOTH</a></header><main><span>ショップA</span>",
            "<h2 class=\"font-bold\">マーダーミステリー『夏の約束』</h2><div class=\"u-tpg-caption1\">ダウンロード商品</div><div class=\"variation-price\">¥ 500</div>",
            "<button><div>ギフトとして贈る</div></button><h4><a>「ギフトとして贈る」とは</a></h4>",
            "<section class=\"main-info-column\"><div class=\"description\"><p class=\"whitespace-pre-line\">マーダーミステリー『夏の約束』\n2人用のシナリオです。\n</p></div></section>",
            "<div class=\"my-40\"><section><section class=\"shop__text\"><h2>▼あらすじ</h2>",
            "<p class=\"whitespace-pre-line\">夏の日差し。\n\n「また会おうね」\n\n約束の場所で、二人は再会する＿＿＿\n</p></section>",
            "<section class=\"shop__text\"><h2>▼本作品について</h2><p class=\"whitespace-pre-line\">人数：2名+GM1人(進行役)\n時間：60分\n準備：Discordのみ</p></section>",
            "<section class=\"shop__text\"><h2>配信について</h2><p class=\"whitespace-pre-line\">配信できます。</p></section></section></div>",
            "<div class=\"shop-items\"><div class=\"shop-name\"><a>ショップA</a></div><ul><li><a>ほかの商品『冬の手紙』</a><div>ショップA</div><div class=\"price\">¥ 0</div></li></ul></div>",
            "</main><footer><nav><h3>BOOTHで「売りたい」</h3><a>ショップを開く</a><h3>サポート・お問い合わせ</h3></nav></footer></body></html>"
        );
        let desc = vec!["マーダーミステリー『夏の約束』".to_string(), "2人用のシナリオです。".to_string()];
        let lines = description_sections(html, &desc, Some("マーダーミステリー『夏の約束』"), Some("ショップA"));
        assert_eq!(
            lines,
            [
                "▼あらすじ",
                "夏の日差し。",
                "「また会おうね」",
                "約束の場所で、二人は再会する＿＿＿",
                "▼本作品について",
                "人数：2名+GM1人(進行役)",
                "時間：60分",
                "準備：Discordのみ",
                "■配信について",
                "配信できます。",
            ]
        );
        // 見出しの欄がないページ
        assert!(description_sections("<html><body><h2>商品名</h2><p>説明</p><h3>BOOTHで「売りたい」</h3></body></html>", &desc, Some("商品名"), None).is_empty());
        // 属性の中の改行は <br> にしない
        assert_eq!(newlines_to_br("<meta content=\"a\nb\"><p>x\ny</p>"), "<meta content=\"a\nb\"><p>x<br>y</p>");
    }

    #[test]
    fn item_json_is_read() {
        let json = r#"{"name":"クトゥルフ神話TRPG「霧の山荘」","description":"■シナリオデータ\r\n▼概要\r\nプレイ人数：２人\r\n","factory_description":null,
            "images":[{"caption":null,"original":"https://booth.pximg.net/x/i/1/a_base_resized.jpg","resized":"https://booth.pximg.net/c/72x72/x/i/1/a.jpg"}],
            "tags":[{"name":"TRPG","url":"https://booth.pm/ja/browse?tags=TRPG"}],"is_adult":false,"url":"https://shop.booth.pm/items/1","id":1}"#;
        let p = parse_item(json, "https://booth.pm/ja/items/1").unwrap();
        assert_eq!(p.title.as_deref(), Some("クトゥルフ神話TRPG「霧の山荘」"));
        assert_eq!(p.lines, ["■シナリオデータ", "▼概要", "プレイ人数：２人"]);
        assert_eq!(p.image_urls, ["https://booth.pximg.net/x/i/1/a_base_resized.jpg"]);
        assert_eq!(p.tags, ["TRPG"]);
        assert_eq!(p.url, "https://shop.booth.pm/items/1");
        assert!(parse_item("<html>", "u").is_err());
    }
}
