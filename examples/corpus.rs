//! 手持ちのシナリオ一式で判定精度を測るCLI（Phase 2 の精度検証用）。
//!
//! ```text
//! cargo run --release --example corpus -- <コーパスフォルダ> [--rules <rules.toml>] [--out <出力フォルダ>]
//! ```
//!
//! コーパスフォルダには、シナリオの ZIP / フォルダと、正解を書いた `expected.toml` を置く。
//!
//! ```toml
//! # キー: ZIP / フォルダの名前、値: 表紙として採用されるべきエントリのパス（list の表示と同じ形）
//! "onazisora_ver1_2.zip" = "onazisora_ver1_2/trailer/onasora1102_a.png"
//! "忘却レストラン.zip" = "忘却レストラン/02_ゲームマスター/GMガイド.pdf"
//! # 表紙がない（プレースホルダーが正しい）場合は空文字
//! "素材集.zip" = ""
//! ```
//!
//! `expected.toml` に載っていないものは「未判定」として結果だけ表示する。
//!
//! 結果の印: `OK` 正解 / `CHOICE` 1位ではないが選択肢の中にある / `NG` 不正解 / `--` 正解未登録。
//! `?` は「迷っている」（選択肢を出してユーザーに選んでもらう）判定。

use std::collections::BTreeMap;
use std::path::PathBuf;
use std::time::Instant;

use cover_extractor::{CoverExtractor, ExtractorConfig, ScoringRanker};

fn main() {
    let mut args = std::env::args_os().skip(1);
    let (mut dir, mut rules, mut out): (Option<PathBuf>, Option<PathBuf>, Option<PathBuf>) =
        (None, None, None);
    while let Some(a) = args.next() {
        if a == "--rules" {
            rules = args.next().map(PathBuf::from);
        } else if a == "--out" {
            out = args.next().map(PathBuf::from);
        } else {
            dir = Some(PathBuf::from(a));
        }
    }
    let Some(dir) = dir else {
        eprintln!("usage: corpus <dir> [--rules <rules.toml>] [--out <dir>]");
        std::process::exit(2);
    };

    let expected: BTreeMap<String, String> = std::fs::read_to_string(dir.join("expected.toml"))
        .map(|t| toml::from_str(&t).expect("invalid expected.toml"))
        .unwrap_or_default();
    let ranker = match &rules {
        Some(r) => ScoringRanker::from_file(r).expect("cannot load rules"),
        None => ScoringRanker::default(),
    };
    let extractor = CoverExtractor::with_ranker(ExtractorConfig::default(), Box::new(ranker));
    if let Some(o) = &out {
        std::fs::create_dir_all(o).expect("cannot create output folder");
    }

    let mut items: Vec<_> = std::fs::read_dir(&dir)
        .expect("cannot read corpus folder")
        .filter_map(Result::ok)
        .map(|e| e.path())
        .filter(|p| p.is_dir() || p.extension().is_some_and(|e| e.eq_ignore_ascii_case("zip")))
        .collect();
    items.sort();

    let (mut ok, mut ng, mut unknown, mut in_choices, mut reviews) = (0, 0, 0, 0, 0);
    for path in &items {
        let name = path.file_name().unwrap().to_string_lossy().to_string();
        let started = Instant::now();
        let cover = extractor.extract(path);
        let ms = started.elapsed().as_secs_f64() * 1000.0;
        let got = cover.entry_path().unwrap_or("").to_string();
        let review = if cover.needs_review() { "?" } else { " " };

        let verdict = match expected.get(&name) {
            Some(want) if *want == got => {
                ok += 1;
                "OK".to_string()
            }
            Some(want) if cover.choices.iter().any(|c| c.entry_path == *want) => {
                in_choices += 1;
                format!(
                    "CHOICE (expected is choice #{})",
                    cover
                        .choices
                        .iter()
                        .position(|c| c.entry_path == *want)
                        .unwrap()
                        + 1
                )
            }
            Some(want) => {
                ng += 1;
                format!(
                    "NG (expected: {})",
                    if want.is_empty() {
                        "<placeholder>"
                    } else {
                        want
                    }
                )
            }
            None => {
                unknown += 1;
                "--".to_string()
            }
        };
        let shown = if got.is_empty() {
            "<placeholder>"
        } else {
            &got
        };
        reviews += usize::from(cover.needs_review());
        println!("{verdict:<4} {review} {name}  ->  {shown}  ({ms:.0} ms)");
        for (i, c) in cover.choices.iter().enumerate() {
            println!(
                "         choice {}: {:>4}  {}",
                i + 1,
                c.score,
                c.entry_path
            );
        }
        if let Some(o) = &out {
            std::fs::write(o.join(format!("{name}.jpg")), &cover.jpeg)
                .expect("cannot write thumbnail");
        }
    }
    let judged = ok + ng + in_choices;
    println!(
        "\n{ok}/{judged} correct ({:.0}%), {in_choices} found in choices, {reviews} asked for review, {unknown} without expectation",
        if judged > 0 {
            ok as f64 * 100.0 / judged as f64
        } else {
            0.0
        }
    );
    if ng > 0 {
        std::process::exit(1);
    }
}
