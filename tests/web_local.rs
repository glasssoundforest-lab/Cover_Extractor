//! URL からの取得を、手元で動かした HTTP サーバーで確かめる（実際の BOOTH には接続しない）。
#![cfg(feature = "web")]

use std::collections::HashMap;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::{Arc, Mutex};

use cover_extractor::web::booth::BoothFetcher;
use cover_extractor::web::generic::GenericFetcher;
use cover_extractor::web::Http;
use cover_extractor::{InfoExtractor, ThumbnailConfig, WebExtractor};

type Files = Arc<Mutex<HashMap<String, (&'static str, Vec<u8>)>>>;

/// パス → (Content-Type, 中身) を返すだけの HTTP サーバー。ポート番号と、中身を足すための表を返す。
fn serve() -> (u16, Files) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = listener.local_addr().unwrap().port();
    let files: Files = Arc::new(Mutex::new(HashMap::new()));
    let shared = files.clone();
    std::thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(mut s) = stream else { continue };
            let files = shared.clone();
            std::thread::spawn(move || {
                let mut buf = vec![0u8; 8192];
                let n = s.read(&mut buf).unwrap_or(0);
                let req = String::from_utf8_lossy(&buf[..n]);
                let path = req.split_whitespace().nth(1).unwrap_or("/").to_string();
                let found = files.lock().unwrap().get(&path).cloned();
                let (status, ctype, body) = match found {
                    Some((t, b)) => ("200 OK", t, b),
                    None => ("404 Not Found", "text/plain", b"not found".to_vec()),
                };
                let head = format!(
                    "HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                );
                let _ = s.write_all(head.as_bytes());
                let _ = s.write_all(&body);
            });
        }
    });
    (port, files)
}

fn png(w: u32, h: u32) -> Vec<u8> {
    let img = image::RgbImage::from_fn(w, h, |x, y| image::Rgb([(x % 256) as u8, (y % 256) as u8, 128]));
    let mut out = std::io::Cursor::new(Vec::new());
    img.write_to(&mut out, image::ImageFormat::Png).unwrap();
    out.into_inner()
}

#[test]
fn booth_item_from_json() {
    let (port, files) = serve();
    let base = format!("http://127.0.0.1:{port}");
    let json = format!(
        r#"{{"description":"■制作\n【商品名】クトゥルフ神話TRPG「霧の山荘」\n\n■シナリオデータ\n▼概要\n「新クトゥルフ神話TRPG」\nプレイ人数：２人\nプレイ時間：４～６時間（ボイスセッション基準）\n▼トレーラー\n山奥の山荘に招かれた二人。\n霧の夜が明けたとき、館の主人の姿はなかった。\n▼ハンドアウト\nHO1 招待客",
            "id":1234,"is_adult":false,"name":"クトゥルフ神話TRPG「霧の山荘」","url":"https://shop.booth.pm/items/1234",
            "images":[{{"caption":null,"original":"{base}/img/missing.png","resized":null}},{{"caption":null,"original":"{base}/img/cover.png","resized":null}}],
            "tags":[{{"name":"TRPG","url":"x"}},{{"name":"CoC","url":"y"}}]}}"#
    );
    {
        let mut f = files.lock().unwrap();
        f.insert("/ja/items/1234.json".into(), ("application/json", json.into_bytes()));
        f.insert("/img/cover.png".into(), ("image/png", png(400, 600)));
    }
    let web = WebExtractor::with_fetchers(Http::new(), vec![Box::new(BoothFetcher { base: base.clone() }), Box::new(GenericFetcher)]);
    let info_ex = InfoExtractor::new();
    let r = web.extract("https://booth.pm/ja/items/1234", &info_ex, &ThumbnailConfig::default()).unwrap();
    assert_eq!(r.site, "booth");
    assert_eq!(r.url, "https://shop.booth.pm/items/1234");
    assert_eq!(r.info.title.as_ref().unwrap().value, "霧の山荘");
    assert_eq!(r.info.overview.as_ref().unwrap().value, "推奨人数：２人\nプレイ時間：４～６時間（ボイスセッション基準）");
    assert_eq!(r.info.synopsis.as_ref().unwrap().value, "山奥の山荘に招かれた二人。\n霧の夜が明けたとき、館の主人の姿はなかった。");
    assert_eq!(r.info.system.as_ref().unwrap().value, "クトゥルフ神話TRPG");
    assert_eq!(r.tags, ["TRPG", "CoC"]);
    assert_eq!(r.page_title.as_deref(), Some("クトゥルフ神話TRPG「霧の山荘」"));
    assert_eq!(r.title_systems, ["クトゥルフ神話TRPG"]);
    let labels: Vec<&str> = r.synopsis_candidates.iter().map(|c| c.label.as_str()).collect();
    assert_eq!(labels, ["トレーラー"]);
    // 1枚目の画像は 404 → 警告に残し、2枚目を表紙にする
    let t = r.image.as_ref().expect("thumbnail");
    assert_eq!((t.width, t.height), (400, 600));
    assert_eq!(r.image_url.as_deref(), Some(format!("{base}/img/cover.png").as_str()));
    assert!(r.warnings.iter().any(|w| w.contains("404")), "{:?}", r.warnings);

    // ショップの URL（xxx.booth.pm）でも同じ商品番号で読む。存在しない商品は 404
    let e = web.extract("https://xxx.booth.pm/items/99", &info_ex, &ThumbnailConfig::default()).unwrap_err();
    assert!(e.contains("404"), "{e}");
}

/// 説明文が短く、あらすじなどが商品ページの見出し付きの欄にだけある商品（「水色が好きな君へ」と同じ形）。
#[test]
fn booth_item_with_description_sections() {
    let (port, files) = serve();
    let base = format!("http://127.0.0.1:{port}");
    let json = r#"{"description":"マーダーミステリー『水色が好きな君へ』\n2人用(GM必須)のシナリオです。\n","name":"マーダーミステリー『水色が好きな君へ』",
        "is_adult":false,"images":[],"tags":[{"name":"マーダーミステリー"}],"url":"https://booth.pm/ja/items/4015766","shop":{"name":"ショップA"}}"#;
    let html = r#"<!DOCTYPE html><html><head><title>マーダーミステリー『水色が好きな君へ』 - BOOTH</title></head><body>
        <header><a>BOOTH</a></header><main>
        <h2>マーダーミステリー『水色が好きな君へ』</h2><a>まめぽよのひみつきち</a><h4>「ギフトとして贈る」とは</h4>
        <div><p>マーダーミステリー『水色が好きな君へ』<br>2人用(GM必須)のシナリオです。</p></div>
        <div><h2>▼あらすじ</h2><p>アスファルトに照り付ける、太陽。<br>夏休みの最初の日、二人は約束の場所へ向かった。</p></div>
        <div><h2>▼本作品について</h2><p>人数：2名+GM1人(進行役)<br>プレイ時間：2〜3時間<br>プレイ環境：オンライン推奨</p></div>
        <div><h2>▼配信について</h2><p>本作品は動画化・配信することができます。</p></div>
        <div><h2>▼更新履歴</h2><p>2022/8/13</p><p>概要にキャラクターの掲載</p></div></main>
        <footer><h3>BOOTHで「売りたい」</h3><p>ショップを開く</p></footer></body></html>"#;
    {
        let mut f = files.lock().unwrap();
        f.insert("/ja/items/4015766.json".into(), ("application/json", json.as_bytes().to_vec()));
        f.insert("/ja/items/4015766".into(), ("text/html; charset=utf-8", html.as_bytes().to_vec()));
    }
    let web = WebExtractor::with_fetchers(Http::new(), vec![Box::new(BoothFetcher { base })]);
    let r = web.extract("https://booth.pm/ja/items/4015766", &InfoExtractor::new(), &ThumbnailConfig::default()).unwrap();
    assert_eq!(r.info.title.as_ref().unwrap().value, "水色が好きな君へ");
    assert_eq!(r.title_systems, ["マーダーミステリー"]);
    assert_eq!(
        r.info.synopsis.as_ref().unwrap().value,
        "アスファルトに照り付ける、太陽。\n夏休みの最初の日、二人は約束の場所へ向かった。"
    );
    let p = &r.info.players.as_ref().unwrap().value;
    assert_eq!((p.min, p.max), (2, 2));
    let d = &r.info.duration.as_ref().unwrap().value;
    assert_eq!((d.min_hours, d.max_hours), (2, 3));
    assert_eq!(r.synopsis_candidates[0].label, "あらすじ");

    // 商品ページが読めなくても、JSON の情報だけで続ける
    files.lock().unwrap().remove("/ja/items/4015766");
    let r = web.extract("https://booth.pm/ja/items/4015766", &InfoExtractor::new(), &ThumbnailConfig::default()).unwrap();
    assert_eq!(r.info.title.as_ref().unwrap().value, "水色が好きな君へ");
    assert!(r.info.synopsis.is_none());
}

#[test]
fn generic_page_with_open_graph() {
    let (port, files) = serve();
    let mut files = files.lock().unwrap();
    files.insert("/img/cover.png".to_string(), ("image/png", png(300, 420)));
    let html = r#"<html><head><meta charset="utf-8"><title>作品ページ</title>
        <meta property="og:title" content="TRPGシナリオ『夜色の図書館』">
        <meta property="og:description" content="ある雨の夜、探索者たちは古い図書館に閉じ込められる。">
        <meta property="og:image" content="/img/cover.png"></head>
        <body><p>推奨人数：2～3人</p><p>プレイ時間：4～5時間</p></body></html>"#;
    files.insert("/works/1".to_string(), ("text/html; charset=utf-8", html.as_bytes().to_vec()));
    drop(files);
    let web = WebExtractor::new();
    let r = web
        .extract(&format!("http://127.0.0.1:{port}/works/1"), &InfoExtractor::new(), &ThumbnailConfig::default())
        .unwrap();
    assert_eq!(r.site, "generic");
    assert_eq!(r.info.title.as_ref().unwrap().value, "夜色の図書館");
    assert_eq!(r.info.synopsis.as_ref().unwrap().value, "ある雨の夜、探索者たちは古い図書館に閉じ込められる。");
    assert_eq!(r.synopsis_candidates[0].label, "ページの説明");
    assert_eq!(r.info.overview.as_ref().unwrap().value, "推奨人数：２～３人\nプレイ時間：４～５時間");
    assert!(r.image.is_some(), "{:?}", r.warnings);

    // 見つからないページ
    let e = web
        .extract(&format!("http://127.0.0.1:{port}/nothing"), &InfoExtractor::new(), &ThumbnailConfig::default())
        .unwrap_err();
    assert!(e.contains("404"), "{e}");
    assert!(web.extract("ftp://x", &InfoExtractor::new(), &ThumbnailConfig::default()).is_err());
}
