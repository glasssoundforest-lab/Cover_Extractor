//! BOOTH 以外のサイト（共有用の情報と本文を読む）。

use super::{Http, SiteFetcher, WebPage, clean_text};

/// どのサイトにも使える取り出し方。
///
/// - 題名: `og:title` → `<title>`
/// - あらすじの代わり: `og:description` → `<meta name="description">`
/// - 表紙: `og:image` → `twitter:image`
/// - 本文: `<body>` のテキスト（見出しの判定にかける）
pub struct GenericFetcher;

impl SiteFetcher for GenericFetcher {
    fn name(&self) -> &'static str {
        "generic"
    }

    fn matches(&self, url: &str) -> bool {
        url.starts_with("http://") || url.starts_with("https://")
    }

    fn fetch(&self, http: &Http, url: &str) -> Result<WebPage, String> {
        let html = http.get_text(url)?;
        Ok(parse_html(&html, url))
    }
}

/// HTML から、共有用の情報と本文を取り出す。
pub fn parse_html(html: &str, url: &str) -> WebPage {
    let metas = meta_tags(html);
    let get = |keys: &[&str]| {
        keys.iter().find_map(|k| {
            metas
                .iter()
                .find(|(n, v)| n.eq_ignore_ascii_case(k) && !v.trim().is_empty())
                .map(|(_, v)| clean_text(v))
        })
    };
    let title = get(&["og:title", "twitter:title"]).or_else(|| tag_text(html, "title").map(|t| clean_text(&t)));
    let summary = get(&["og:description", "twitter:description", "description"]);
    let image_urls: Vec<String> = ["og:image", "og:image:url", "og:image:secure_url", "twitter:image"]
        .iter()
        .filter_map(|k| get(&[k]))
        .map(|u| absolute_url(url, &u))
        .fold(Vec::new(), |mut v, u| {
            if !v.contains(&u) {
                v.push(u);
            }
            v
        });
    let body = body_html(html);
    // 見出しのタグ（h1〜h6）の行は、見出しとして扱えるように先頭に「■」を付ける
    let lines: Vec<String> =
        super::html_lines(body).into_iter().map(|(l, heading)| if heading { super::as_heading(&l) } else { l }).collect();
    let canonical = get(&["og:url"]).filter(|u| u.starts_with("http")).unwrap_or_else(|| url.to_string());
    WebPage { url: canonical, title, lines, summary, image_urls, tags: Vec::new(), is_adult: false }
}

/// `<meta property="..." content="...">` / `<meta name="..." content="...">` の一覧。
fn meta_tags(html: &str) -> Vec<(String, String)> {
    let mut out = Vec::new();
    let lower = html.to_ascii_lowercase();
    let mut from = 0;
    while let Some(p) = lower[from..].find("<meta") {
        let start = from + p;
        let Some(end) = lower[start..].find('>').map(|e| start + e) else { break };
        let attrs = attributes(&html[start + 5..end]);
        let key = attrs.iter().find(|(k, _)| k == "property" || k == "name").map(|(_, v)| v.clone());
        let content = attrs.iter().find(|(k, _)| k == "content").map(|(_, v)| v.clone());
        if let (Some(k), Some(c)) = (key, content) {
            out.push((k, c));
        }
        from = end + 1;
    }
    out
}

/// タグの属性（`name="value"` / `name='value'` / `name=value`）。名前は小文字にする。
fn attributes(s: &str) -> Vec<(String, String)> {
    let chars: Vec<char> = s.chars().collect();
    let mut out = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        while i < chars.len() && (chars[i].is_whitespace() || chars[i] == '/') {
            i += 1;
        }
        let ks = i;
        while i < chars.len() && !chars[i].is_whitespace() && chars[i] != '=' {
            i += 1;
        }
        let key: String = chars[ks..i].iter().collect::<String>().to_ascii_lowercase();
        while i < chars.len() && chars[i].is_whitespace() {
            i += 1;
        }
        if i < chars.len() && chars[i] == '=' {
            i += 1;
            while i < chars.len() && chars[i].is_whitespace() {
                i += 1;
            }
            let value = if i < chars.len() && (chars[i] == '"' || chars[i] == '\'') {
                let q = chars[i];
                i += 1;
                let vs = i;
                while i < chars.len() && chars[i] != q {
                    i += 1;
                }
                let v: String = chars[vs..i].iter().collect();
                i += 1;
                v
            } else {
                let vs = i;
                while i < chars.len() && !chars[i].is_whitespace() {
                    i += 1;
                }
                chars[vs..i].iter().collect()
            };
            if !key.is_empty() {
                out.push((key, value));
            }
        } else if key.is_empty() {
            i += 1;
        }
    }
    out
}

fn tag_text(html: &str, tag: &str) -> Option<String> {
    let lower = html.to_ascii_lowercase();
    let open = lower.find(&format!("<{tag}"))?;
    let start = open + lower[open..].find('>')? + 1;
    let end = start + lower[start..].find(&format!("</{tag}"))?;
    Some(html[start..end].to_string())
}

/// `<body>` の中身（なければ全体）。
fn body_html(html: &str) -> &str {
    let lower = html.to_ascii_lowercase();
    let Some(open) = lower.find("<body") else { return html };
    let Some(gt) = lower[open..].find('>') else { return html };
    let start = open + gt + 1;
    let end = lower[start..].rfind("</body").map(|e| start + e).unwrap_or(html.len());
    &html[start..end]
}

/// 相対 URL（`/img/a.jpg`、`//cdn/a.jpg`、`a.jpg`）を、ページの URL を基準に絶対 URL にする。
fn absolute_url(page: &str, u: &str) -> String {
    let u = u.trim();
    if u.starts_with("http://") || u.starts_with("https://") {
        return u.to_string();
    }
    let (scheme, rest) = page.split_once("://").unwrap_or(("https", page));
    if let Some(r) = u.strip_prefix("//") {
        return format!("{scheme}://{r}");
    }
    let host = rest.split('/').next().unwrap_or(rest);
    if u.starts_with('/') {
        return format!("{scheme}://{host}{u}");
    }
    let path = rest.split(['?', '#']).next().unwrap_or(rest);
    let dir = path.rsplit_once('/').map(|(d, _)| d).unwrap_or(host);
    format!("{scheme}://{dir}/{u}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn open_graph_and_body_are_read() {
        let html = r#"<!doctype html><html><head><title>霧の山荘 | 作品ページ</title>
            <meta property="og:title" content="霧の山荘">
            <meta name="description" content="山奥の山荘に招かれた二人の物語。&amp;ホラー">
            <meta property='og:image' content='/img/cover.png'/>
            <meta property="og:image" content="/img/cover.png">
            </head><body><h2>シナリオ情報</h2><p>推奨人数：2人<br>プレイ時間：4～6時間</p></body></html>"#;
        let p = parse_html(html, "https://example.com/works/kiri.html?x=1");
        assert_eq!(p.title.as_deref(), Some("霧の山荘"));
        assert_eq!(p.summary.as_deref(), Some("山奥の山荘に招かれた二人の物語。&ホラー"));
        assert_eq!(p.image_urls, ["https://example.com/img/cover.png"]);
        assert_eq!(p.lines, ["■シナリオ情報", "推奨人数：2人", "プレイ時間：4～6時間"]);
    }

    #[test]
    fn relative_urls() {
        assert_eq!(absolute_url("https://a.jp/x/y.html", "//cdn.jp/i.png"), "https://cdn.jp/i.png");
        assert_eq!(absolute_url("https://a.jp/x/y.html", "i.png"), "https://a.jp/x/i.png");
        assert_eq!(absolute_url("https://a.jp", "/i.png"), "https://a.jp/i.png");
    }
}
