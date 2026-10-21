//! シナリオ情報（題名・システム・人数・時間・概要・あらすじなど）を取り出して表示するCLI。
//!
//! ```text
//! cargo run --release --example info -- <フォルダ / ZIP / PDF>... [--rules <info_rules.toml>] [--json] [--summary] [--dump]
//! ```
//! - 既定では結果の JSON（`ce_extract_info` が返すものと同じ形）を整形して表示する。
//! - `--json`    : 1件につき1行の JSON で出力する（main.py から呼ぶ形）。読めなかった場合は `{}` を出力する。
//! - `--summary` : 項目ごとに1行の要約を表示する（ルールの調整用）。
//! - `--dump`    : 読んだ文書と、そこから取り出した行（PDF はページと文字の大きさ付き）を標準エラーに表示する。
//!                 項目が取れないときに、文書がどう読めているかを確かめるために使う。
//! - パスの代わりに URL（`https://booth.pm/ja/items/...` など）を指定すると、そのページから取り出す。

use std::path::PathBuf;
use std::process::ExitCode;

use cover_extractor::{InfoExtractor, ScenarioInfo, ThumbnailConfig, WebExtractor};
use cover_extractor::info::InfoValue;

fn main() -> ExitCode {
    let mut args = std::env::args_os().skip(1);
    let (mut paths, mut rules): (Vec<PathBuf>, Option<PathBuf>) = (vec![], None);
    let (mut json, mut summary, mut dump) = (false, false, false);
    while let Some(a) = args.next() {
        match a.to_str() {
            Some("--rules") => rules = args.next().map(PathBuf::from),
            Some("--json") => json = true,
            Some("--summary") => summary = true,
            Some("--dump") => dump = true,
            _ => paths.push(PathBuf::from(a)),
        }
    }
    if paths.is_empty() {
        eprintln!("usage: info <folder | zip | pdf>... [--rules <info_rules.toml>] [--json] [--summary] [--dump]");
        return ExitCode::from(2);
    }
    let extractor = match &rules {
        Some(r) => match InfoExtractor::from_rules_file(r) {
            Ok(ex) => ex,
            Err(e) => {
                eprintln!("cannot load rules: {e}");
                return ExitCode::from(2);
            }
        },
        None => InfoExtractor::new(),
    };

    let mut failed = false;
    for path in &paths {
        let as_str = path.to_string_lossy();
        if as_str.starts_with("http://") || as_str.starts_with("https://") {
            match WebExtractor::new().extract(&as_str, &extractor, &ThumbnailConfig::default()) {
                Ok(web) => {
                    for w in &web.warnings {
                        eprintln!("warning: {w}");
                    }
                    eprintln!("site: {} / image: {:?} / tags: {:?}", web.site, web.image_url, web.tags);
                    if summary {
                        print_summary(path, &web.info, 0);
                    } else if json {
                        println!("{}", serde_json::to_string(&web.info).unwrap_or_else(|_| "{}".into()));
                    } else {
                        println!("{}", serde_json::to_string_pretty(&web.info).unwrap_or_default());
                    }
                }
                Err(e) => {
                    eprintln!("{as_str}: {e}");
                    failed = true;
                }
            }
            continue;
        }
        if dump {
            dump_documents(&extractor, path);
        }
        let started = std::time::Instant::now();
        let info = match extractor.extract(path) {
            Ok(info) => info,
            Err(e) => {
                eprintln!("{}: {e}", path.display());
                if json {
                    println!("{{}}");
                }
                failed = true;
                continue;
            }
        };
        if json {
            println!("{}", serde_json::to_string(&info).unwrap_or_else(|_| "{}".into()));
        } else if summary {
            print_summary(path, &info, started.elapsed().as_millis());
        } else {
            println!("{}", serde_json::to_string_pretty(&info).unwrap_or_default());
        }
    }
    if failed { ExitCode::FAILURE } else { ExitCode::SUCCESS }
}

fn print_summary(path: &std::path::Path, info: &ScenarioInfo, ms: u128) {
    println!("== {} ({ms} ms)", path.display());
    fn show<T>(name: &str, v: &Option<InfoValue<T>>, fmt: impl Fn(&T) -> String) {
        match v {
            Some(f) => {
                let raw = f.raw_text.replace('\n', " / ");
                let raw: String = raw.chars().take(60).collect();
                println!("  {name:<9} {}  \"{raw}\" <- {}", fmt(&f.value), f.source_path);
            }
            None => println!("  {name:<9} -"),
        }
    }
    let one_line = |s: &String| {
        let s = s.replace('\n', " / ");
        let n = s.chars().count();
        if n > 60 { format!("{}…({n}字)", s.chars().take(60).collect::<String>()) } else { s }
    };
    show("title", &info.title, one_line);
    show("system", &info.system, |s| s.clone());
    show("players", &info.players, |p| format!("{}〜{}", p.min, p.max));
    show("duration", &info.duration, |d| format!("{}〜{}h", d.min_hours, d.max_hours));
    show("genre", &info.genre, |s| s.clone());
    show("lost", &info.lost, |s| s.clone());
    show("format", &info.format, |s| s.clone());
    show("skills", &info.skills, |s| s.join("、"));
    show("overview", &info.overview, one_line);
    show("synopsis", &info.synopsis, one_line);
}

fn dump_documents(extractor: &InfoExtractor, path: &std::path::Path) {
    match extractor.document_lines(path) {
        Ok(docs) => {
            if docs.is_empty() {
                eprintln!("(読む文書がありません。PDF を読むには `pdf` feature を有効にしてビルドしてください)");
            }
            for (doc, text) in docs {
                eprintln!("==== {doc}");
                match text {
                    Ok(t) => {
                        for l in t.lines.iter().take(200) {
                            if t.is_pdf {
                                eprintln!("p{:<2} {:>5.1} | {}", l.page + 1, l.size, l.text);
                            } else {
                                eprintln!("{}", l.text);
                            }
                        }
                    }
                    Err(e) => eprintln!("(読めませんでした: {e})"),
                }
            }
        }
        Err(e) => eprintln!("{}: cannot open: {e}", path.display()),
    }
}
