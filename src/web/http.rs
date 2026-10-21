//! HTTP の取得（上限付き）。

use std::time::Duration;

/// HTML / JSON の大きさの上限。
pub const MAX_PAGE_BYTES: u64 = 8 * 1024 * 1024;
/// 画像の大きさの上限。
pub const MAX_IMAGE_BYTES: u64 = 32 * 1024 * 1024;

const USER_AGENT: &str = concat!("cover-extractor/", env!("CARGO_PKG_VERSION"), " (TRPG scenario catalog)");

/// HTTP クライアント。環境変数（`HTTPS_PROXY` / `NO_PROXY` など）のプロキシ設定に従う。
pub struct Http {
    #[cfg(feature = "web")]
    agent: ureq::Agent,
}

impl Default for Http {
    fn default() -> Self {
        Self::new()
    }
}

impl Http {
    #[cfg(feature = "web")]
    pub fn new() -> Self {
        let config = ureq::Agent::config_builder()
            .timeout_global(Some(Duration::from_secs(20)))
            .max_redirects(5)
            .user_agent(USER_AGENT)
            .build();
        Self { agent: config.into() }
    }

    #[cfg(not(feature = "web"))]
    pub fn new() -> Self {
        let _ = (Duration::ZERO, USER_AGENT);
        Self {}
    }

    /// URL の中身を最大 `limit` バイトまで読む。`referer` があれば付ける（画像のサーバーが求めることがある）。
    #[cfg(feature = "web")]
    pub fn get_bytes(&self, url: &str, referer: Option<&str>, limit: u64) -> Result<Vec<u8>, String> {
        let mut req = self.agent.get(url).header("Accept-Language", "ja,en;q=0.8");
        if let Some(r) = referer {
            req = req.header("Referer", r);
        }
        let mut resp = req.call().map_err(|e| describe(url, e))?;
        resp.body_mut()
            .with_config()
            .limit(limit)
            .read_to_vec()
            .map_err(|e| describe(url, e))
    }

    #[cfg(not(feature = "web"))]
    pub fn get_bytes(&self, _url: &str, _referer: Option<&str>, _limit: u64) -> Result<Vec<u8>, String> {
        Err("URL からの取得は無効です（`web` feature を有効にしてビルドしてください）".into())
    }

    /// URL の中身を文字列として読む（文字コードは自動判定）。
    pub fn get_text(&self, url: &str) -> Result<String, String> {
        let bytes = self.get_bytes(url, None, MAX_PAGE_BYTES)?;
        Ok(crate::info::text::decode_text(&bytes).0)
    }
}

#[cfg(feature = "web")]
fn describe(url: &str, e: ureq::Error) -> String {
    match e {
        ureq::Error::StatusCode(404) => format!("ページが見つかりません（404）: {url}"),
        ureq::Error::StatusCode(403) => format!("アクセスが拒否されました（403）: {url}"),
        ureq::Error::StatusCode(code) => format!("サーバーがエラーを返しました（{code}）: {url}"),
        ureq::Error::Timeout(_) => format!("時間内に応答がありませんでした: {url}"),
        ureq::Error::BodyExceedsLimit(n) => format!("データが大きすぎます（{n} バイトを超えました）: {url}"),
        other => format!("取得できませんでした（{other}）: {url}"),
    }
}
