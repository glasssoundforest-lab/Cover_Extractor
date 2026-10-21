//! 表紙抽出のエントリポイント。
//!
//! ソースを開く → 候補に点数を付ける → 点数の高い順に読んで減点を確定 → 最高点を採用、
//! 全滅ならプレースホルダー、という流れをまとめる。
//! どの段階で失敗してもパニックせず、必ず `Cover` を返す。
//!
//! 判定に迷った場合（1位の点数が低い、または2位との差が小さい）は、
//! `Cover::choices` に選択肢を入れて返す。選択肢に正解がなければ
//! `more_candidates` で続きの候補を取り出せる。選ばれた候補は `extract_entry` で表紙にする。

use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap, HashSet};
use std::path::Path;
use std::sync::OnceLock;

use sha2::{Digest, Sha256};

use crate::error::SourceError;
use crate::limits::run_on_worker;
use crate::names::normalize_path;
use crate::pdf::render_first_page;
use crate::placeholder::placeholder_jpeg;
use crate::select::{
    common_root_depth, Candidate, CandidateKind, CandidateRanker, Evidence, ScoringRanker,
};
use crate::source::{fingerprint_for_path, open_source, SourceAccessor, SourceFingerprint};
use crate::thumbnail::{finish_thumbnail, make_thumbnail, Thumbnail, ThumbnailConfig};

/// `more_candidates` が1回で返す件数の上限。
const MAX_MORE_PER_CALL: usize = 100;

/// 抽出処理全体のバージョン。出力に影響する変更をしたら上げる（キャッシュ無効化用）。
pub const EXTRACTOR_VERSION: &str = "cover-extractor/0.3.0";

/// 抽出の設定。
#[derive(Debug, Clone)]
pub struct ExtractorConfig {
    pub thumbnail: ThumbnailConfig,
    /// 画像1件あたりの読み込み上限（バイト）。ZIP bomb・巨大ファイル対策。
    pub max_entry_bytes: u64,
    /// PDF 1件あたりの読み込み上限（バイト）。シナリオ PDF は大きいことが多いので別枠。
    pub max_pdf_bytes: u64,
    /// 表紙を1つ決めるまでに、候補を最大何件まで実際に読むか。
    pub max_attempts: usize,
    /// 1回の処理で PDF を最大何件まで描画するか（PDF の描画は画像より重い）。
    pub max_pdf_renders: usize,
}

impl Default for ExtractorConfig {
    fn default() -> Self {
        Self {
            thumbnail: ThumbnailConfig::default(),
            max_entry_bytes: 64 * 1024 * 1024,
            max_pdf_bytes: 256 * 1024 * 1024,
            max_attempts: 8,
            max_pdf_renders: 3,
        }
    }
}

/// 抽出結果。成功時もプレースホルダー時も同じ形で返す。
#[derive(Debug, Clone)]
pub struct Cover {
    /// JPEGバイト列。
    pub jpeg: Vec<u8>,
    pub width: u32,
    pub height: u32,
    pub origin: CoverOrigin,
    /// 判定の確かさ。
    pub confidence: Confidence,
    /// 判定に迷った場合の選択肢（先頭は採用した候補）。迷っていなければ空。
    pub choices: Vec<Choice>,
    /// 読み込みやデコードに失敗した候補と理由（調査用）。
    pub failed_attempts: Vec<FailedAttempt>,
    /// キャッシュキー。ソースを開けなかった場合は `None`。
    pub cache_key: Option<String>,
}

impl Cover {
    pub fn is_placeholder(&self) -> bool {
        matches!(self.origin, CoverOrigin::Placeholder { .. })
    }

    /// 採用したエントリのパス（プレースホルダーなら `None`）。
    pub fn entry_path(&self) -> Option<&str> {
        match &self.origin {
            CoverOrigin::Extracted { entry_path, .. } => Some(entry_path),
            CoverOrigin::Placeholder { .. } => None,
        }
    }

    /// ユーザーに選んでもらうべきか。
    pub fn needs_review(&self) -> bool {
        !matches!(self.confidence, Confidence::Confident)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CoverOrigin {
    /// ソース内の画像（または PDF の1ページ目）から作った。
    Extracted {
        entry_path: String,
        kind: CandidateKind,
        source_width: u32,
        source_height: u32,
        /// 最終的な点数と、その内訳。
        score: i32,
        reasons: Vec<String>,
    },
    /// プレースホルダーを返した。
    Placeholder { reason: FallbackReason },
}

/// 判定の確かさ。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Confidence {
    /// 1位が十分に高く、2位との差も大きい。
    Confident,
    /// 迷っている。`Cover::choices` から選んでもらう。
    Ambiguous { reason: String },
    /// 表紙が見つからなかった（プレースホルダー）。`more_candidates` で探せる場合がある。
    NotFound,
    /// ユーザーが選んだ。
    UserSelected,
}

/// 表紙の選択肢。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Choice {
    pub entry_path: String,
    pub kind: CandidateKind,
    pub score: i32,
    pub reasons: Vec<String>,
    /// サムネイル（JPEG）。そのまま表紙として使える。
    pub jpeg: Vec<u8>,
    pub width: u32,
    pub height: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FallbackReason {
    /// フォルダ / ZIP を開けなかった（存在しない、壊れている、非対応形式など）。
    SourceUnreadable(String),
    /// 表紙候補（画像・PDF）が1つもなかった。除外キーワードで全部外れた場合も含む。
    NoCandidates,
    /// 候補はあったが、すべて読み込みに失敗した。
    AllCandidatesFailed,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FailedAttempt {
    pub entry_path: String,
    pub error: String,
}

/// 表紙抽出器。スレッド間で共有できる（`&self` で呼べる）。
pub struct CoverExtractor {
    config: ExtractorConfig,
    ranker: Box<dyn CandidateRanker>,
    placeholder: OnceLock<(Vec<u8>, u32, u32)>,
}

impl Default for CoverExtractor {
    fn default() -> Self {
        Self::new(ExtractorConfig::default())
    }
}

impl CoverExtractor {
    /// 既定のスコアリング（組み込みの `rules.toml`）で抽出器を作る。
    pub fn new(config: ExtractorConfig) -> Self {
        Self::with_ranker(config, Box::new(ScoringRanker::default()))
    }

    /// 判定器を差し替える（独自の `rules.toml` を使う場合など）。
    pub fn with_ranker(config: ExtractorConfig, ranker: Box<dyn CandidateRanker>) -> Self {
        Self {
            config,
            ranker,
            placeholder: OnceLock::new(),
        }
    }

    pub fn config(&self) -> &ExtractorConfig {
        &self.config
    }

    pub fn ranker(&self) -> &dyn CandidateRanker {
        self.ranker.as_ref()
    }

    /// フォルダまたはZIPのパスから表紙を取り出す。失敗してもプレースホルダーを返す。
    pub fn extract(&self, path: &Path) -> Cover {
        match open_source(path) {
            Ok(mut source) => self.extract_from(source.as_mut()),
            Err(e) => self.placeholder_cover(
                FallbackReason::SourceUnreadable(e.to_string()),
                vec![],
                vec![],
                None,
            ),
        }
    }

    /// 開いたソースから表紙を取り出す。
    pub fn extract_from(&self, source: &mut dyn SourceAccessor) -> Cover {
        let cache_key = Some(self.cache_key(source.fingerprint()));
        let cs = self.ranker.choice_settings();
        let candidates = self.ranker.candidates(source.entries());
        let mut search = Search::new(
            self,
            source,
            candidates,
            self.ranker.min_score(),
            &[],
            Budget {
                attempts: self.config.max_attempts,
                pdf_renders: self.config.max_pdf_renders,
            },
        );
        if search.is_empty() {
            // 通常候補が0件の場合でも、除外キーワードを含む候補から選択肢を集める
            let fallback_candidates = self.ranker.candidates(source.entries());
            let mut fallback_search = Search::new(
                self,
                source,
                fallback_candidates,
                cs.browse_floor,
                &[],
                Budget {
                    attempts: cs.count * 2,
                    pdf_renders: self.config.max_pdf_renders,
                },
            );
            fallback_search.enable_diversity(cs.per_section, &[]);
            let mut choices = Vec::new();
            while choices.len() < cs.count {
                let Some(f) = fallback_search.next_final() else { break };
                choices.push(f.into_choice());
            }

            return self.placeholder_cover(
                FallbackReason::NoCandidates,
                choices,
                vec![],
                cache_key,
            );
        }

        let Some(best) = search.next_final() else {
            let failed = search.failed;
            // 評価した候補が全滅した場合でも、除外候補（NPC・マップ等）から選択肢を収集
            let fallback_candidates = self.ranker.candidates(source.entries());
            let mut fallback_search = Search::new(
                self,
                source,
                fallback_candidates,
                cs.browse_floor,
                &[],
                Budget {
                    attempts: cs.count * 2,
                    pdf_renders: self.config.max_pdf_renders,
                },
            );
            fallback_search.enable_diversity(cs.per_section, &[]);
            let mut choices = Vec::new();
            while choices.len() < cs.count {
                let Some(f) = fallback_search.next_final() else { break };
                choices.push(f.into_choice());
            }

            return self.placeholder_cover(
                FallbackReason::AllCandidatesFailed,
                choices,
                failed,
                cache_key,
            );
        };

        // ---- 迷っているか
        let mut reason = (best.score() < cs.min_confident_score)
            .then(|| format!("best score {} < {}", best.score(), cs.min_confident_score));
        let mut taken = vec![best];
        if reason.is_none()
            && let Some(upper) = search.peek_score()
            && taken[0].score().saturating_sub(upper) < cs.min_margin
        {
            // 2位の楽観値が近い → 実際に読んで確かめる
            search.extend_budget(cs.max_attempts);
            if let Some(second) = search.next_final() {
                if taken[0].score().saturating_sub(second.score()) < cs.min_margin {
                    reason = Some(format!(
                        "close scores: {} vs {} ({})",
                        taken[0].score(),
                        second.score(),
                        second.entry_path
                    ));
                }
                taken.push(second);
            }
        }

        // ---- 迷っていれば選択肢を集める
        let mut choices = Vec::new();
        if reason.is_some() {
            search.extend_budget(cs.max_attempts);
            let shown: Vec<String> = taken.iter().map(|f| f.entry_path.clone()).collect();
            search.enable_diversity(cs.per_section, &shown);
            choices.extend(taken.iter().cloned().map(Finalized::into_choice));
            while choices.len() < cs.count {
                let Some(f) = search.next_final() else { break };
                choices.push(f.into_choice());
            }
        }

        let best = taken.swap_remove(0);
        let confidence = match reason {
            Some(reason) => Confidence::Ambiguous { reason },
            None => Confidence::Confident,
        };
        best.into_cover(confidence, choices, search.failed, cache_key)
    }

    /// 「その他の候補」を返す。
    pub fn more_candidates(
        &self,
        path: &Path,
        exclude: &[String],
        limit: usize,
    ) -> Result<Vec<Choice>, SourceError> {
        let limit = limit.min(MAX_MORE_PER_CALL);
        let mut source = open_source(path)?;
        let cs = self.ranker.choice_settings();
        let candidates = self.ranker.candidates(source.entries());
        let mut search = Search::new(
            self,
            source.as_mut(),
            candidates,
            cs.browse_floor,
            exclude,
            Budget {
                attempts: limit.saturating_mul(2).saturating_add(4),
                pdf_renders: self.config.max_pdf_renders.min(limit),
            },
        );
        search.enable_diversity(cs.per_section, exclude);
        let mut out = Vec::new();
        while out.len() < limit {
            let Some(f) = search.next_final() else { break };
            out.push(f.into_choice());
        }
        Ok(out)
    }

    /// ユーザーが選んだエントリを表紙にする。
    pub fn extract_entry(&self, path: &Path, entry_path: &str) -> Result<Cover, SourceError> {
        let mut source = open_source(path)?;
        let cache_key = Some(self.cache_key(source.fingerprint()));
        let normalized_target = normalize_path(entry_path);
        let entry = source
            .entries()
            .iter()
            .find(|e| normalize_path(&e.path) == normalized_target)
            .cloned()
            .ok_or_else(|| SourceError::NoSuchEntryPath(entry_path.to_string()))?;
        let kind = if entry.path.to_lowercase().ends_with(".pdf") {
            CandidateKind::PdfFirstPage
        } else {
            CandidateKind::Image
        };
        let candidate = Candidate {
            index: entry.index,
            kind,
            score: 0,
            reasons: vec!["selected by user".into()],
        };
        let thumb = self
            .evaluate(source.as_mut(), &candidate)
            .map_err(|reason| SourceError::Unreadable {
                path: entry_path.to_string(),
                reason,
            })?;
        let f = Finalized {
            candidate,
            entry_path: entry.path,
            thumbnail: thumb,
        };
        Ok(f.into_cover(Confidence::UserSelected, vec![], vec![], cache_key))
    }

    /// 候補を実際に読んでサムネイルを作る。
    fn evaluate(
        &self,
        source: &mut dyn SourceAccessor,
        c: &Candidate,
    ) -> Result<Thumbnail, String> {
        run_on_worker(|| self.evaluate_on_this_thread(source, c))
    }

    fn evaluate_on_this_thread(
        &self,
        source: &mut dyn SourceAccessor,
        c: &Candidate,
    ) -> Result<Thumbnail, String> {
        let cfg = &self.config;
        match c.kind {
            CandidateKind::Image => {
                let bytes = source
                    .read_entry(c.index, cfg.max_entry_bytes)
                    .map_err(|e| e.to_string())?;
                make_thumbnail(&bytes, &cfg.thumbnail).map_err(|e| e.to_string())
            }
            CandidateKind::PdfFirstPage => {
                let bytes = source
                    .read_entry(c.index, cfg.max_pdf_bytes)
                    .map_err(|e| e.to_string())?;
                let page = render_first_page(bytes, cfg.thumbnail.max_long_edge)
                    .map_err(|e| e.to_string())?;
                finish_thumbnail(page, &cfg.thumbnail).map_err(|e| e.to_string())
            }
        }
    }

    /// ソースの中身を読まずにキャッシュキーを計算する。
    pub fn cache_key_for_path(&self, path: &Path) -> Result<String, SourceError> {
        let fp = fingerprint_for_path(path)?;
        Ok(self.cache_key(&fp))
    }

    /// キャッシュキー（SHA-256 の16進文字列）。
    pub fn cache_key(&self, fp: &SourceFingerprint) -> String {
        let t = &self.config.thumbnail;
        let parts = [
            EXTRACTOR_VERSION.to_string(),
            self.ranker.version(),
            format!("pdf={}", cfg!(feature = "pdf")),
            format!(
                "{}:{}:{}:{:?}",
                t.max_long_edge, t.jpeg_quality, t.min_source_edge, t.background
            ),
            fp.kind.to_string(),
            fp.identity.clone(),
            fp.revision.clone(),
        ];
        let mut hasher = Sha256::new();
        for p in &parts {
            hasher.update(p.as_bytes());
            hasher.update([0u8]);
        }
        hasher
            .finalize()
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect()
    }

    fn placeholder_cover(
        &self,
        reason: FallbackReason,
        choices: Vec<Choice>,
        failed_attempts: Vec<FailedAttempt>,
        cache_key: Option<String>,
    ) -> Cover {
        let t = &self.config.thumbnail;
        let (jpeg, width, height) = self
            .placeholder
            .get_or_init(|| placeholder_jpeg(t.max_long_edge, t.jpeg_quality).unwrap_or_default())
            .clone();
        Cover {
            jpeg,
            width,
            height,
            origin: CoverOrigin::Placeholder { reason },
            confidence: Confidence::NotFound,
            choices,
            failed_attempts,
            cache_key,
        }
    }
}

// ------------------------------------------------------------------ 探索

#[derive(Debug, Clone)]
struct Finalized {
    candidate: Candidate,
    entry_path: String,
    thumbnail: Thumbnail,
}

impl Finalized {
    fn score(&self) -> i32 {
        self.candidate.score
    }

    fn into_choice(self) -> Choice {
        Choice {
            entry_path: self.entry_path,
            kind: self.candidate.kind,
            score: self.candidate.score,
            reasons: self.candidate.reasons,
            jpeg: self.thumbnail.jpeg,
            width: self.thumbnail.width,
            height: self.thumbnail.height,
        }
    }

    fn into_cover(
        self,
        confidence: Confidence,
        choices: Vec<Choice>,
        failed_attempts: Vec<FailedAttempt>,
        cache_key: Option<String>,
    ) -> Cover {
        let (c, t) = (self.candidate, self.thumbnail);
        Cover {
            jpeg: t.jpeg,
            width: t.width,
            height: t.height,
            origin: CoverOrigin::Extracted {
                entry_path: self.entry_path,
                kind: c.kind,
                source_width: t.source_width,
                source_height: t.source_height,
                score: c.score,
                reasons: c.reasons,
            },
            confidence,
            choices,
            failed_attempts,
            cache_key,
        }
    }
}

#[derive(Debug, Clone, Copy)]
struct Budget {
    attempts: usize,
    pdf_renders: usize,
}

struct Queued {
    candidate: Candidate,
    order: usize,
    thumbnail: Option<Thumbnail>,
}

impl PartialEq for Queued {
    fn eq(&self, other: &Self) -> bool {
        self.cmp(other) == Ordering::Equal
    }
}
impl Eq for Queued {}
impl PartialOrd for Queued {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for Queued {
    fn cmp(&self, other: &Self) -> Ordering {
        self.candidate
            .score
            .cmp(&other.candidate.score)
            .then_with(|| other.order.cmp(&self.order))
    }
}

struct Search<'a> {
    ex: &'a CoverExtractor,
    source: &'a mut dyn SourceAccessor,
    queue: BinaryHeap<Queued>,
    budget: Budget,
    used: Budget,
    failed: Vec<FailedAttempt>,
    strip: usize,
    diversity: Option<Diversity>,
}

struct Diversity {
    quota: usize,
    counts: HashMap<String, usize>,
    deferred: Vec<Queued>,
}

fn section(path: &str, strip: usize) -> String {
    let segs: Vec<&str> = path.split('/').skip(strip).collect();
    if segs.len() >= 2 {
        segs[0].to_string()
    } else {
        String::new()
    }
}

impl<'a> Search<'a> {
    fn new(
        ex: &'a CoverExtractor,
        source: &'a mut dyn SourceAccessor,
        candidates: Vec<Candidate>,
        floor: i32,
        exclude: &[String],
        budget: Budget,
    ) -> Self {
        let exclude: HashSet<String> = exclude.iter().map(|s| normalize_path(s)).collect();
        let entries = source.entries();
        let queue = candidates
            .into_iter()
            .filter(|c| c.score >= floor)
            .filter(|c| cfg!(feature = "pdf") || c.kind != CandidateKind::PdfFirstPage)
            .filter(|c| !exclude.contains(&normalize_path(&entries[c.index].path)))
            .enumerate()
            .map(|(order, candidate)| Queued {
                candidate,
                order,
                thumbnail: None,
            })
            .collect();
        let strip = common_root_depth(entries);
        Self {
            ex,
            source,
            queue,
            budget,
            used: Budget {
                attempts: 0,
                pdf_renders: 0,
            },
            failed: Vec::new(),
            strip,
            diversity: None,
        }
    }

    fn enable_diversity(&mut self, quota: usize, already: &[String]) {
        let mut counts = HashMap::new();
        let mut seen = HashSet::new();
        for p in already.iter() {
            let norm = normalize_path(p);
            if seen.insert(norm) {
                *counts.entry(section(p, self.strip)).or_default() += 1;
            }
        }
        self.diversity = Some(Diversity {
            quota: quota.max(1),
            counts,
            deferred: Vec::new(),
        });
    }

    fn is_empty(&self) -> bool {
        self.queue.is_empty()
    }

    fn peek_score(&self) -> Option<i32> {
        self.queue.peek().map(|q| q.candidate.score)
    }

    fn extend_budget(&mut self, attempts: usize) {
        self.budget.attempts = self.budget.attempts.max(attempts);
        self.budget.pdf_renders = self
            .budget
            .pdf_renders
            .max(self.used.pdf_renders.saturating_add(2));
    }

    fn next_final(&mut self) -> Option<Finalized> {
        loop {
            let Some(mut item) = self.queue.pop() else {
                match self.diversity.as_mut() {
                    Some(d) if !d.deferred.is_empty() => {
                        d.quota += 1;
                        self.queue.extend(d.deferred.drain(..));
                        continue;
                    }
                    _ => return None,
                }
            };
            let entry_path = self.source.entries()[item.candidate.index].path.clone();

            if let Some(d) = self.diversity.as_mut() {
                let key = section(&entry_path, self.strip);
                if d.counts.get(&key).copied().unwrap_or(0) >= d.quota {
                    d.deferred.push(item);
                    continue;
                }
            }

            if let Some(thumbnail) = item.thumbnail {
                if let Some(d) = self.diversity.as_mut() {
                    *d.counts
                        .entry(section(&entry_path, self.strip))
                        .or_default() += 1;
                }
                return Some(Finalized {
                    candidate: item.candidate,
                    entry_path,
                    thumbnail,
                });
            }

            let is_pdf = item.candidate.kind == CandidateKind::PdfFirstPage;
            if self.used.attempts >= self.budget.attempts
                || (is_pdf && self.used.pdf_renders >= self.budget.pdf_renders)
            {
                continue;
            }
            self.used.attempts += 1;
            self.used.pdf_renders += usize::from(is_pdf);

            match self.ex.evaluate(self.source, &item.candidate) {
                Ok(thumb) => {
                    let evidence = Evidence {
                        width: thumb.source_width,
                        height: thumb.source_height,
                        dominant_ratio: thumb.dominant_ratio,
                    };
                    for (delta, why) in self.ex.ranker.adjust(&item.candidate, &evidence) {
                        let delta = delta.min(0);
                        item.candidate.score = item.candidate.score.saturating_add(delta);
                        item.candidate.reasons.push(format!("{delta:+} {why}"));
                    }
                    item.thumbnail = Some(thumb);
                    self.queue.push(item);
                }
                Err(error) => self.failed.push(FailedAttempt { entry_path, error }),
            }
        }
    }
}