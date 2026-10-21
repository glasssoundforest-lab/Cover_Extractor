//! 表紙候補の列挙と点数付け。

use std::collections::HashMap;

use sha2::{Digest, Sha256};

use crate::names::{depth, extension, file_name, is_image_path};
use crate::rules::{ChoiceSettings, PathTerms, Rules, Scope, Target};
use crate::source::Entry;
use unicode_normalization::UnicodeNormalization;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CandidateKind {
    Image,
    PdfFirstPage,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Candidate {
    pub index: usize,
    pub kind: CandidateKind,
    pub score: i32,
    pub reasons: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Evidence {
    pub width: u32,
    pub height: u32,
    pub dominant_ratio: f32,
}

pub trait CandidateRanker: Send + Sync {
    fn candidates(&self, entries: &[Entry]) -> Vec<Candidate>;

    fn adjust(&self, _candidate: &Candidate, _evidence: &Evidence) -> Vec<(i32, String)> {
        Vec::new()
    }

    fn min_score(&self) -> i32 {
        i32::MIN
    }

    fn choice_settings(&self) -> ChoiceSettings {
        ChoiceSettings::default()
    }

    fn version(&self) -> String;
}

#[derive(Debug, Clone)]
pub struct ScoringRanker {
    rules: Rules,
    version: String,
}

impl Default for ScoringRanker {
    fn default() -> Self {
        Self::from_toml(crate::rules::DEFAULT_RULES_TOML)
            .expect("built-in rules.toml must be valid")
    }
}

impl ScoringRanker {
    pub fn from_toml(text: &str) -> Result<Self, toml::de::Error> {
        let rules = Rules::from_toml(text)?;
        let digest = Sha256::digest(text.as_bytes());
        let short: String = digest.iter().take(6).map(|b| format!("{b:02x}")).collect();
        let version = format!("scoring/{}/{short}", rules.version);
        Ok(Self { rules, version })
    }

    pub fn from_file(
        path: &std::path::Path,
    ) -> Result<Self, Box<dyn std::error::Error + Send + Sync>> {
        use crate::limits::{read_limited, MAX_RULES_FILE_BYTES};
        let meta = std::fs::metadata(path)?;
        if !meta.is_file() {
            return Err(format!("rules file is not a regular file: {}", path.display()).into());
        }
        let bytes = read_limited(std::fs::File::open(path)?, MAX_RULES_FILE_BYTES, meta.len())?
            .map_err(|_| format!("rules file is larger than {MAX_RULES_FILE_BYTES} bytes"))?;
        Ok(Self::from_toml(std::str::from_utf8(&bytes)?)?)
    }

    pub fn rules(&self) -> &Rules {
        &self.rules
    }

    fn keyword_score(
        &self,
        terms: &PathTerms,
        target: Target,
        saturated: &[usize],
        reasons: &mut Vec<String>,
    ) -> Option<i32> {
        let mut name: Vec<(i32, String, bool)> = Vec::new();
        let mut dirs: Vec<(i32, String, bool)> = Vec::new();
        for (gi, g) in self.rules.groups.iter().enumerate() {
            if !g.applies_to(target) {
                continue;
            }
            if let Some(w) = g.words.iter().find(|w| terms.matches_name(w)) {
                if saturated.contains(&gi) {
                    reasons.push(format!("+0 {}({w}) ignored: too many in folder", g.name));
                } else {
                    name.push((g.score, format!("{}({w})", g.name), g.exclude));
                }
            } else if g.scope == Scope::Path {
                if let Some(w) = g.words.iter().find(|w| terms.matches_dirs(w)) {
                    dirs.push((g.score, format!("{}({w}/)", g.name), g.exclude));
                }
            }
        }

        let hits = if name.is_empty() { dirs } else { name };
        if let Some((_, label, _)) = hits.iter().find(|(_, _, ex)| *ex) {
            reasons.push(format!("excluded {label}"));
            return None;
        }
        let pos = hits
            .iter()
            .filter(|(s, ..)| *s >= 0)
            .max_by_key(|(s, ..)| *s);
        let neg = hits
            .iter()
            .filter(|(s, ..)| *s < 0)
            .min_by_key(|(s, ..)| *s);
        let mut total: i32 = 0;
        for (s, label, _) in pos.into_iter().chain(neg) {
            reasons.push(format!("{s:+} {label}"));
            total = total.saturating_add(*s);
        }
        Some(total)
    }

    fn saturated_groups(&self, entries: &[Entry]) -> Vec<(usize, String)> {
        let mut counts: HashMap<(usize, String), usize> = HashMap::new();
        for e in entries {
            let target = match candidate_kind(&e.path) {
                Some(CandidateKind::Image) => Target::Image,
                Some(CandidateKind::PdfFirstPage) => Target::Pdf,
                None => continue,
            };
            let terms = PathTerms::new(&e.path);
            for (gi, g) in self.rules.groups.iter().enumerate() {
                if g.max_per_dir.is_some()
                    && g.applies_to(target)
                    && g.words.iter().any(|w| terms.matches_name(w))
                {
                    *counts
                        .entry((gi, parent_dir(&e.path).to_string()))
                        .or_default() += 1;
                }
            }
        }
        counts
            .into_iter()
            .filter(|((gi, _), n)| {
                self.rules.groups[*gi]
                    .max_per_dir
                    .is_some_and(|max| *n > max)
            })
            .map(|(k, _)| k)
            .collect()
    }
}

fn candidate_kind(path: &str) -> Option<CandidateKind> {
    if is_image_path(path) {
        Some(CandidateKind::Image)
    } else if extension(path).as_deref() == Some("pdf") {
        Some(CandidateKind::PdfFirstPage)
    } else {
        None
    }
}

fn parent_dir(path: &str) -> &str {
    path.rsplit_once('/').map(|(d, _)| d).unwrap_or("")
}

impl CandidateRanker for ScoringRanker {
    fn candidates(&self, entries: &[Entry]) -> Vec<Candidate> {
        let strip = common_root_depth(entries);
        let seq = sequence_positions(entries);
        let adj = &self.rules.adjust;

        let saturated = self.saturated_groups(entries);

        let mut out = Vec::new();
        for e in entries {
            let (kind, target, base) = match candidate_kind(&e.path) {
                Some(k @ CandidateKind::Image) => (k, Target::Image, self.rules.base.image),
                Some(k @ CandidateKind::PdfFirstPage) => {
                    (k, Target::Pdf, self.rules.base.pdf_first_page)
                }
                None => continue,
            };

            let dir = parent_dir(&e.path);
            let sat: Vec<usize> = saturated
                .iter()
                .filter(|(_, d)| d == dir)
                .map(|(gi, _)| *gi)
                .collect();
            let mut reasons = vec![format!("{base:+} base")];
            let mut score = base;
            let Some(kw) = self.keyword_score(&PathTerms::new(&e.path), target, &sat, &mut reasons)
            else {
                continue;
            };
            score = score.saturating_add(kw);

            let d = depth(&e.path).saturating_sub(strip).min(i32::MAX as usize) as i32;
            if d > 0 {
                let p = d.saturating_mul(adj.per_depth);
                score = score.saturating_sub(p);
                reasons.push(format!("{:+} depth {d}", -p));
            }
            if kind == CandidateKind::Image {
                match seq.get(&e.index) {
                    Some(0) => {
                        score = score.saturating_add(adj.sequence_first_bonus);
                        reasons.push(format!("{:+} sequence first", adj.sequence_first_bonus));
                    }
                    Some(&n) => {
                        let p = adj.sequence_later_penalty.saturating_mul(n.min(4) as i32);
                        score = score.saturating_sub(p);
                        reasons.push(format!("{:+} sequence #{}", -p, n + 1));
                    }
                    None => {}
                }
            }
            out.push(Candidate {
                index: e.index,
                kind,
                score,
                reasons,
            });
        }
        out
    }

    fn adjust(&self, _candidate: &Candidate, ev: &Evidence) -> Vec<(i32, String)> {
        let adj = &self.rules.adjust;
        let mut out = Vec::new();
        let (long, short) = (ev.width.max(ev.height), ev.width.min(ev.height).max(1));
        let ratio = long as f32 / short as f32;
        if ratio > adj.extreme_aspect_ratio {
            out.push((
                adj.extreme_aspect_penalty.saturating_neg(),
                format!("aspect {ratio:.2}"),
            ));
        }
        if ev.dominant_ratio >= adj.plain_dominant_ratio {
            out.push((
                adj.plain_page_penalty.saturating_neg(),
                format!("plain page (one color {:.0}%)", ev.dominant_ratio * 100.0),
            ));
        }
        out
    }

    fn min_score(&self) -> i32 {
        self.rules.min_score
    }

    fn choice_settings(&self) -> ChoiceSettings {
        self.rules.choices.clone()
    }

    fn version(&self) -> String {
        self.version.clone()
    }
}

fn sequence_positions(entries: &[Entry]) -> HashMap<usize, usize> {
    let mut groups: HashMap<(String, String), Vec<(SeqKey, usize)>> = HashMap::new();
    for e in entries.iter().filter(|e| is_image_path(&e.path)) {
        let dir = e
            .path
            .rsplit_once('/')
            .map(|(d, _)| d)
            .unwrap_or("")
            .to_string();
        let name = file_name(&e.path);
        let stem = name.rsplit_once('.').map(|(s, _)| s).unwrap_or(name);
        let stem: String = stem.nfkc().collect();
        if let Some((prefix, key)) = split_sequence(&stem) {
            groups
                .entry((dir, prefix.to_lowercase()))
                .or_default()
                .push((key, e.index));
        }
    }
    let mut out = HashMap::new();
    for mut members in groups.into_values().filter(|m| m.len() >= 2) {
        members.sort();
        for (pos, (_, index)) in members.into_iter().enumerate() {
            out.insert(index, pos);
        }
    }
    out
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
enum SeqKey {
    Number(u32),
    Letter(char),
}

fn split_sequence(stem: &str) -> Option<(&str, SeqKey)> {
    let digits = stem
        .chars()
        .rev()
        .take_while(|c| c.is_ascii_digit())
        .count();
    if (1..=3).contains(&digits) {
        let (prefix, num) = stem.split_at(stem.len() - digits);
        let prefix = prefix.trim_end_matches(['_', '-', ' ']);
        return Some((prefix, SeqKey::Number(num.parse().ok()?)));
    }
    let mut chars = stem.chars().rev();
    let last = chars.next()?;
    let sep = chars.next()?;
    if last.is_ascii_alphabetic() && matches!(sep, '_' | '-' | ' ') {
        let prefix = &stem[..stem.len() - 2];
        return Some((prefix, SeqKey::Letter(last.to_ascii_lowercase())));
    }
    None
}

#[derive(Debug, Default, Clone)]
pub struct ShallowFirstRanker;

impl CandidateRanker for ShallowFirstRanker {
    fn candidates(&self, entries: &[Entry]) -> Vec<Candidate> {
        let strip = common_root_depth(entries);
        let mut images: Vec<&Entry> = entries.iter().filter(|e| is_image_path(&e.path)).collect();
        images.sort_by(|a, b| {
            let da = depth(&a.path).saturating_sub(strip);
            let db = depth(&b.path).saturating_sub(strip);
            da.cmp(&db).then_with(|| a.path.cmp(&b.path))
        });
        images
            .into_iter()
            .enumerate()
            .map(|(rank, e)| Candidate {
                index: e.index,
                kind: CandidateKind::Image,
                score: -(rank as i32),
                reasons: vec![],
            })
            .collect()
    }

    fn version(&self) -> String {
        "shallow-first/1".into()
    }
}

pub fn common_root_depth(entries: &[Entry]) -> usize {
    let mut first: Option<&str> = None;
    for e in entries {
        let Some((top, _)) = e.path.split_once('/') else {
            return 0;
        };
        match first {
            None => first = Some(top),
            Some(f) if f != top => return 0,
            _ => {}
        }
    }
    usize::from(first.is_some())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn entries(paths: &[&str]) -> Vec<Entry> {
        paths
            .iter()
            .enumerate()
            .map(|(i, p)| Entry {
                index: i,
                path: p.to_string(),
                size: 0,
            })
            .collect()
    }

    fn ranking(ranker: &dyn CandidateRanker, paths: &[&str]) -> Vec<(String, i32)> {
        let es = entries(paths);
        let mut c = ranker.candidates(&es);
        c.retain(|c| c.score >= ranker.min_score());
        c.sort_by(|a, b| b.score.cmp(&a.score).then(a.index.cmp(&b.index)));
        c.into_iter()
            .map(|c| (es[c.index].path.clone(), c.score))
            .collect()
    }

    #[test]
    fn shallow_first_prefers_shallow_images() {
        let es = entries(&["s/素材/npc/a.png", "s/readme.txt", "s/表紙.jpg", "s/b.png"]);
        let order: Vec<_> = ShallowFirstRanker
            .candidates(&es)
            .into_iter()
            .map(|c| c.index)
            .collect();
        assert_eq!(order, vec![3, 2, 0]);
    }

    #[test]
    fn common_root_is_stripped_only_when_shared() {
        assert_eq!(common_root_depth(&entries(&["s/a.png", "s/x/b.png"])), 1);
        assert_eq!(common_root_depth(&entries(&["s/a.png", "t/b.png"])), 0);
        assert_eq!(common_root_depth(&entries(&["a.png", "s/b.png"])), 0);
        assert_eq!(common_root_depth(&[]), 0);
    }

    #[test]
    fn splits_sequences() {
        assert_eq!(
            split_sequence("trailer_sample_a"),
            Some(("trailer_sample", SeqKey::Letter('a')))
        );
        assert_eq!(
            split_sequence("trailer01"),
            Some(("trailer", SeqKey::Number(1)))
        );
        assert_eq!(
            split_sequence("page-12"),
            Some(("page", SeqKey::Number(12)))
        );
        assert_eq!(split_sequence("cover"), None);
        assert_eq!(split_sequence("scenario2026"), None, "4桁は西暦や日付等として扱う");
    }

    /// 典型的なシナリオ配布パッケージ（連番トレーラー・立ち絵素材・部屋画像・本文PDF）
    const SAMPLE_TRAILER_STRUCTURE: &[&str] = &[
        "scenario_pkg/NPC/npc_a/standing_normal_50.png",
        "scenario_pkg/NPC/npc_b/weapons/standing_battle_50.png",
        "scenario_pkg/NPC/npc_c/standing_normal_50.png",
        "scenario_pkg/room/room_bg_a.png",
        "scenario_pkg/room/room_bg_b.png",
        "scenario_pkg/Scenario/main_scenario.pdf",
        "scenario_pkg/Scenario/txt/scenario_text.txt",
        "scenario_pkg/trailer/trailer_image_a.png",
        "scenario_pkg/trailer/trailer_image_b.png",
        "scenario_pkg/trailer/trailer_image_c.png",
    ];

    #[test]
    fn trailer_sequence_with_assets_ranking() {
        let r = ranking(&ScoringRanker::default(), SAMPLE_TRAILER_STRUCTURE);
        let paths: Vec<&str> = r.iter().map(|(p, _)| p.as_str()).collect();
        assert_eq!(
            paths,
            [
                "scenario_pkg/Scenario/main_scenario.pdf",
                "scenario_pkg/trailer/trailer_image_a.png",
                "scenario_pkg/trailer/trailer_image_b.png",
                "scenario_pkg/trailer/trailer_image_c.png",
            ],
            "NPC と room は除外される: {r:?}"
        );
        let pdf = r[0].1 - 60;
        assert!(r[1].1 > pdf, "{r:?}");
    }

    /// ガイドPDF、エンドカード、同梱素材が混在する配布パッケージ
    const SAMPLE_MIXED_DOCS_STRUCTURE: &[&str] = &[
        "scenario_package/01_はじめにお読みください.pdf",
        "scenario_package/02_ゲームマスター/GMガイド.pdf",
        "scenario_package/02_ゲームマスター/ココフォリアルームデータ.zip",
        "scenario_package/03_エンドカード&アンケート/EndCard_GM.PNG",
        "scenario_package/03_エンドカード&アンケート/EndCard_Player.PNG",
        "scenario_package/03_エンドカード&アンケート/アンケートURL.txt",
        "scenario_package/04_BGM集/00_開演前の待機BGM.mp3",
    ];

    #[test]
    fn mixed_scenario_package_ranking() {
        let r = ranking(&ScoringRanker::default(), SAMPLE_MIXED_DOCS_STRUCTURE);
        assert_eq!(
            r[0].0, "scenario_package/02_ゲームマスター/GMガイド.pdf",
            "{r:?}"
        );
        assert!(r.last().unwrap().0.contains("はじめに"), "{r:?}");
        assert!(
            r.iter().any(|(p, _)| p.ends_with("EndCard_GM.PNG")),
            "{r:?}"
        );
    }

    #[test]
    fn file_name_clues_override_opposite_folder_clues() {
        let r = ranking(
            &ScoringRanker::default(),
            &[
                "u/セッション用素材/トレーラー1.png",
                "u/セッション用素材/bg_forest.png",
                "u/trailer/icon.png",
            ],
        );
        assert_eq!(r.len(), 1, "{r:?}");
        assert_eq!(r[0].0, "u/セッション用素材/トレーラー1.png");
    }

    #[test]
    fn full_width_digits_form_a_sequence() {
        let es = entries(&[
            "t/トレーラー４.png",
            "t/トレーラー1.png",
            "t/トレーラー２.png",
        ]);
        let seq = sequence_positions(&es);
        assert_eq!((seq[&1], seq[&2], seq[&0]), (0, 1, 2));
    }

    #[test]
    fn spoiler_documents_are_never_covers() {
        let r = ranking(
            &ScoringRanker::default(),
            &[
                "01_rule/01_rule.pdf",
                "02_handout/PC1.pdf",
                "03_ending/02_ED.pdf",
                "03_ending/03_commentary.pdf",
                "04_appx/02_trailer.png",
                "04_appx/03_logo.png",
                "room.zip",
            ],
        );
        let paths: Vec<&str> = r.iter().map(|(p, _)| p.as_str()).collect();
        assert!(!paths.iter().any(|p| p.contains("ending")), "{r:?}");
        let pos = |p: &str| paths.iter().position(|x| *x == p).unwrap();
        assert!(
            pos("04_appx/03_logo.png") > pos("04_appx/02_trailer.png"),
            "{r:?}"
        );
        assert_eq!(
            paths[..2],
            ["01_rule/01_rule.pdf", "04_appx/02_trailer.png"],
            "{r:?}"
        );
    }

    #[test]
    fn cover_keyword_is_ignored_when_it_is_a_naming_pattern() {
        let mut paths: Vec<String> = ["い", "ろ", "は", "に", "ほ"]
            .iter()
            .map(|k| format!("d/3.盤面カード/表紙：カード_{k}.png"))
            .collect();
        paths.push("d/3.盤面カード/ロゴ.png".into());
        paths.push("d/画像/表紙.png".into());
        let refs: Vec<&str> = paths.iter().map(|s| s.as_str()).collect();
        let r = ranking(&ScoringRanker::default(), &refs);
        let names: Vec<&str> = r.iter().map(|(p, _)| p.as_str()).collect();
        assert_eq!(
            names,
            ["d/画像/表紙.png", "d/3.盤面カード/ロゴ.png"],
            "{r:?}"
        );
    }

    #[test]
    fn explicit_cover_beats_pdf_and_trailer() {
        let r = ranking(
            &ScoringRanker::default(),
            &["s/trailer/t_1.png", "s/scenario.pdf", "s/表紙.png"],
        );
        assert_eq!(r[0].0, "s/表紙.png", "{r:?}");
    }

    #[test]
    fn negative_keywords_cancel_positive_ones() {
        let r = ranking(&ScoringRanker::default(), &["title_back.png", "art.png"]);
        assert!(
            r.iter().all(|(_, s)| *s == 0),
            "title(+100) と back(-100) は相殺される: {r:?}"
        );
    }

    #[test]
    fn version_changes_with_rules_text() {
        let a = ScoringRanker::default().version();
        let b = ScoringRanker::from_toml(&format!("{}\n# tweak", crate::rules::DEFAULT_RULES_TOML))
            .unwrap()
            .version();
        assert_ne!(a, b);
    }
}