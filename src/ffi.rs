//! DLL（C ABI）として他の言語から呼び出すためのインターフェース。

use std::cell::RefCell;
use std::collections::HashMap;
use std::ffi::{c_char, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::path::Path;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::{Arc, LazyLock, Mutex, MutexGuard};

use serde::Deserialize;
use serde_json::{json, Value};

use crate::extractor::{
    Choice, Confidence, Cover, CoverExtractor, CoverOrigin, ExtractorConfig, FallbackReason,
};
use crate::info::InfoExtractor;
use crate::web::WebExtractor;
use crate::limits::{MAX_READ_BYTES, run_on_worker};
use crate::select::{CandidateKind, ScoringRanker};

pub struct CeExtractor {
    inner: CoverExtractor,
    info: InfoExtractor,
    web: WebExtractor,
}

pub struct CeResult {
    json: CString,
    images: Vec<Vec<u8>>,
}

#[derive(Default)]
struct Registry {
    extractors: HashMap<usize, Arc<CeExtractor>>,
    results: HashMap<usize, Arc<CeResult>>,
    strings: HashMap<usize, CString>,
}

static REGISTRY: LazyLock<Mutex<Registry>> = LazyLock::new(Default::default);
static NEXT_ID: AtomicUsize = AtomicUsize::new(1);

fn registry() -> MutexGuard<'static, Registry> {
    REGISTRY.lock().unwrap_or_else(|e| e.into_inner())
}

fn new_handle() -> usize {
    NEXT_ID
        .fetch_add(1, Ordering::Relaxed)
        .wrapping_mul(16)
        .max(16)
}

const INVALID_HANDLE: &str =
    "invalid handle (not created by this library, already freed, or of the wrong type)";

thread_local! {
    static LAST_ERROR: RefCell<CString> = RefCell::new(CString::default());
}

fn set_error(msg: impl Into<String>) {
    let msg = msg.into().replace('\0', " ");
    LAST_ERROR.with(|e| *e.borrow_mut() = CString::new(msg).unwrap_or_default());
}

fn clear_error() {
    LAST_ERROR.with(|e| *e.borrow_mut() = CString::default());
}

fn guard<T>(fallback: T, f: impl FnOnce() -> Result<T, String>) -> T {
    clear_error();
    match catch_unwind(AssertUnwindSafe(f)) {
        Ok(Ok(v)) => v,
        Ok(Err(msg)) => {
            set_error(msg);
            fallback
        }
        Err(_) => {
            set_error("internal error (panic) in cover_extractor");
            fallback
        }
    }
}

unsafe fn read_str<'a>(p: *const c_char, what: &str) -> Result<&'a str, String> {
    if p.is_null() {
        return Err(format!("{what} is NULL"));
    }
    unsafe { CStr::from_ptr(p) }
        .to_str()
        .map_err(|_| format!("{what} is not valid UTF-8"))
}

unsafe fn read_opt_str<'a>(p: *const c_char, what: &str) -> Result<Option<&'a str>, String> {
    if p.is_null() {
        Ok(None)
    } else {
        unsafe { read_str(p, what) }.map(Some)
    }
}

fn into_result(json: Value, images: Vec<Vec<u8>>) -> Result<*mut CeResult, String> {
    into_result_text(json.to_string(), images)
}

fn into_result_text(json: String, images: Vec<Vec<u8>>) -> Result<*mut CeResult, String> {
    let json = CString::new(json).map_err(|e| e.to_string())?;
    let h = new_handle();
    registry()
        .results
        .insert(h, Arc::new(CeResult { json, images }));
    Ok(h as *mut CeResult)
}

fn extractor(ex: *const CeExtractor) -> Result<Arc<CeExtractor>, String> {
    if ex.is_null() {
        return Err("extractor is NULL".into());
    }
    registry()
        .extractors
        .get(&(ex as usize))
        .cloned()
        .ok_or_else(|| INVALID_HANDLE.into())
}

fn result(r: *const CeResult) -> Result<Arc<CeResult>, String> {
    if r.is_null() {
        return Err("result is NULL".into());
    }
    registry()
        .results
        .get(&(r as usize))
        .cloned()
        .ok_or_else(|| INVALID_HANDLE.into())
}

#[derive(Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct Options {
    rules_path: Option<String>,
    rules_toml: Option<String>,
    max_long_edge: Option<u32>,
    jpeg_quality: Option<u8>,
    max_attempts: Option<usize>,
    max_pdf_renders: Option<usize>,
    max_entry_bytes: Option<u64>,
    max_pdf_bytes: Option<u64>,
    info_rules_path: Option<String>,
    info_rules_toml: Option<String>,
}

#[unsafe(no_mangle)]
pub extern "C" fn ce_version() -> *const c_char {
    // コンパイル時保証された静的文字列ポインタ
    const VERSION_BYTES: &[u8] = concat!(env!("CARGO_PKG_VERSION"), "\0").as_bytes();
    VERSION_BYTES.as_ptr().cast()
}

#[unsafe(no_mangle)]
pub extern "C" fn ce_last_error() -> *const c_char {
    LAST_ERROR.with(|e| e.borrow().as_ptr())
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_extractor_new(options_json: *const c_char) -> *mut CeExtractor {
    guard(std::ptr::null_mut(), || {
        let opts: Options = match unsafe { read_opt_str(options_json, "options_json") }? {
            Some(s) if !s.trim().is_empty() => {
                serde_json::from_str(s).map_err(|e| format!("invalid options: {e}"))?
            }
            _ => Options::default(),
        };
        let ranker = match (&opts.rules_path, &opts.rules_toml) {
            (Some(_), Some(_)) => {
                return Err("specify either rules_path or rules_toml, not both".into());
            }
            (Some(p), None) => ScoringRanker::from_file(Path::new(p))
                .map_err(|e| format!("cannot load rules: {e}"))?,
            (None, Some(t)) => {
                ScoringRanker::from_toml(t).map_err(|e| format!("invalid rules: {e}"))?
            }
            (None, None) => ScoringRanker::default(),
        };
        let mut cfg = ExtractorConfig::default();
        if let Some(v) = opts.max_long_edge {
            cfg.thumbnail.max_long_edge = v.clamp(32, 4096);
        }
        if let Some(v) = opts.jpeg_quality {
            cfg.thumbnail.jpeg_quality = v.clamp(1, 100);
        }
        if let Some(v) = opts.max_attempts {
            cfg.max_attempts = v.clamp(1, 10_000);
        }
        if let Some(v) = opts.max_pdf_renders {
            cfg.max_pdf_renders = v.min(100);
        }
        if let Some(v) = opts.max_entry_bytes {
            cfg.max_entry_bytes = v.clamp(1, MAX_READ_BYTES);
        }
        if let Some(v) = opts.max_pdf_bytes {
            cfg.max_pdf_bytes = v.clamp(1, MAX_READ_BYTES);
        }
        let info = match (&opts.info_rules_path, &opts.info_rules_toml) {
            (Some(_), Some(_)) => {
                return Err("specify either info_rules_path or info_rules_toml, not both".into());
            }
            (Some(p), None) => InfoExtractor::from_rules_file(Path::new(p))
                .map_err(|e| format!("cannot load info rules: {e}"))?,
            (None, Some(t)) => {
                InfoExtractor::from_toml(t).map_err(|e| format!("invalid info rules: {e}"))?
            }
            (None, None) => InfoExtractor::new(),
        };
        let inner = CoverExtractor::with_ranker(cfg, Box::new(ranker));
        let h = new_handle();
        registry()
            .extractors
            .insert(h, Arc::new(CeExtractor { inner, info, web: WebExtractor::new() }));
        Ok(h as *mut CeExtractor)
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_extractor_free(ex: *mut CeExtractor) {
    clear_error();
    if !ex.is_null() && registry().extractors.remove(&(ex as usize)).is_none() {
        set_error(INVALID_HANDLE);
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_extract(ex: *const CeExtractor, path: *const c_char) -> *mut CeResult {
    guard(std::ptr::null_mut(), || {
        let ex = extractor(ex)?;
        let path = unsafe { read_str(path, "path") }?;
        let cover = ex.inner.extract(Path::new(path));
        cover_result(cover)
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_more_candidates(
    ex: *const CeExtractor,
    path: *const c_char,
    exclude_json: *const c_char,
    limit: u32,
) -> *mut CeResult {
    guard(std::ptr::null_mut(), || {
        let ex = extractor(ex)?;
        let path = unsafe { read_str(path, "path") }?;
        let exclude: Vec<String> = match unsafe { read_opt_str(exclude_json, "exclude_json") }? {
            Some(s) if !s.trim().is_empty() => serde_json::from_str(s)
                .map_err(|e| format!("exclude_json must be a JSON array of strings: {e}"))?,
            _ => Vec::new(),
        };
        let list = ex
            .inner
            .more_candidates(Path::new(path), &exclude, limit as usize)
            .map_err(|e| e.to_string())?;
        let mut images = Vec::new();
        let candidates: Vec<Value> = list
            .into_iter()
            .map(|c| choice_json(c, &mut images))
            .collect();
        into_result(json!({ "candidates": candidates }), images)
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_extract_entry(
    ex: *const CeExtractor,
    path: *const c_char,
    entry_path: *const c_char,
) -> *mut CeResult {
    guard(std::ptr::null_mut(), || {
        let ex = extractor(ex)?;
        let path = unsafe { read_str(path, "path") }?;
        let entry = unsafe { read_str(entry_path, "entry_path") }?;
        let cover = ex
            .inner
            .extract_entry(Path::new(path), entry)
            .map_err(|e| e.to_string())?;
        cover_result(cover)
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_extract_info(
    ex: *const CeExtractor,
    path: *const c_char,
) -> *mut CeResult {
    guard(std::ptr::null_mut(), || {
        let ex = extractor(ex)?;
        let path = unsafe { read_str(path, "path") }?;
        let info = ex.info.extract(Path::new(path)).map_err(|e| e.to_string())?;
        let json = serde_json::to_string(&info).map_err(|e| e.to_string())?;
        into_result_text(json, Vec::new())
    })
}

/// URL（BOOTH の商品ページなど）から、題名・あらすじ・概要と表紙画像を取り出す。
///
/// 結果の JSON:
/// `{"site": "booth", "url": ..., "info": {ce_extract_info と同じ形}, "page_title": 商品名,
///   "title_systems": [商品名に含まれていたシステム名],
///   "synopsis_candidates": [{"label": "トレーラー", "text": ..., "tier": 0}, ...]（あらすじの候補。先頭が info.synopsis）,
///   "tags": [...], "image": 0 または null,
///   "image_url": ..., "width": ..., "height": ..., "is_adult": false, "warnings": [...]}`
/// 表紙が取れた場合は、画像 0 番にサムネイルの JPEG が入る。
#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_extract_url(ex: *const CeExtractor, url: *const c_char) -> *mut CeResult {
    guard(std::ptr::null_mut(), || {
        let ex = extractor(ex)?;
        let url = unsafe { read_str(url, "url") }?;
        let thumb_cfg = &ex.inner.config().thumbnail;
        let web = run_on_worker(|| ex.web.extract(url, &ex.info, thumb_cfg))?;
        let mut images = Vec::new();
        let (image, width, height) = match &web.image {
            Some(t) => {
                images.push(t.jpeg.clone());
                (Some(0), Some(t.width), Some(t.height))
            }
            None => (None, None, None),
        };
        let json = json!({
            "site": web.site,
            "url": web.url,
            "info": serde_json::to_value(&web.info).map_err(|e| e.to_string())?,
            "page_title": web.page_title,
            "title_systems": web.title_systems,
            "synopsis_candidates": web.synopsis_candidates,
            "tags": web.tags,
            "image": image,
            "image_url": web.image_url,
            "width": width,
            "height": height,
            "is_adult": web.is_adult,
            "warnings": web.warnings,
        });
        into_result(json, images)
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_cache_key(ex: *const CeExtractor, path: *const c_char) -> *mut c_char {
    guard(std::ptr::null_mut(), || {
        let ex = extractor(ex)?;
        let path = unsafe { read_str(path, "path") }?;
        let key = ex
            .inner
            .cache_key_for_path(Path::new(path))
            .map_err(|e| e.to_string())?;
        let s = CString::new(key).map_err(|e| e.to_string())?;
        let ptr = s.as_ptr() as *mut c_char;
        registry().strings.insert(ptr as usize, s);
        Ok(ptr)
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_string_free(s: *mut c_char) {
    clear_error();
    if !s.is_null() && registry().strings.remove(&(s as usize)).is_none() {
        set_error(INVALID_HANDLE);
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_result_json(r: *const CeResult) -> *const c_char {
    guard(std::ptr::null(), || {
        let res = result(r)?;
        Ok(res.json.as_ptr())
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_result_image_count(r: *const CeResult) -> u32 {
    guard(0, || {
        Ok(result(r)?.images.len().min(u32::MAX as usize) as u32)
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_result_image(
    r: *const CeResult,
    index: u32,
    data: *mut *const u8,
    len: *mut usize,
) -> i32 {
    guard(-1, || {
        if data.is_null() || len.is_null() {
            return Err("data or len is NULL".into());
        }
        let res = result(r)?;
        let img = res
            .images
            .get(index as usize)
            .ok_or_else(|| format!("image index {index} out of range ({})", res.images.len()))?;
        unsafe {
            *data = img.as_ptr();
            *len = img.len();
        }
        Ok(0)
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_result_save_image(
    r: *const CeResult,
    index: u32,
    out_path: *const c_char,
) -> i32 {
    guard(-1, || {
        let res = result(r)?;
        let out = unsafe { read_str(out_path, "out_path") }?;
        let img = res
            .images
            .get(index as usize)
            .ok_or_else(|| format!("image index {index} out of range ({})", res.images.len()))?;
        std::fs::write(out, img).map_err(|e| format!("cannot write {out}: {e}"))?;
        Ok(0)
    })
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn ce_result_free(r: *mut CeResult) {
    clear_error();
    if !r.is_null() && registry().results.remove(&(r as usize)).is_none() {
        set_error(INVALID_HANDLE);
    }
}

fn kind_str(k: CandidateKind) -> &'static str {
    match k {
        CandidateKind::Image => "image",
        CandidateKind::PdfFirstPage => "pdf_first_page",
    }
}

fn choice_json(c: Choice, images: &mut Vec<Vec<u8>>) -> Value {
    let index = images.len();
    images.push(c.jpeg);
    json!({
        "image": index,
        "entry_path": c.entry_path,
        "kind": kind_str(c.kind),
        "score": c.score,
        "reasons": c.reasons,
        "width": c.width,
        "height": c.height,
    })
}

fn cover_result(cover: Cover) -> Result<*mut CeResult, String> {
    let needs_review = cover.needs_review();
    let mut images = vec![cover.jpeg];
    let (confidence, ambiguity_reason) = match &cover.confidence {
        Confidence::Confident => ("confident", None),
        Confidence::Ambiguous { reason } => ("ambiguous", Some(reason.clone())),
        Confidence::NotFound => ("not_found", None),
        Confidence::UserSelected => ("user_selected", None),
    };
    let cover_json = match cover.origin {
        CoverOrigin::Extracted {
            entry_path,
            kind,
            source_width,
            source_height,
            score,
            reasons,
        } => json!({
            "image": 0,
            "placeholder": false,
            "entry_path": entry_path,
            "kind": kind_str(kind),
            "width": cover.width,
            "height": cover.height,
            "source_width": source_width,
            "source_height": source_height,
            "score": score,
            "reasons": reasons,
        }),
        CoverOrigin::Placeholder { reason } => json!({
            "image": 0,
            "placeholder": true,
            "placeholder_reason": match reason {
                FallbackReason::SourceUnreadable(e) => format!("source_unreadable: {e}"),
                FallbackReason::NoCandidates => "no_candidates".into(),
                FallbackReason::AllCandidatesFailed => "all_candidates_failed".into(),
            },
            "width": cover.width,
            "height": cover.height,
        }),
    };
    let choices: Vec<Value> = cover
        .choices
        .into_iter()
        .map(|c| choice_json(c, &mut images))
        .collect();
    let failed: Vec<Value> = cover
        .failed_attempts
        .into_iter()
        .map(|f| json!({ "entry_path": f.entry_path, "error": f.error }))
        .collect();
    into_result(
        json!({
            "cover": cover_json,
            "confidence": confidence,
            "needs_review": needs_review,
            "ambiguity_reason": ambiguity_reason,
            "choices": choices,
            "failed_attempts": failed,
            "cache_key": cover.cache_key,
        }),
        images,
    )
}