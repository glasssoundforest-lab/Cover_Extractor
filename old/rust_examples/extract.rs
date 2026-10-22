//! 表紙抽出を試すCLI。
//!
//! ```text
//! cargo run --release --example extract -- <フォルダ or ZIP>... [--out <出力フォルダ>] [--rules <rules.toml>] [--more <件数>]
//! ```
//!
//! 各ソースについて、採用した候補と点数の内訳・判定の確かさ・選択肢・処理時間を表示する。
//! - `--more N`: 選択肢に正解がなかった場合の「その他の候補」を N 件表示する
//! - `--out`: サムネイルを保存する（`<名前>.jpg`、選択肢は `<名前>.choice1.jpg`…、その他は `<名前>.more1.jpg`…）

use std::path::{Path, PathBuf};
use std::time::Instant;

use cover_extractor::{
    Choice, Confidence, CoverExtractor, CoverOrigin, ExtractorConfig, ScoringRanker,
};

fn main() {
    let mut inputs = Vec::new();
    let (mut out_dir, mut rules, mut more): (Option<PathBuf>, Option<PathBuf>, usize) =
        (None, None, 0);
    let mut args = std::env::args_os().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--out" {
            out_dir = args.next().map(PathBuf::from);
        } else if arg == "--rules" {
            rules = args.next().map(PathBuf::from);
        } else if arg == "--more" {
            more = args
                .next()
                .and_then(|n| n.to_str()?.parse().ok())
                .unwrap_or(4);
        } else {
            inputs.push(PathBuf::from(arg));
        }
    }
    if inputs.is_empty() {
        eprintln!(
            "usage: extract <folder-or-zip>... [--out <dir>] [--rules <rules.toml>] [--more <n>]"
        );
        std::process::exit(2);
    }
    if let Some(dir) = &out_dir {
        std::fs::create_dir_all(dir).expect("cannot create output folder");
    }

    let ranker = match &rules {
        Some(r) => ScoringRanker::from_file(r).expect("cannot load rules"),
        None => ScoringRanker::default(),
    };
    let extractor = CoverExtractor::with_ranker(ExtractorConfig::default(), Box::new(ranker));

    for input in &inputs {
        let started = Instant::now();
        let cover = extractor.extract(input);
        let elapsed = started.elapsed();

        println!("== {}", input.display());
        match &cover.origin {
            CoverOrigin::Extracted {
                entry_path,
                kind,
                source_width,
                source_height,
                score,
                reasons,
            } => {
                println!("   cover : {entry_path} [{kind:?}] ({source_width}x{source_height})");
                println!("   score : {score}  ({})", reasons.join(", "));
            }
            CoverOrigin::Placeholder { reason } => println!("   cover : <placeholder> {reason:?}"),
        }
        match &cover.confidence {
            Confidence::Ambiguous { reason } => {
                println!("   judge : 迷っている（{reason}）→ 選択肢から選んでください")
            }
            other => println!("   judge : {other:?}"),
        }
        print_choices("choice", &cover.choices);
        for a in &cover.failed_attempts {
            println!("   skip  : {} -- {}", a.entry_path, a.error);
        }
        println!(
            "   thumb : {}x{}, {} bytes, {:.1} ms",
            cover.width,
            cover.height,
            cover.jpeg.len(),
            elapsed.as_secs_f64() * 1000.0
        );

        let mut more_list = Vec::new();
        if more > 0 {
            // すでに見せたもの（採用した候補と選択肢）を除いて、続きを出す
            let mut shown: Vec<String> =
                cover.choices.iter().map(|c| c.entry_path.clone()).collect();
            shown.extend(cover.entry_path().map(str::to_string));
            let started = Instant::now();
            more_list = extractor
                .more_candidates(input, &shown, more)
                .unwrap_or_default();
            println!(
                "   -- その他の候補（{:.0} ms）",
                started.elapsed().as_secs_f64() * 1000.0
            );
            print_choices("more", &more_list);
        }

        if let Some(dir) = &out_dir {
            let stem = file_stem(input);
            save(dir, &format!("{stem}.jpg"), &cover.jpeg);
            for (i, c) in cover.choices.iter().enumerate() {
                save(dir, &format!("{stem}.choice{}.jpg", i + 1), &c.jpeg);
            }
            for (i, c) in more_list.iter().enumerate() {
                save(dir, &format!("{stem}.more{}.jpg", i + 1), &c.jpeg);
            }
        }
    }
}

fn print_choices(label: &str, choices: &[Choice]) {
    for (i, c) in choices.iter().enumerate() {
        println!(
            "   {label} {}: {:>4}  {}  ({})",
            i + 1,
            c.score,
            c.entry_path,
            c.reasons.join(", ")
        );
    }
}

/// "シナリオ v1.2.zip" のような名前でも末尾の ".2" を消さないよう、最後の拡張子だけ外す。
fn file_stem(p: &Path) -> String {
    p.file_stem()
        .map(|s| s.to_string_lossy().to_string())
        .unwrap_or_else(|| "cover".into())
}

fn save(dir: &Path, name: &str, data: &[u8]) {
    let path = dir.join(name);
    std::fs::write(&path, data).expect("cannot write thumbnail");
}
