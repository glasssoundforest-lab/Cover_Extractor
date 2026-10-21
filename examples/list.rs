//! ソース内のエントリ一覧と、表紙候補の点数・内訳を表示するCLI（判定ルールの調整用）。
//!
//! ```text
//! cargo run --release --example list -- <フォルダ or ZIP> [--rules <rules.toml>] [--all]
//! ```
//! - 点数はパスだけで付けた「楽観値」。実際の抽出では、上位から読んで縦横比やインク率で減点される。
//! - `--all` を付けると、候補にならないファイルも含めた全エントリを表示する。

use cover_extractor::{CandidateKind, CandidateRanker, ScoringRanker, open_source};

fn main() {
    let mut args = std::env::args().skip(1);
    let (mut path, mut rules, mut all) = (None, None, false);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--rules" => rules = args.next(),
            "--all" => all = true,
            _ => path = Some(a),
        }
    }
    let Some(path) = path else {
        eprintln!("usage: list <folder-or-zip> [--rules <rules.toml>] [--all]");
        std::process::exit(2);
    };
    let ranker = match &rules {
        Some(r) => ScoringRanker::from_file(r.as_ref()).expect("cannot load rules"),
        None => ScoringRanker::default(),
    };

    let source = open_source(path.as_ref()).expect("cannot open source");
    let entries = source.entries();
    if all {
        println!("-- entries ({}):", entries.len());
        for e in entries {
            println!("{:>10}  {}", e.size, e.path);
        }
        println!();
    }

    let mut cands = ranker.candidates(entries);
    cands.sort_by(|a, b| b.score.cmp(&a.score).then(a.index.cmp(&b.index)));
    println!("-- candidates (min_score {}):", ranker.min_score());
    for c in &cands {
        let mark = if c.score < ranker.min_score() {
            "x"
        } else {
            " "
        };
        let kind = match c.kind {
            CandidateKind::Image => "img",
            CandidateKind::PdfFirstPage => "pdf",
        };
        println!("{mark}{:>5}  {kind}  {}", c.score, entries[c.index].path);
        println!("          {}", c.reasons.join(", "));
    }
}
