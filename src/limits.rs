//! 異常な入力から身を守るための上限値と、安全な読み込みの補助関数。
//!
//! Rust では「メモリ確保の失敗」と「スタックオーバーフロー」だけは回復できず、プロセスが即座に終了する。
//! そのため、入力データの値に応じてメモリを確保する箇所には必ず上限をかける。

use std::io::Read;

/// ZIP の中のファイル数の上限。TRPG の配布物は多くても数千件。
/// これを超える件数を申告する ZIP は、メモリを使い果たさせる細工とみなして開かない。
pub const MAX_ZIP_ENTRIES: u64 = 200_000;

/// フォルダを走査するときのファイル数の上限（ドライブ全体などを渡されても止まるように）。
pub const MAX_FOLDER_FILES: usize = 200_000;

/// 1件の読み込みサイズの上限の上限（設定でこれより大きな値を指定しても、ここで頭打ちにする）。
pub const MAX_READ_BYTES: u64 = 1 << 30; // 1 GiB

/// 読み込み前にまとめて確保するメモリの上限（申告サイズが嘘でも、確保しすぎないように）。
const MAX_CAPACITY_HINT: u64 = 16 << 20; // 16 MiB

/// 判定ルールのファイルの大きさの上限。
pub const MAX_RULES_FILE_BYTES: u64 = 1 << 20; // 1 MiB

/// 候補の処理（画像のデコードや PDF の描画）に使うスレッドのスタックサイズ。
/// 呼び出し元のスレッドのスタックが小さくても（Windows のメインスレッドは 1MB）溢れないようにする。
pub const WORKER_STACK_BYTES: usize = 16 << 20; // 16 MiB

/// `reader` から最大 `max_bytes` バイトを読む。超えたら `Err(読めたバイト数)`。
///
/// `size_hint` は申告サイズ（信用しない）。確保量は `MAX_CAPACITY_HINT` までに抑える。
pub fn read_limited(
    reader: impl Read,
    max_bytes: u64,
    size_hint: u64,
) -> std::io::Result<Result<Vec<u8>, u64>> {
    let max_bytes = max_bytes.min(MAX_READ_BYTES);
    let mut buf = Vec::with_capacity(size_hint.min(max_bytes).min(MAX_CAPACITY_HINT) as usize);
    reader
        .take(max_bytes.saturating_add(1))
        .read_to_end(&mut buf)?;
    if buf.len() as u64 > max_bytes {
        Ok(Err(buf.len() as u64))
    } else {
        Ok(Ok(buf))
    }
}

/// スタックを大きく取った専用スレッドで `f` を実行する。パニックはエラーにする。
///
/// 画像のデコードや PDF の解析など、入力によって深い再帰が起きうる処理に使う。
pub fn run_on_worker<T: Send>(f: impl FnOnce() -> Result<T, String> + Send) -> Result<T, String> {
    std::thread::scope(|scope| {
        let handle = std::thread::Builder::new()
            .name("cover-extractor-worker".into())
            .stack_size(WORKER_STACK_BYTES)
            .spawn_scoped(scope, f)
            .map_err(|e| format!("cannot start worker thread: {e}"))?;
        handle.join().unwrap_or_else(|_| Err("internal error while processing this entry".into()))
    })
}
