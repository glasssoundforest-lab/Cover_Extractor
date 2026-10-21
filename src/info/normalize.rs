//! 解析前のテキストの正規化。

use unicode_normalization::UnicodeNormalization;

/// 1行を正規化する。
pub fn normalize_line(s: &str) -> String {
    let nfkc: String = s.nfkc().collect();
    let mapped: String = nfkc
        .chars()
        .map(|c| match c {
            '~' | '∼' | '〜' | '〰' | '⁓' => '〜',
            '−' | '‐' | '‑' | '‒' | '–' | '—' | '―' => '-',
            '【' | '〔' | '［' | '〖' => '[',
            '】' | '〕' | '］' | '〗' => ']',
            '∶' | '꞉' | '˸' => ':',
            '\u{3000}' | '\t' | '\u{a0}' => ' ',
            c if c.is_control() => ' ',
            c => c,
        })
        .collect();
    squeeze_spaces(&mapped)
}

/// 表示用の整形（あらすじなど、文章として見せる部分に使う）。
///
/// `normalize_line` と違い、全角の句読点や括弧はそのまま残す。
/// PDF 特有の文字（康熙部首の「⼈」、縦書き用の「︓」、互換漢字など）だけを通常の文字に直し、
/// 文字の間に入った余計な空白を取り除く。
pub fn clean_display(s: &str) -> String {
    squeeze_spaces(fix_pdf_chars(s).trim())
}

/// PDF 特有の文字（「⼈」「︓」など）だけを通常の文字に直す。空白はそのまま残す（題名など、語の間の空白が意味を持つもの用）。
pub fn fix_pdf_chars(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        let cp = c as u32;
        let pdf_artifact = matches!(cp,
            0x2E80..=0x2FDF      // CJK 部首補助・康熙部首（「⼈」「⽇」など）
            | 0xF900..=0xFAFF    // CJK 互換漢字
            | 0xFE10..=0xFE1F    // 縦書き用の句読点（「︓」「︒」など）
            | 0xFE30..=0xFE4F    // CJK 互換形
        );
        if pdf_artifact {
            out.extend(c.to_string().nfkc());
        } else if c == '\u{3000}' || c == '\t' || c == '\u{a0}' || c.is_control() {
            out.push(' ');
        } else {
            out.push(c);
        }
    }
    out
}

/// 連続する空白を1つにし、日本語に隣接する空白は取り除く。
fn squeeze_spaces(s: &str) -> String {
    let chars: Vec<char> = s.chars().collect();
    let mut out = String::with_capacity(s.len());
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c == ' ' {
            let mut j = i;
            while j < chars.len() && chars[j] == ' ' {
                j += 1;
            }
            let prev = out.chars().last();
            let next = chars.get(j).copied();
            let keep = match (prev, next) {
                (None, _) | (_, None) => false,
                (Some(p), Some(n)) => !(is_cjk(p) || is_cjk(n)),
            };
            if keep {
                out.push(' ');
            }
            i = j;
        } else {
            out.push(c);
            i += 1;
        }
    }
    out
}

/// 日本語（漢字・かな・全角記号）かどうか。
pub fn is_cjk(c: char) -> bool {
    matches!(c as u32,
        0x3000..=0x30FF
        | 0x3400..=0x4DBF
        | 0x4E00..=0x9FFF
        | 0xF900..=0xFAFF
        | 0xFF01..=0xFF60
        | 0xFF61..=0xFF9F
        | 0x20000..=0x2FFFF
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pdf_artifacts_are_normalized() {
        assert_eq!(normalize_line("プレイ⼈数︓PL７名+GM１⼈"), "プレイ人数:PL7名+GM1人");
        assert_eq!(normalize_line("プレイ時間︓４〜５時間を想定しています"), "プレイ時間:4〜5時間を想定しています");
        assert_eq!(normalize_line("PL 人数：2 人(タイマン改変可)"), "PL人数:2人(タイマン改変可)");
        assert_eq!(normalize_line("システム：CoC6 版"), "システム:CoC6版");
        assert_eq!(normalize_line("所要時間：8 ～ 12 時間"), "所要時間:8〜12時間");
    }

    #[test]
    fn english_spacing_is_kept() {
        assert_eq!(normalize_line("System:  Call of   Cthulhu 7th"), "System: Call of Cthulhu 7th");
        assert_eq!(normalize_line(" 【 推奨技能 】 "), "[推奨技能]");
    }
}