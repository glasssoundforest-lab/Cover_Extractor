//! 形式ごとのテキスト抽出器（プラグイン）。

use encoding_rs::{SHIFT_JIS, UTF_16BE, UTF_16LE};

pub const MAX_LINES: usize = 20_000;
pub const MAX_LINE_CHARS: usize = 2_000;

/// 文書1件の読み込み上限（バイト）。シナリオ PDF は画像入りで大きいことがあるので余裕を持たせる。
pub const MAX_DOCUMENT_BYTES: u64 = 256 * 1024 * 1024;

/// PDF から読むページ数。表紙・目次の後にあらすじが来ることが多いので数ページ先まで読む。
pub const PDF_MAX_PAGES: usize = 8;

pub trait TextExtractor: Send + Sync {
    fn name(&self) -> &'static str;
    fn accepts(&self, extension: &str) -> bool;
    fn extract(&self, bytes: &[u8]) -> Result<Vec<String>, String>;
}

/// 文書の1行。
#[derive(Debug, Clone, PartialEq)]
pub struct DocLine {
    pub text: String,
    /// 文字の大きさ（PDF のみ。分からなければ 0）。タイトルや見出しの判定に使う。
    pub size: f32,
    /// ページ番号（0 始まり。PDF 以外は 0）。
    pub page: u16,
}

/// 文書から取り出したテキスト。
#[derive(Debug, Clone, PartialEq)]
pub struct DocText {
    pub is_pdf: bool,
    pub lines: Vec<DocLine>,
}

/// 情報を読む対象の文書かどうか（拡張子で判定）。
pub fn is_document_path(path: &str) -> bool {
    let ext = crate::names::extension(path).unwrap_or_default();
    ext == "pdf" && cfg!(feature = "pdf")
        || PlainTextExtractor.accepts(&ext)
        || MarkdownExtractor.accepts(&ext)
        || HtmlExtractor.accepts(&ext)
        || JsonExtractor.accepts(&ext)
}

/// 拡張子に応じた抽出器で、文書を行に分ける。
pub fn extract_document(path: &str, bytes: &[u8]) -> Result<DocText, String> {
    let ext = crate::names::extension(path).unwrap_or_default();
    if ext == "pdf" {
        let lines = pdf_sized_lines(bytes, PDF_MAX_PAGES)?;
        return Ok(DocText { is_pdf: true, lines });
    }
    let extractors: [&dyn TextExtractor; 4] = [&PlainTextExtractor, &MarkdownExtractor, &HtmlExtractor, &JsonExtractor];
    let ex = extractors
        .into_iter()
        .find(|e| e.accepts(&ext))
        .ok_or_else(|| format!("unsupported document type: {path}"))?;
    let lines = ex.extract(bytes)?;
    Ok(DocText {
        is_pdf: false,
        lines: lines.into_iter().map(|text| DocLine { text, size: 0.0, page: 0 }).collect(),
    })
}

pub(crate) fn bounded_lines<'a>(lines: impl Iterator<Item = &'a str>) -> Vec<String> {
    lines
        .take(MAX_LINES)
        .map(|l| {
            if l.chars().count() > MAX_LINE_CHARS { l.chars().take(MAX_LINE_CHARS).collect() } else { l.to_string() }
        })
        .collect()
}

pub fn decode_text(bytes: &[u8]) -> (String, &'static str) {
    if let Some(rest) = bytes.strip_prefix(b"\xEF\xBB\xBF") {
        return (String::from_utf8_lossy(rest).into_owned(), "utf-8");
    }
    if bytes.starts_with(b"\xFF\xFE") {
        return (UTF_16LE.decode_with_bom_removal(bytes).0.into_owned(), "utf-16le");
    }
    if bytes.starts_with(b"\xFE\xFF") {
        return (UTF_16BE.decode_with_bom_removal(bytes).0.into_owned(), "utf-16be");
    }
    if let Ok(s) = std::str::from_utf8(bytes) {
        return (s.to_string(), "utf-8");
    }
    let mut best: Option<(f32, String, &'static str)> = None;
    let mut consider = |text: Option<String>, name: &'static str| {
        if let Some(t) = text {
            let score = plausibility(&t);
            if best.as_ref().is_none_or(|(s, ..)| score > *s) {
                best = Some((score, t, name));
            }
        }
    };
    if bytes.len().is_multiple_of(2) {
        consider(UTF_16LE.decode_without_bom_handling_and_without_replacement(bytes).map(|c| c.into_owned()), "utf-16le");
        consider(UTF_16BE.decode_without_bom_handling_and_without_replacement(bytes).map(|c| c.into_owned()), "utf-16be");
    }
    consider(SHIFT_JIS.decode_without_bom_handling_and_without_replacement(bytes).map(|c| c.into_owned()), "cp932");
    if let Some((score, text, name)) = best {
        if score >= 0.6 {
            return (text, name);
        }
    }
    (String::from_utf8_lossy(bytes).into_owned(), "unknown")
}

fn plausibility(text: &str) -> f32 {
    let mut total = 0usize;
    let mut good = 0usize;
    for c in text.chars().take(8192) {
        total += 1;
        let ok = matches!(c, ' '..='~' | '\n' | '\r' | '\t')
            || matches!(c as u32, 0x3000..=0x30FF | 0x4E00..=0x9FFF | 0xFF01..=0xFF5E | 0x2010..=0x2312 | 0x25A0..=0x26FF);
        good += usize::from(ok);
    }
    if total == 0 { 0.0 } else { good as f32 / total as f32 }
}

pub struct PlainTextExtractor;

impl TextExtractor for PlainTextExtractor {
    fn name(&self) -> &'static str {
        "text"
    }
    fn accepts(&self, ext: &str) -> bool {
        matches!(ext, "txt" | "text")
    }
    fn extract(&self, bytes: &[u8]) -> Result<Vec<String>, String> {
        let (text, _) = decode_text(bytes);
        Ok(bounded_lines(text.lines()))
    }
}

pub struct MarkdownExtractor;

impl TextExtractor for MarkdownExtractor {
    fn name(&self) -> &'static str {
        "markdown"
    }
    fn accepts(&self, ext: &str) -> bool {
        matches!(ext, "md" | "markdown")
    }
    fn extract(&self, bytes: &[u8]) -> Result<Vec<String>, String> {
        let (text, _) = decode_text(bytes);
        let lines = bounded_lines(text.lines());
        Ok(lines.iter().map(|l| markdown_line(l)).collect())
    }
}

pub fn markdown_line(line: &str) -> String {
    let mut s = String::with_capacity(line.len());
    let mut rest = line;
    while let Some(open) = rest.find('[') {
        let Some(close) = rest[open..].find("](").map(|i| open + i) else { break };
        let Some(end) = rest[close..].find(')').map(|i| close + i) else { break };
        let before = rest[..open].strip_suffix('!').unwrap_or(&rest[..open]);
        s.push_str(before);
        s.push_str(&rest[open + 1..close]);
        rest = &rest[end + 1..];
    }
    s.push_str(rest);
    let s = s.replace("**", "").replace("__", "").replace("~~", "").replace('`', "");
    let t = s.trim();
    if t.starts_with('|') && t.ends_with('|') && t.len() >= 2 {
        let cells: Vec<&str> = t[1..t.len() - 1].split('|').map(str::trim).collect();
        if cells.iter().all(|c| !c.is_empty() && c.chars().all(|ch| matches!(ch, '-' | ':' | ' '))) {
            return String::new();
        }
        return join_cells(&cells);
    }
    s
}

fn join_cells(cells: &[&str]) -> String {
    match cells {
        [a, b] => format!("{a}: {b}"),
        _ => cells.join(" | "),
    }
}

pub struct HtmlExtractor;

impl TextExtractor for HtmlExtractor {
    fn name(&self) -> &'static str {
        "html"
    }
    fn accepts(&self, ext: &str) -> bool {
        matches!(ext, "html" | "htm" | "xhtml")
    }
    fn extract(&self, bytes: &[u8]) -> Result<Vec<String>, String> {
        let (html, _) = decode_text(bytes);
        let text = html_to_text(&html);
        Ok(bounded_lines(text.lines()))
    }
}

pub fn html_to_text(html: &str) -> String {
    const BLOCKS: &[&str] = &[
        "br", "p", "div", "li", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "section", "article",
        "header", "footer", "table", "ul", "ol", "dl", "blockquote", "pre", "hr",
    ];
    let mut out = String::with_capacity(html.len() / 2);
    let mut rest = html;
    let mut skip_until: Option<&'static str> = None;
    let mut cell_in_row = 0usize;
    let mut after_dt = false;
    let mut in_pre = false;
    let push_text = |out: &mut String, text: &str, in_pre: bool| {
        if in_pre {
            out.push_str(&decode_entities(text));
        } else {
            let collapsed: String = text.chars().map(|c| if c.is_whitespace() { ' ' } else { c }).collect();
            out.push_str(&decode_entities(&collapsed));
        }
    };
    while let Some(lt) = rest.find('<') {
        if skip_until.is_none() {
            push_text(&mut out, &rest[..lt], in_pre);
        }
        let after = &rest[lt + 1..];
        let Some(gt) = after.find('>') else {
            rest = "";
            break;
        };
        let tag = after[..gt].trim();
        rest = &after[gt + 1..];
        let closing = tag.starts_with('/');
        let name: String = tag
            .trim_start_matches('/')
            .chars()
            .take_while(|c| c.is_ascii_alphanumeric())
            .collect::<String>()
            .to_ascii_lowercase();
        if let Some(end) = skip_until {
            if closing && name == end {
                skip_until = None;
            }
            continue;
        }
        if !closing && (name == "script" || name == "style") {
            skip_until = Some(if name == "script" { "script" } else { "style" });
            continue;
        }
        if name == "pre" {
            in_pre = !closing;
        }
        if closing {
            if BLOCKS.contains(&name.as_str()) && !matches!(name.as_str(), "td" | "th" | "dt") {
                out.push('\n');
            }
            continue;
        }
        match name.as_str() {
            "tr" => {
                cell_in_row = 0;
                out.push('\n');
            }
            "td" | "th" => {
                cell_in_row += 1;
                out.push_str(match cell_in_row {
                    1 => "\n",
                    2 => ": ",
                    _ => " | ",
                });
            }
            "dt" => {
                after_dt = true;
                out.push('\n');
            }
            "dd" if after_dt => {
                after_dt = false;
                out.push_str(": ");
            }
            n if BLOCKS.contains(&n) => {
                after_dt = false;
                out.push('\n');
            }
            _ => {}
        }
    }
    if skip_until.is_none() {
        push_text(&mut out, rest, in_pre);
    }
    out
}

fn decode_entities(s: &str) -> String {
    if !s.contains('&') {
        return s.to_string();
    }
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    while let Some(amp) = rest.find('&') {
        out.push_str(&rest[..amp]);
        let after = &rest[amp + 1..];
        let end = after.find(';').filter(|&e| e <= 10);
        let decoded = end.and_then(|e| {
            let ent = &after[..e];
            let c = match ent {
                "amp" => Some('&'),
                "lt" => Some('<'),
                "gt" => Some('>'),
                "quot" => Some('"'),
                "apos" | "#39" => Some('\''),
                "nbsp" => Some(' '),
                _ if ent.starts_with("#x") || ent.starts_with("#X") => {
                    u32::from_str_radix(&ent[2..], 16).ok().and_then(char::from_u32)
                }
                _ if ent.starts_with('#') => ent[1..].parse::<u32>().ok().and_then(char::from_u32),
                _ => None,
            };
            c.map(|c| (c, e))
        });
        match decoded {
            Some((c, e)) => {
                out.push(c);
                rest = &after[e + 1..];
            }
            None => {
                out.push('&');
                rest = after;
            }
        }
    }
    out.push_str(rest);
    out
}

pub struct JsonExtractor;

impl TextExtractor for JsonExtractor {
    fn name(&self) -> &'static str {
        "json"
    }
    fn accepts(&self, ext: &str) -> bool {
        ext == "json"
    }
    fn extract(&self, bytes: &[u8]) -> Result<Vec<String>, String> {
        let (text, _) = decode_text(bytes);
        let value: serde_json::Value = serde_json::from_str(&text).map_err(|e| format!("invalid JSON: {e}"))?;
        let mut lines = Vec::new();
        flatten_json(&value, None, 0, &mut lines);
        Ok(bounded_lines(lines.iter().map(String::as_str)))
    }
}

fn flatten_json(v: &serde_json::Value, key: Option<&str>, depth: usize, out: &mut Vec<String>) {
    use serde_json::Value;
    if depth > 4 || out.len() >= MAX_LINES {
        return;
    }
    let scalar = |v: &Value| match v {
        Value::String(s) => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        Value::Bool(b) => Some(b.to_string()),
        _ => None,
    };
    match v {
        Value::Object(map) => {
            let get = |k: &str| map.iter().find(|(key, _)| key.eq_ignore_ascii_case(k)).and_then(|(_, v)| scalar(v));
            if let (Some(a), Some(b)) = (get("min_players"), get("max_players")) {
                out.push(format!("players: {a}〜{b}"));
            }
            if let (Some(a), Some(b)) = (get("min_hours").or(get("min_playtime")), get("max_hours").or(get("max_playtime"))) {
                out.push(format!("play time: {a}〜{b}時間"));
            }
            for (k, child) in map {
                flatten_json(child, Some(k), depth + 1, out);
            }
        }
        Value::Array(items) => {
            let parts: Vec<String> = items.iter().filter_map(scalar).collect();
            if let (Some(k), false) = (key, parts.is_empty()) {
                out.push(format!("{k}: {}", parts.join("、")));
            }
            for item in items.iter().filter(|i| i.is_object()) {
                flatten_json(item, None, depth + 1, out);
            }
        }
        other => {
            if let (Some(k), Some(s)) = (key, scalar(other)) {
                out.push(format!("{k}: {s}"));
            }
        }
    }
}

pub struct PdfTextExtractor {
    pub max_pages: usize,
}

impl Default for PdfTextExtractor {
    fn default() -> Self {
        Self { max_pages: 4 }
    }
}

impl TextExtractor for PdfTextExtractor {
    fn name(&self) -> &'static str {
        "pdf"
    }
    fn accepts(&self, ext: &str) -> bool {
        cfg!(feature = "pdf") && ext == "pdf"
    }
    fn extract(&self, bytes: &[u8]) -> Result<Vec<String>, String> {
        Ok(pdf_sized_lines(bytes, self.max_pages)?.into_iter().map(|l| l.text).collect())
    }
}

#[cfg(not(feature = "pdf"))]
fn pdf_sized_lines(_bytes: &[u8], _max_pages: usize) -> Result<Vec<DocLine>, String> {
    Err("PDF support is disabled (build with the `pdf` feature)".into())
}

#[cfg(feature = "pdf")]
fn pdf_sized_lines(bytes: &[u8], max_pages: usize) -> Result<Vec<DocLine>, String> {
    use hayro::hayro_interpret::font::GlyphRun;
    use hayro::hayro_interpret::hayro_cmap::BfString;
    use hayro::hayro_interpret::util::TransformExt;
    use hayro::hayro_interpret::{
        BlendMode, ClipPath, Context, Device, DrawMode, DrawProps, Image, ImageDrawProps, InterpreterCache,
        InterpreterSettings, SoftMask, interpret_page,
    };
    use hayro::hayro_syntax::Pdf;
    use hayro::kurbo::{BezPath, Rect};

    const MAX_GLYPHS: usize = 200_000;

    struct Glyph {
        x: f64,
        y: f64,
        size: f64,
        text: String,
    }

    struct TextCollector {
        glyphs: Vec<Glyph>,
    }

    impl<'a> Device<'a> for TextCollector {
        fn draw_path(&mut self, _: &BezPath, _: DrawProps<'a>, _: &DrawMode) {}
        fn push_clip_path(&mut self, _: &ClipPath) {}
        fn push_transparency_group(&mut self, _: f32, _: Option<SoftMask<'a>>, _: BlendMode) {}
        fn draw_glyph_run(&mut self, run: &GlyphRun<'_, 'a>, props: DrawProps<'a>, _: &DrawMode) {
            for g in run.glyphs() {
                if self.glyphs.len() >= MAX_GLYPHS {
                    return;
                }
                let Some(u) = g.as_unicode() else { continue };
                let text = match u {
                    BfString::Char(c) => c.to_string(),
                    BfString::String(s) => s,
                };
                let c = (props.transform * g.transform()).as_coeffs();
                let size = ((c[0] * c[3] - c[1] * c[2]).abs()).sqrt() * 1000.0;
                if !(c[4].is_finite() && c[5].is_finite() && size.is_finite()) {
                    continue;
                }
                self.glyphs.push(Glyph { x: c[4], y: c[5], size: size.max(0.1), text });
            }
        }
        fn draw_image(&mut self, _: Image<'a, '_>, _: ImageDrawProps<'a>) {}
        fn pop_clip(&mut self) {}
        fn pop_transparency_group(&mut self) {}
    }

    let data = bytes.to_vec();
    let result = std::panic::catch_unwind(move || {
        let pdf = Pdf::new(data).map_err(|e| format!("cannot open PDF: {e:?}"))?;
        let mut lines = Vec::new();
        let cache = InterpreterCache::new();
        for (page_no, page) in pdf.pages().iter().take(max_pages).enumerate() {
            let (w, h) = page.render_dimensions();
            let mut dev = TextCollector { glyphs: Vec::new() };
            let mut ctx = Context::new(
                page.initial_transform(true).to_kurbo(),
                Rect::new(0.0, 0.0, w as f64, h as f64),
                &cache,
                page.xref(),
                InterpreterSettings::default(),
            );
            interpret_page(page, &mut ctx, &mut dev);
            let glyphs: Vec<RawGlyph> = dev.glyphs.into_iter().map(|g| (g.x, g.y, g.size, g.text)).collect();
            let grouped: Vec<(String, f64)> =
                split_columns(glyphs, 0).into_iter().flat_map(group_into_sized_lines).collect();
            for (text, size) in grouped {
                let text = if text.chars().count() > MAX_LINE_CHARS { text.chars().take(MAX_LINE_CHARS).collect() } else { text };
                lines.push(DocLine { text, size: size as f32, page: page_no.min(u16::MAX as usize) as u16 });
            }
            if lines.len() >= MAX_LINES {
                lines.truncate(MAX_LINES);
                break;
            }
        }
        Ok::<_, String>(lines)
    });
    result.unwrap_or_else(|_| Err("PDF text extraction panicked".into()))
}

/// PDF の1文字（x, y, 大きさ, 文字）。y は下に向かって増える。
pub(crate) type RawGlyph = (f64, f64, f64, String);

/// 文字1つ分の幅の目安（全角は大きさと同じ、半角はその 0.6 倍）。
fn advance(g: &RawGlyph) -> f64 {
    let wide = g.3.chars().next().is_some_and(super::normalize::is_cjk);
    g.2 * if wide { 1.0 } else { 0.6 }
}

/// 段組みのページを、段ごとの文字のまとまりに分ける（読む順に並べる）。
///
/// 縦に文字のない帯（段の間の余白）が、ページの中ほどにあり、その左右の両方に文字のある行が多ければ、
/// 2段組みとみなす。左右の段をまたぐ行（見出しなど）があれば、そこでページを上下に区切り、
/// 区切りごとに「左の段 → 右の段」の順に読む。段の中がさらに段組みなら、もう一段階分ける。
///
/// 表（左のセルが見出し、右のセルが値）を段組みと取り違えないよう、左の段の行の多くが
/// 余白の近くまで文字で埋まっている（文章が段の幅いっぱいに流し込まれている）場合だけ段組みとみなす。
#[cfg_attr(not(feature = "pdf"), allow(dead_code))]
pub(crate) fn split_columns(glyphs: Vec<RawGlyph>, depth: usize) -> Vec<Vec<RawGlyph>> {
    if depth >= 2 || glyphs.len() < 40 {
        return vec![glyphs];
    }
    let rows = assign_rows(&glyphs);
    let nrows = rows.iter().copied().max().map_or(0, |m| m + 1);
    if nrows < 6 {
        return vec![glyphs];
    }
    let visible = |g: &RawGlyph| !g.3.trim().is_empty() && g.2 > 0.0;

    // 行ごとの、文字で埋まっている区間（近い文字はつなげる）
    let mut spans: Vec<Vec<(f64, f64)>> = vec![Vec::new(); nrows];
    let mut order: Vec<usize> = (0..glyphs.len()).filter(|&i| visible(&glyphs[i])).collect();
    order.sort_by(|&a, &b| rows[a].cmp(&rows[b]).then(glyphs[a].0.total_cmp(&glyphs[b].0)));
    for &i in &order {
        let g = &glyphs[i];
        let (x0, x1) = (g.0, g.0 + advance(g));
        let row = &mut spans[rows[i]];
        match row.last_mut() {
            Some(last) if x0 <= last.1 + g.2 * 0.6 => last.1 = last.1.max(x1),
            _ => row.push((x0, x1)),
        }
    }
    let text_rows: Vec<usize> = (0..nrows).filter(|&r| !spans[r].is_empty()).collect();
    if text_rows.len() < 6 {
        return vec![glyphs];
    }
    let min_x = text_rows.iter().map(|&r| spans[r][0].0).fold(f64::INFINITY, f64::min);
    let max_x = text_rows.iter().map(|&r| spans[r].last().map_or(0.0, |s| s.1)).fold(f64::NEG_INFINITY, f64::max);
    let width = max_x - min_x;
    let mut sizes: Vec<f64> = order.iter().map(|&i| glyphs[i].2).collect();
    sizes.sort_by(f64::total_cmp);
    let size = sizes[sizes.len() / 2];
    if !(width > size * 20.0) {
        return vec![glyphs];
    }

    // 余白の候補: ページの中ほどで、文字のない帯（1pt 刻みで調べる）
    let crosses = |r: usize, x: f64| spans[r].iter().any(|&(a, b)| a < x && x < b);
    let lo = min_x + width * 0.25;
    let hi = min_x + width * 0.75;
    let allowed = (text_rows.len() as f64 * 0.12).floor() as usize;
    let mut best: Option<(usize, f64, f64)> = None; // (左右に文字がある行の数, 帯の左端, 帯の右端)
    let mut x = lo;
    while x < hi {
        let crossing = text_rows.iter().filter(|&&r| crosses(r, x)).count();
        if crossing <= allowed {
            let start = x;
            while x < hi && text_rows.iter().filter(|&&r| crosses(r, x)).count() <= allowed {
                x += 1.0;
            }
            let (a, b) = (start, x);
            if b - a >= size * 0.8 {
                let mid = (a + b) / 2.0;
                let both = text_rows
                    .iter()
                    .filter(|&&r| !crosses(r, mid) && spans[r][0].0 < a && spans[r].last().is_some_and(|s| s.1 > b))
                    .count();
                if best.is_none_or(|(n, ..)| both > n) {
                    best = Some((both, a, b));
                }
            }
        }
        x += 1.0;
    }
    let Some((both, gap_left, gap_right)) = best else {
        return vec![glyphs];
    };
    if both < 3 || (both as f64) < text_rows.len() as f64 * 0.2 {
        return vec![glyphs];
    }
    let gutter = (gap_left + gap_right) / 2.0;

    // 左の段が文章の段か（表の見出しのセルではないか）。
    // 段の幅いっぱいまで文字が流し込まれた行が多く、行の長さ（中央値）が 10 文字分以上あれば文章の段とみなす。
    let left: Vec<(f64, f64)> = text_rows
        .iter()
        .filter_map(|&r| {
            let side: Vec<&(f64, f64)> = spans[r].iter().filter(|s| s.1 <= gutter).collect();
            Some((side.first()?.0, side.iter().map(|s| s.1).fold(f64::NEG_INFINITY, f64::max)))
        })
        .collect();
    if left.len() < 3 {
        return vec![glyphs];
    }
    let left_edge = left.iter().map(|s| s.1).fold(f64::NEG_INFINITY, f64::max);
    let near = left.iter().filter(|s| s.1 >= left_edge - size * 3.0).count();
    let mut widths: Vec<f64> = left.iter().map(|s| s.1 - s.0).collect();
    widths.sort_by(f64::total_cmp);
    let median_width = widths[widths.len() / 2];
    if (near as f64) < left.len() as f64 * 0.3 || median_width < size * 10.0 {
        return vec![glyphs];
    }

    // 段をまたぐ行で上下に区切り、区切りごとに左 → 右の順に並べる
    let spanning: Vec<bool> = (0..nrows).map(|r| crosses(r, gutter)).collect();
    let mut row_glyphs: Vec<Vec<RawGlyph>> = vec![Vec::new(); nrows];
    for (i, g) in glyphs.into_iter().enumerate() {
        row_glyphs[rows[i]].push(g);
    }
    let mut out: Vec<Vec<RawGlyph>> = Vec::new();
    let (mut left, mut right): (Vec<RawGlyph>, Vec<RawGlyph>) = (Vec::new(), Vec::new());
    let flush = |left: &mut Vec<RawGlyph>, right: &mut Vec<RawGlyph>, out: &mut Vec<Vec<RawGlyph>>| {
        for side in [std::mem::take(left), std::mem::take(right)] {
            if !side.is_empty() {
                out.extend(split_columns(side, depth + 1));
            }
        }
    };
    for (r, gs) in row_glyphs.into_iter().enumerate() {
        if spanning[r] {
            flush(&mut left, &mut right, &mut out);
            out.push(gs);
            continue;
        }
        for g in gs {
            if g.0 + advance(&g) / 2.0 < gutter { left.push(g) } else { right.push(g) }
        }
    }
    flush(&mut left, &mut right, &mut out);
    out
}

/// 文字を行（同じ高さに並んでいるもの）に分け、各文字の行番号（上から 0, 1, …）を返す。
fn assign_rows(glyphs: &[RawGlyph]) -> Vec<usize> {
    let mut idx: Vec<usize> = (0..glyphs.len()).collect();
    idx.sort_by(|&a, &b| glyphs[a].1.total_cmp(&glyphs[b].1).then(glyphs[a].0.total_cmp(&glyphs[b].0)));
    let mut rows = vec![0usize; glyphs.len()];
    let mut current: Option<(f64, f64, usize)> = None; // (行の先頭の y, 大きさ, 行番号)
    let mut next = 0;
    for i in idx {
        let g = &glyphs[i];
        match current {
            Some((y, s, n)) if (g.1 - y).abs() <= s.min(g.2).max(1.0) * 0.5 => rows[i] = n,
            _ => {
                rows[i] = next;
                current = Some((g.1, g.2, next));
                next += 1;
            }
        }
    }
    rows
}

#[cfg(test)]
pub(crate) fn group_into_lines(glyphs: Vec<(f64, f64, f64, String)>) -> Vec<String> {
    group_into_sized_lines(glyphs).into_iter().map(|(t, _)| t).collect()
}

/// 文字を行にまとめ、各行の文字の大きさ（最大値）も返す。
#[cfg_attr(not(feature = "pdf"), allow(dead_code))]
pub(crate) fn group_into_sized_lines(mut glyphs: Vec<RawGlyph>) -> Vec<(String, f64)> {
    glyphs.retain(|(_, _, s, _)| *s > 0.0);
    glyphs.sort_by(|a, b| a.1.total_cmp(&b.1).then(a.0.total_cmp(&b.0)));
    let mut rows: Vec<Vec<(f64, f64, f64, String)>> = Vec::new();
    for g in glyphs {
        match rows.last_mut() {
            Some(row) if (g.1 - row[0].1).abs() <= row[0].2.min(g.2).max(1.0) * 0.5 => row.push(g),
            _ => rows.push(vec![g]),
        }
    }
    let mut out = Vec::new();
    for mut row in rows {
        row.sort_by(|a, b| a.0.total_cmp(&b.0));
        let mut placed: Vec<(f64, String)> = Vec::new();
        let mut line = String::new();
        let mut line_size: f64 = 0.0;
        let mut prev: Option<(f64, f64, bool)> = None;
        for (x, _, size, text) in row {
            if placed.iter().rev().take(4).any(|(px, pt)| *pt == text && (x - px).abs() < size * 0.12) {
                continue;
            }
            if let Some((px, ps, wide)) = prev {
                let advance = ps * if wide { 1.0 } else { 0.6 };
                let gap = x - px - advance;
                if gap > size * 3.0 {
                    if !line.is_empty() {
                        out.push((std::mem::take(&mut line), line_size));
                        line_size = 0.0;
                    }
                } else if gap > size * 0.5 {
                    line.push(' ');
                }
            }
            let wide = text.chars().next().is_some_and(super::normalize::is_cjk);
            line.push_str(&text);
            if !text.trim().is_empty() {
                line_size = line_size.max(size);
            }
            placed.push((x, text));
            prev = Some((x, size, wide));
        }
        if !line.is_empty() {
            out.push((line, line_size));
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decodes_common_encodings() {
        let s = "システム：CoC7版\nPL人数：3～4人";
        assert_eq!(decode_text(s.as_bytes()).0, s);
        let mut bom = b"\xEF\xBB\xBF".to_vec();
        bom.extend_from_slice(s.as_bytes());
        assert_eq!(decode_text(&bom), (s.to_string(), "utf-8"));
        let (sj, _, _) = SHIFT_JIS.encode(s);
        assert_eq!(decode_text(&sj), (s.to_string(), "cp932"));
        let le: Vec<u8> = s.encode_utf16().flat_map(|u| u.to_le_bytes()).collect();
        assert_eq!(decode_text(&le), (s.to_string(), "utf-16le"));
        let mut le_bom = b"\xFF\xFE".to_vec();
        le_bom.extend_from_slice(&le);
        assert_eq!(decode_text(&le_bom).0, s);
        let be: Vec<u8> = s.encode_utf16().flat_map(|u| u.to_be_bytes()).collect();
        assert_eq!(decode_text(&be), (s.to_string(), "utf-16be"));
    }

    #[test]
    fn html_is_flattened_to_lines() {
        let html = r#"<html><head><style>p{color:red}</style><script>var a="<p>x</p>";</script></head>
            <body><h2>概要</h2><ul><li>システム&#xFF1A;CoC7版</li><li>PL人数&nbsp;:&nbsp;2&lt;3人&amp;GM</li></ul>
            <p>プレイ時間：約3時間<br>ロスト：低</p></body></html>"#;
        let lines: Vec<String> = html_to_text(html).lines().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).collect();
        assert_eq!(lines, ["概要", "システム：CoC7版", "PL人数 : 2<3人&GM", "プレイ時間：約3時間", "ロスト：低"]);
    }

    #[test]
    fn json_is_flattened_to_label_lines() {
        let json = r#"{"title":"夜の図書館","system":"CoC7","min_players":2,"max_players":4,
            "meta":{"playtime":"約3時間","lost":"低","skills":["目星","図書館"]}}"#;
        let lines = JsonExtractor.extract(json.as_bytes()).unwrap();
        for want in ["players: 2〜4", "system: CoC7", "playtime: 約3時間", "lost: 低", "skills: 目星、図書館"] {
            assert!(lines.iter().any(|l| l == want), "{want} not in {lines:?}");
        }
        assert!(JsonExtractor.extract(b"{broken").is_err());
        let deep = format!("{}{}", "[".repeat(10_000), "]".repeat(10_000));
        assert!(JsonExtractor.extract(deep.as_bytes()).is_err());
    }

    #[test]
    fn html_with_broken_tags_does_not_panic() {
        for s in ["<", "<<<>", "<p", "&", "&#xFFFFFFFF;", "&#99999999999;", "<script>never closed", "</>"] {
            let _ = html_to_text(s);
        }
    }

    /// 2段組みのページ（左に仕様、右にあらすじ）を、段ごとに読む。
    fn two_column_page() -> Vec<RawGlyph> {
        let mut gs = Vec::new();
        // 実際の PDF と同じく、文字の送り幅は大きさより少し狭い（8.4pt / 9pt）
        let mut put = |x0: f64, y: f64, text: &str| {
            for (k, c) in text.chars().enumerate() {
                gs.push((x0 + k as f64 * 8.4, y, 9.0, c.to_string()));
            }
        };
        put(229.0, 71.0, "▼概要");
        put(229.0, 86.0, "学園の裏山に流れ星が落ちたのを見た。");
        put(51.0, 117.0, "♢推奨人数：２人");
        put(229.0, 102.0, "居ても立っても居られなくなり、家を飛び出");
        put(229.0, 117.0, "す。");
        put(51.0, 148.0, "♢推奨技能：目星、心理学、信用、");
        put(229.0, 148.0, "きっとあの流星は、この退屈な日常を打ち砕");
        put(51.0, 164.0, "対人関係技能");
        put(229.0, 164.0, "いてくれるって。");
        put(51.0, 179.0, "（威圧、言いくるめ、説得もしくは魅惑）");
        put(229.0, 179.0, "どうしようもない衝動のまま、裏山の天辺目");
        put(51.0, 195.0, "♢準推奨技能：自然、サバイバル");
        put(229.0, 195.0, "掛けて一目散だ。");
        put(51.0, 272.0, "探索者たちは高校二年生、学生である。");
        put(51.0, 287.0, "学校の名称は好きに決めてよい。ここでの記");
        put(229.0, 287.0, "が裏山に落ちた日。");
        gs
    }

    #[test]
    fn two_columns_are_read_column_by_column() {
        let lines: Vec<String> =
            split_columns(two_column_page(), 0).into_iter().flat_map(group_into_sized_lines).map(|(t, _)| t).collect();
        assert_eq!(
            lines,
            [
                "♢推奨人数：２人",
                "♢推奨技能：目星、心理学、信用、",
                "対人関係技能",
                "（威圧、言いくるめ、説得もしくは魅惑）",
                "♢準推奨技能：自然、サバイバル",
                "探索者たちは高校二年生、学生である。",
                "学校の名称は好きに決めてよい。ここでの記",
                "▼概要",
                "学園の裏山に流れ星が落ちたのを見た。",
                "居ても立っても居られなくなり、家を飛び出",
                "す。",
                "きっとあの流星は、この退屈な日常を打ち砕",
                "いてくれるって。",
                "どうしようもない衝動のまま、裏山の天辺目",
                "掛けて一目散だ。",
                "が裏山に落ちた日。",
            ]
        );
    }

    #[test]
    fn tables_and_single_column_pages_are_not_split() {
        // 表: 左のセルが短い見出し、右のセルが値
        let mut gs = Vec::new();
        let mut put = |x0: f64, y: f64, text: &str| {
            for (k, c) in text.chars().enumerate() {
                gs.push((x0 + k as f64 * 10.0, y, 10.0, c.to_string()));
            }
        };
        for (n, (k, v)) in [("PL人数", "1人（タイマン）"), ("想定時間", "約3時間"), ("ロスト率", "中"), ("ジャンル", "ホラー"), ("形式", "ボイス"), ("推奨技能", "目星、聞き耳"), ("舞台", "現代日本")]
            .iter()
            .enumerate()
        {
            put(50.0, 100.0 + n as f64 * 16.0, k);
            put(250.0, 100.0 + n as f64 * 16.0, v);
        }
        assert_eq!(split_columns(gs.clone(), 0).len(), 1);
        // 1段組みの文章
        let mut gs = Vec::new();
        for r in 0..10 {
            for k in 0..40 {
                gs.push((50.0 + k as f64 * 10.0, 100.0 + r as f64 * 16.0, 10.0, "あ".to_string()));
            }
        }
        assert_eq!(split_columns(gs, 0).len(), 1);
    }

    #[test]
    fn glyphs_are_grouped_into_lines() {
        let g = |x: f64, y: f64, t: &str| (x, y, 10.0, t.to_string());
        let lines = group_into_lines(vec![g(22.0, 100.4, "数"), g(12.0, 100.0, "人"), g(0.0, 100.0, "P"), g(6.0, 99.8, "L"), g(0.0, 120.0, "2")]);
        assert_eq!(lines, ["PL人数", "2"]);
        let lines = group_into_lines(vec![g(0.0, 0.0, "作"), g(0.5, 0.0, "作"), g(10.0, 0.0, "家"), g(10.5, 0.0, "家")]);
        assert_eq!(lines, ["作家"]);
        let lines = group_into_lines(vec![g(0.0, 0.0, "左"), g(10.0, 0.0, "段"), g(200.0, 0.0, "右"), g(210.0, 0.0, "段")]);
        assert_eq!(lines, ["左段", "右段"]);
    }
}