//! UIエフェクト・グラフィック生成モジュール (Rust GFX)
//!
//! Pillow に依存していた各種画像エフェクト・描画処理（木目テクスチャ、ドロップシャドウ、
//! ページめくり透視投影変形、本棚パーツ、クラシック洋書風カバー等）を
//! Rust 側で高速かつ独立して処理する。

use std::f32::consts::PI;
use image::{ImageBuffer, Rgba, RgbaImage};

/// 乱数生成器 (Xorshift64)
struct SimpleRng {
    state: u64,
}

impl SimpleRng {
    fn new(seed: u64) -> Self {
        let s = if seed == 0 { 0x853c49e6748fea9b } else { seed };
        Self { state: s }
    }

    fn next_u64(&mut self) -> u64 {
        self.state ^= self.state << 13;
        self.state ^= self.state >> 7;
        self.state ^= self.state << 17;
        self.state
    }

    fn next_f32(&mut self) -> f32 {
        (self.next_u64() & 0xFFFF_FFFF) as f32 / 4294967296.0
    }
}

/// 16進カラーコード (0xRRGGBB) から [r, g, b] を取得
#[inline]
pub fn hex_to_rgb(hex: u32) -> [u8; 3] {
    [
        ((hex >> 16) & 0xFF) as u8,
        ((hex >> 8) & 0xFF) as u8,
        (hex & 0xFF) as u8,
    ]
}

/// 2つのRGBカラーを線形補間 (t: 0.0 ~ 1.0)
#[inline]
fn lerp_rgb(c0: [u8; 3], c1: [u8; 3], t: f32) -> [u8; 3] {
    let t = t.clamp(0.0, 1.0);
    [
        (c0[0] as f32 + (c1[0] as f32 - c0[0] as f32) * t).round() as u8,
        (c0[1] as f32 + (c1[1] as f32 - c0[1] as f32) * t).round() as u8,
        (c0[2] as f32 + (c1[2] as f32 - c0[2] as f32) * t).round() as u8,
    ]
}

/// RgbaImage を PNG バイト列にエンコード
pub fn to_png_bytes(img: &RgbaImage) -> Result<Vec<u8>, String> {
    let mut buf = Vec::new();
    let encoder = image::codecs::png::PngEncoder::new(&mut buf);
    img.write_with_encoder(encoder)
        .map_err(|e| format!("PNG encoding error: {e}"))?;
    Ok(buf)
}

/// バイトバッファを C ABI 呼び出し元へポインタとして渡すためのヘルパー
pub fn export_bytes(bytes: Vec<u8>, out_len: *mut usize) -> *mut u8 {
    let mut boxed = bytes.into_boxed_slice();
    let ptr = boxed.as_mut_ptr();
    let len = boxed.len();
    std::mem::forget(boxed);
    if !out_len.is_null() {
        unsafe {
            *out_len = len;
        }
    }
    ptr
}

// ==============================================================================
// 1. プロシージャル木目テクスチャ生成
// ==============================================================================

/// プロシージャル木目テクスチャの生成
///
/// Python の wood_texture と同等のプロシージャルアルゴリズムを高速に実行。
pub fn generate_wood_texture(
    width: u32,
    height: u32,
    light_rgb: [u8; 3],
    dark_rgb: [u8; 3],
    vertical: bool,
    seed: u64,
    contrast: f32,
) -> RgbaImage {
    let w = width.max(1);
    let h = height.max(1);
    let (across, along) = if vertical { (w, h) } else { (h, w) };

    let mut rng = SimpleRng::new(seed);
    let phase = rng.next_f32() * 2.0 * PI;
    let wave_factor = 7.0 + rng.next_f32() * 2.0;

    // wave(x) の計算
    let mut wave = Vec::with_capacity(across as usize);
    for x in 0..across {
        let fx = x as f32;
        let v = 128.0 + 60.0 * (phase + fx / wave_factor).sin() * (fx / 53.0 + phase).sin();
        wave.push(v.clamp(0.0, 255.0));
    }

    // 粗いストリークノイズ (along方向は間引いて後で補間)
    let streak_rows = (along / 40).max(2) as usize;
    let mut streak_grid = vec![0.0f32; (across as usize) * streak_rows];
    for val in streak_grid.iter_mut() {
        *val = rng.next_f32() * 255.0;
    }

    // 細かいグレインノイズ (along方向は細かく間引く)
    let fine_rows = (along / 6).max(2) as usize;
    let mut fine_grid = vec![0.0f32; (across as usize) * fine_rows];
    for val in fine_grid.iter_mut() {
        *val = rng.next_f32() * 255.0;
    }

    // 1行補間ヘルパー
    let sample_grid = |grid: &[f32], rows: usize, x: usize, y: usize| -> f32 {
        if rows <= 1 {
            return grid[x];
        }
        let pos_y = (y as f32 / along as f32) * (rows - 1) as f32;
        let y0 = (pos_y.floor() as usize).min(rows - 1);
        let y1 = (y0 + 1).min(rows - 1);
        let dy = pos_y - y0 as f32;
        let v0 = grid[y0 * (across as usize) + x];
        let v1 = grid[y1 * (across as usize) + x];
        v0 + (v1 - v0) * dy
    };

    // グレースケール値のグリッドを生成
    let mut grays = vec![0.0f32; (across as usize) * (along as usize)];
    let mut min_val = f32::MAX;
    let mut max_val = f32::MIN;

    for y in 0..(along as usize) {
        for x in 0..(across as usize) {
            let s = sample_grid(&streak_grid, streak_rows, x, y);
            let f = sample_grid(&fine_grid, fine_rows, x, y);
            let w_val = wave[x];
            // gray = (s * w / 255 + f) / 1.6
            let mult = (s * w_val) / 255.0;
            let g = (mult + f) / 1.6;
            grays[y * (across as usize) + x] = g;
            if g < min_val {
                min_val = g;
            }
            if g > max_val {
                max_val = g;
            }
        }
    }

    // オートコントラスト (min/max 正規化) & contrast 補正
    let range = (max_val - min_val).max(1.0);
    let mut out_img = ImageBuffer::new(w, h);

    for y in 0..along {
        for x in 0..across {
            let g_raw = grays[(y as usize) * (across as usize) + (x as usize)];
            let norm = ((g_raw - min_val) / range) * 255.0;

            let final_g = if (contrast - 1.0).abs() > 0.001 {
                let v = 128.0 + (norm - 128.0) * contrast;
                v.clamp(0.0, 255.0)
            } else {
                norm.clamp(0.0, 255.0)
            };

            let t = final_g / 255.0;
            let [r, g, b] = lerp_rgb(dark_rgb, light_rgb, t);

            // vertical / horizontal 配置
            let (target_x, target_y) = if vertical {
                (x, y)
            } else {
                // 90度回転: (x, y) -> (y, across - 1 - x)
                (y, across - 1 - x)
            };

            if target_x < w && target_y < h {
                out_img.put_pixel(target_x, target_y, Rgba([r, g, b, 255]));
            }
        }
    }

    out_img
}

// ==============================================================================
// 2. 高速ガウシアンシャドウ生成
// ==============================================================================

/// 水平＋垂直セパレートガウシアンブラー (アルファチャンネルのみを処理)
fn gaussian_blur_alpha(alpha: &[u8], w: usize, h: usize, sigma: f32) -> Vec<u8> {
    if sigma <= 0.0 || w == 0 || h == 0 {
        return alpha.to_vec();
    }

    // ガウシアンカーネル生成
    let radius = (3.0 * sigma).ceil() as usize;
    let mut kernel = Vec::with_capacity(radius * 2 + 1);
    let two_sigma_sq = 2.0 * sigma * sigma;
    let mut sum = 0.0f32;

    for i in (-(radius as isize))..=(radius as isize) {
        let w_val = (-((i * i) as f32) / two_sigma_sq).exp();
        kernel.push(w_val);
        sum += w_val;
    }
    for k in kernel.iter_mut() {
        *k /= sum;
    }

    // 1. 水平ブラー
    let mut temp = vec![0.0f32; w * h];
    for y in 0..h {
        let row_offset = y * w;
        for x in 0..w {
            let mut acc = 0.0f32;
            for (ki, i) in (-(radius as isize)..=(radius as isize)).enumerate() {
                let sx = (x as isize + i).clamp(0, w as isize - 1) as usize;
                acc += (alpha[row_offset + sx] as f32) * kernel[ki];
            }
            temp[row_offset + x] = acc;
        }
    }

    // 2. 垂直ブラー
    let mut out = vec![0u8; w * h];
    for x in 0..w {
        for y in 0..h {
            let mut acc = 0.0f32;
            for (ki, i) in (-(radius as isize)..=(radius as isize)).enumerate() {
                let sy = (y as isize + i).clamp(0, h as isize - 1) as usize;
                acc += temp[sy * w + x] * kernel[ki];
            }
            out[y * w + x] = acc.round().clamp(0.0, 255.0) as u8;
        }
    }

    out
}

/// 本やカード用のドロップシャドウ生成
pub fn generate_shadow(
    width: u32,
    height: u32,
    pad: u32,
    sigma: f32,
    strength: f32,
    shadow_rgb: [u8; 3],
) -> RgbaImage {
    let total_w = width + pad * 2;
    let total_h = height + pad * 2;
    let mut alpha_plane = vec![0u8; (total_w as usize) * (total_h as usize)];

    let base_alpha = (255.0 * strength.clamp(0.0, 1.0)).round() as u8;

    // 中央に矩形マスクを配置
    for y in pad..(pad + height) {
        let row = (y as usize) * (total_w as usize);
        for x in pad..(pad + width) {
            alpha_plane[row + (x as usize)] = base_alpha;
        }
    }

    // ぼかし
    let blurred_alpha = gaussian_blur_alpha(&alpha_plane, total_w as usize, total_h as usize, sigma);

    // RgbaImage に変換
    let mut out = ImageBuffer::new(total_w, total_h);
    let [r, g, b] = shadow_rgb;
    for y in 0..total_h {
        let row = (y as usize) * (total_w as usize);
        for x in 0..total_w {
            let a = blurred_alpha[row + (x as usize)];
            out.put_pixel(x, y, Rgba([r, g, b, a]));
        }
    }

    out
}

// ==============================================================================
// 3. ページめくり透視投影変形 (Turning Page)
// ==============================================================================

/// 4頂点 dst から src への射影変換行列 (3x3) を計算 (ガウス消去法)
fn get_perspective_matrix(src: &[[f32; 2]; 4], dst: &[[f32; 2]; 4]) -> Option<[f32; 9]> {
    // 8x8 の連立方程式 A * h = b を解く
    let mut a = [[0.0f32; 9]; 8];
    for i in 0..4 {
        let x = dst[i][0];
        let y = dst[i][1];
        let u = src[i][0];
        let v = src[i][1];

        a[i * 2] = [x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y, u];
        a[i * 2 + 1] = [0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y, v];
    }

    for col in 0..8 {
        let mut piv = col;
        for r in (col + 1)..8 {
            if a[r][col].abs() > a[piv][col].abs() {
                piv = r;
            }
        }
        if a[piv][col].abs() < 1e-9 {
            return None;
        }
        a.swap(col, piv);

        let pivot = a[col][col];
        for r in 0..8 {
            if r != col {
                let factor = a[r][col] / pivot;
                for c in col..9 {
                    a[r][c] -= factor * a[col][c];
                }
            }
        }
    }

    let mut h = [0.0f32; 9];
    for i in 0..8 {
        h[i] = a[i][8] / a[i][i];
    }
    h[8] = 1.0;
    Some(h)
}

/// 凸四角形の内外判定 (外積の符号がすべて一致するか)
fn is_point_inside_quad(p: [f32; 2], quad: &[[f32; 2]; 4]) -> bool {
    let mut last_cross = 0.0f32;
    for i in 0..4 {
        let p0 = quad[i];
        let p1 = quad[(i + 1) % 4];
        let dx = p1[0] - p0[0];
        let dy = p1[1] - p0[1];
        let px = p[0] - p0[0];
        let py = p[1] - p0[1];
        let cross = dx * py - dy * px;
        if cross.abs() > 1e-5 {
            if last_cross == 0.0 {
                last_cross = cross;
            } else if (cross > 0.0) != (last_cross > 0.0) {
                return false;
            }
        }
    }
    true
}

/// バイリニア補間による画像サンプリング
fn sample_bilinear(img: &RgbaImage, u: f32, v: f32) -> Rgba<u8> {
    let w = img.width();
    let h = img.height();
    if w == 0 || h == 0 {
        return Rgba([0, 0, 0, 0]);
    }
    if u < 0.0 || u > (w - 1) as f32 || v < 0.0 || v > (h - 1) as f32 {
        return Rgba([0, 0, 0, 0]);
    }

    let x0 = (u.floor() as u32).min(w - 1);
    let y0 = (v.floor() as u32).min(h - 1);
    let x1 = (x0 + 1).min(w - 1);
    let y1 = (y0 + 1).min(h - 1);

    let dx = u - x0 as f32;
    let dy = v - y0 as f32;

    let p00 = img.get_pixel(x0, y0);
    let p10 = img.get_pixel(x1, y0);
    let p01 = img.get_pixel(x0, y1);
    let p11 = img.get_pixel(x1, y1);

    let mut out = [0u8; 4];
    for c in 0..4 {
        let v0 = (p00[c] as f32) * (1.0 - dx) + (p10[c] as f32) * dx;
        let v1 = (p01[c] as f32) * (1.0 - dx) + (p11[c] as f32) * dx;
        out[c] = (v0 * (1.0 - dy) + v1 * dy).round().clamp(0.0, 255.0) as u8;
    }
    Rgba(out)
}

/// ページめくりアニメーションの変形レンダリング
pub fn turning_page_render(
    input_bytes: &[u8],
    width: u32,
    height: u32,
    spine_x_is_left: bool,
    lift: f32,
    darkness: f32,
) -> Result<(RgbaImage, u32), String> {
    let src_img = image::load_from_memory(input_bytes)
        .map_err(|e| format!("Failed to decode input image: {e}"))?
        .to_rgba8();

    let w0 = src_img.width() as f32;
    let h0 = src_img.height() as f32;
    let out_w = width.max(1);
    let grow = ((height as f32) * lift).round() as u32;
    let total_h = height + 2 * grow;

    let (g_f, w_f, tot_h_f, h_f) = (grow as f32, out_w as f32, total_h as f32, height as f32);

    let dst: [[f32; 2]; 4] = if spine_x_is_left {
        [[0.0, g_f], [w_f, 0.0], [w_f, tot_h_f], [0.0, g_f + h_f]]
    } else {
        [[0.0, 0.0], [w_f, g_f], [w_f, g_f + h_f], [0.0, tot_h_f]]
    };

    let src: [[f32; 2]; 4] = [[0.0, 0.0], [w0, 0.0], [w0, h0], [0.0, h0]];

    let h_mat = match get_perspective_matrix(&src, &dst) {
        Some(m) => m,
        None => return Ok((ImageBuffer::new(out_w, total_h), grow)),
    };

    let mut out_img = ImageBuffer::new(out_w, total_h);
    let dark_alpha = (255.0 * darkness.clamp(0.0, 1.0)).round() as u8;

    for y in 0..total_h {
        let py = y as f32;
        for x in 0..out_w {
            let px = x as f32;
            if !is_point_inside_quad([px, py], &dst) {
                continue;
            }

            // 射影変換 (u, v) = H * (x, y, 1)
            let denom = h_mat[6] * px + h_mat[7] * py + h_mat[8];
            if denom.abs() < 1e-9 {
                continue;
            }
            let u = (h_mat[0] * px + h_mat[1] * py + h_mat[2]) / denom;
            let v = (h_mat[3] * px + h_mat[4] * py + h_mat[5]) / denom;

            let mut pixel = sample_bilinear(&src_img, u, v);

            // darkness が指定されていれば暗色 (10, 6, 3) とブレンド
            if dark_alpha > 0 && pixel[3] > 0 {
                let da = dark_alpha as f32 / 255.0;
                pixel[0] = ((pixel[0] as f32) * (1.0 - da) + 10.0 * da).round() as u8;
                pixel[1] = ((pixel[1] as f32) * (1.0 - da) + 6.0 * da).round() as u8;
                pixel[2] = ((pixel[2] as f32) * (1.0 - da) + 3.0 * da).round() as u8;
            }

            out_img.put_pixel(x, y, pixel);
        }
    }

    Ok((out_img, grow))
}

// ==============================================================================
// 4. 本棚パーツ (Bay / Crown) 生成
// ==============================================================================

pub const BAY_BOARD: u32 = 40;
pub const BAY_SIDE: u32 = 26;
pub const CROWN_H: u32 = 30;

/// 水平ライン描画
fn draw_horizontal_line(img: &mut RgbaImage, x0: u32, x1: u32, y: u32, color: Rgba<u8>) {
    if y >= img.height() {
        return;
    }
    let w = img.width();
    let start = x0.min(w);
    let end = x1.min(w);
    for x in start..end {
        img.put_pixel(x, y, color);
    }
}

/// 垂直ライン描画
fn draw_vertical_line(img: &mut RgbaImage, x: u32, y0: u32, y1: u32, color: Rgba<u8>) {
    if x >= img.width() {
        return;
    }
    let h = img.height();
    let start = y0.min(h);
    let end = y1.min(h);
    for y in start..end {
        img.put_pixel(x, y, color);
    }
}

/// アルファ合成 (overlay を base 上に位置 (ox, oy) で重ねる)
pub fn alpha_blend(base: &mut RgbaImage, overlay: &RgbaImage, ox: i32, oy: i32) {
    let bw = base.width() as i32;
    let bh = base.height() as i32;
    let ow = overlay.width() as i32;
    let oh = overlay.height() as i32;

    for sy in 0..oh {
        let ty = oy + sy;
        if ty < 0 || ty >= bh {
            continue;
        }
        for sx in 0..ow {
            let tx = ox + sx;
            if tx < 0 || tx >= bw {
                continue;
            }

            let sp = overlay.get_pixel(sx as u32, sy as u32);
            let sa = sp[3] as f32 / 255.0;
            if sa <= 0.0 {
                continue;
            }

            let bp = base.get_pixel_mut(tx as u32, ty as u32);
            let ba = bp[3] as f32 / 255.0;

            let out_a = sa + ba * (1.0 - sa);
            if out_a > 0.0 {
                let r = ((sp[0] as f32 * sa + bp[0] as f32 * ba * (1.0 - sa)) / out_a).round() as u8;
                let g = ((sp[1] as f32 * sa + bp[1] as f32 * ba * (1.0 - sa)) / out_a).round() as u8;
                let b = ((sp[2] as f32 * sa + bp[2] as f32 * ba * (1.0 - sa)) / out_a).round() as u8;
                let a = (out_a * 255.0).round() as u8;
                *bp = Rgba([r, g, b, a]);
            }
        }
    }
}

/// 本棚の1区画背景 (bay_photo) の完全生成
pub fn render_bay(width: u32, height: u32, seed: u64) -> RgbaImage {
    // 1. 背面ベース木目
    let mut im = generate_wood_texture(
        width,
        height,
        hex_to_rgb(0x3d2717),
        hex_to_rgb(0x1f130a),
        true,
        seed + 3,
        0.7,
    );

    // 2. 陰影オーバーレイ (上部と両サイドのグラデーション)
    let mut shade_img = ImageBuffer::new(width, height);
    for y in 0..height {
        for x in 0..width {
            let mut alpha = 30.0f32; // 基本の暗さ
            if y < 46 {
                let top_val = 190.0 * (1.0 - y as f32 / 46.0).powf(1.6);
                alpha = alpha.max(top_val);
            }
            if x >= BAY_SIDE && x < (BAY_SIDE + 40) {
                let left_val = 150.0 * (1.0 - (x - BAY_SIDE) as f32 / 40.0).powf(2.0);
                alpha = alpha.max(left_val);
            }
            if x >= (width.saturating_sub(BAY_SIDE + 40)) && x < (width.saturating_sub(BAY_SIDE)) {
                let right_offset = (width - BAY_SIDE - 1).saturating_sub(x);
                let right_val = 150.0 * (1.0 - right_offset as f32 / 40.0).powf(2.0);
                alpha = alpha.max(right_val);
            }
            let a = alpha.round().clamp(0.0, 255.0) as u8;
            shade_img.put_pixel(x, y, Rgba([8, 4, 2, a]));
        }
    }
    alpha_blend(&mut im, &shade_img, 0, 0);

    // 3. 左右の柱 (BAY_SIDE)
    for &x0 in &[0, width.saturating_sub(BAY_SIDE)] {
        let mut post = generate_wood_texture(
            BAY_SIDE,
            height,
            hex_to_rgb(0x6a4527),
            hex_to_rgb(0x3a2413),
            true,
            seed + (x0 as u64) + 11,
            0.9,
        );
        draw_vertical_line(&mut post, 1, 0, height, Rgba([0x8a, 0x60, 0x3a, 255]));
        if BAY_SIDE >= 2 {
            draw_vertical_line(&mut post, BAY_SIDE - 2, 0, height, Rgba([0x24, 0x15, 0x0a, 255]));
        }
        alpha_blend(&mut im, &post, x0 as i32, 0);
    }

    // 4. 棚板の上面
    let top = height.saturating_sub(BAY_BOARD);
    let top_face_w = (width.saturating_sub(2 * BAY_SIDE) + 8).max(1);
    let top_face = generate_wood_texture(
        top_face_w,
        8,
        hex_to_rgb(0x7d5431),
        hex_to_rgb(0x5a391f),
        false,
        seed + 5,
        1.0,
    );
    alpha_blend(&mut im, &top_face, (BAY_SIDE as i32) - 4, top as i32);

    // 5. 棚板の手前正面
    let front_w = (width.saturating_sub(2)).max(1);
    let front_h = (BAY_BOARD.saturating_sub(8)).max(1);
    let mut front = generate_wood_texture(
        front_w,
        front_h,
        hex_to_rgb(0x6e4728),
        hex_to_rgb(0x3f2714),
        false,
        seed + 7,
        1.1,
    );
    draw_horizontal_line(&mut front, 0, width, 0, Rgba([0x9a, 0x6c, 0x42, 255]));
    draw_horizontal_line(&mut front, 0, width, 1, Rgba([0x87, 0x60, 0x3b, 255]));
    if front_h >= 2 {
        draw_horizontal_line(&mut front, 0, width, front_h - 1, Rgba([0x1c, 0x10, 0x07, 255]));
    }
    alpha_blend(&mut im, &front, 1, (top + 8) as i32);

    im
}

/// 本棚の上部飾り板 (crown_photo) の完全生成
pub fn render_crown(width: u32) -> RgbaImage {
    let h = CROWN_H;
    let mut im = generate_wood_texture(
        width,
        h,
        hex_to_rgb(0x7a5030),
        hex_to_rgb(0x402714),
        false,
        21,
        1.0,
    );
    draw_horizontal_line(&mut im, 0, width, 0, Rgba([0xa3, 0x75, 0x48, 255]));
    draw_horizontal_line(&mut im, 0, width, 9, Rgba([0x2a, 0x18, 0x09, 255]));
    draw_horizontal_line(&mut im, 0, width, 10, Rgba([0x8f, 0x65, 0x3d, 255]));
    if h >= 6 {
        draw_horizontal_line(&mut im, 0, width, h - 6, Rgba([0x2a, 0x18, 0x09, 255]));
        draw_horizontal_line(&mut im, 0, width, h - 5, Rgba([0x8f, 0x65, 0x3d, 255]));
    }
    draw_horizontal_line(&mut im, 0, width, h - 1, Rgba([0x1a, 0x0f, 0x06, 255]));
    im
}

// ==============================================================================
// 5. クラシックカバー & 表紙装丁エフェクト (Book / Cover)
// ==============================================================================

pub const CLOTH_PALETTE: [(&str, &str); 6] = [
    ("#5a1f22", "#d4b06a"),
    ("#1f3a2c", "#d9bf7a"),
    ("#1e2a4a", "#cfb071"),
    ("#4a3320", "#e0c48a"),
    ("#3b1e3a", "#d6b77a"),
    ("#2c3a3e", "#d2b678"),
];

/// 16進カラー文字列 "#RRGGBB" を [u8; 3] に変換
fn parse_hex_color(hex_str: &str) -> [u8; 3] {
    let s = hex_str.trim_start_matches('#');
    if s.len() >= 6 {
        let r = u8::from_str_radix(&s[0..2], 16).unwrap_or(0);
        let g = u8::from_str_radix(&s[2..4], 16).unwrap_or(0);
        let b = u8::from_str_radix(&s[4..6], 16).unwrap_or(0);
        [r, g, b]
    } else {
        [0, 0, 0]
    }
}

/// 背表紙・本の綴じ目シャドウ (_binding) を付与
pub fn apply_book_binding(im: &mut RgbaImage) {
    let w = im.width();
    let h = im.height();
    let band = (w as f32 * 0.06).round().max(4.0) as u32;

    for y in 0..h {
        // 1. 左端のグラデーション陰影
        for i in 0..band.min(w) {
            let factor = 1.0 - (i as f32 / band as f32);
            let shadow_a = (120.0 * factor).round() as u8;
            let p = im.get_pixel_mut(i, y);
            let sa = shadow_a as f32 / 255.0;
            p[0] = ((p[0] as f32) * (1.0 - sa)).round() as u8;
            p[1] = ((p[1] as f32) * (1.0 - sa)).round() as u8;
            p[2] = ((p[2] as f32) * (1.0 - sa)).round() as u8;
        }

        // 2. ハイライト線と溝シャドウ線
        if band < w {
            let p = im.get_pixel_mut(band, y);
            p[0] = p[0].saturating_add(34);
            p[1] = p[1].saturating_add(34);
            p[2] = p[2].saturating_add(34);
        }
        if (band + 1) < w {
            let p = im.get_pixel_mut(band + 1, y);
            p[0] = p[0].saturating_sub(40);
            p[1] = p[1].saturating_sub(40);
            p[2] = p[2].saturating_sub(40);
        }

        // 3. 上部のハイライト (薄い温かみのある光)
        if y < h / 3 {
            let factor = 1.0 - (y as f32 / (h as f32 / 3.0));
            let hl_a = (20.0 * factor).round() as u8;
            let ha = hl_a as f32 / 255.0;
            for x in 0..w {
                let p = im.get_pixel_mut(x, y);
                p[0] = ((p[0] as f32) * (1.0 - ha) + 255.0 * ha).round() as u8;
                p[1] = ((p[1] as f32) * (1.0 - ha) + 236.0 * ha).round() as u8;
                p[2] = ((p[2] as f32) * (1.0 - ha) + 200.0 * ha).round() as u8;
            }
        }
    }
}

/// 角丸マスクとエッジラインの適用
pub fn apply_rounded_corners(im: &mut RgbaImage, radius: u32) {
    let w = im.width();
    let h = im.height();
    let r = radius as f32;

    for y in 0..h {
        for x in 0..w {
            let fx = x as f32;
            let fy = y as f32;

            // 4隅の判定
            let in_corner = (fx < r && fy < r)
                || (fx >= (w as f32 - r) && fy < r)
                || (fx < r && fy >= (h as f32 - r))
                || (fx >= (w as f32 - r) && fy >= (h as f32 - r));

            if in_corner {
                let cx = if fx < r { r } else { w as f32 - r };
                let cy = if fy < r { r } else { h as f32 - r };
                let dist = ((fx - cx).powi(2) + (fy - cy).powi(2)).sqrt();
                if dist > r {
                    im.put_pixel(x, y, Rgba([0, 0, 0, 0]));
                } else if dist > (r - 1.0) {
                    // アンチエイリアス
                    let alpha = (r - dist).clamp(0.0, 1.0);
                    let p = im.get_pixel_mut(x, y);
                    p[3] = ((p[3] as f32) * alpha).round() as u8;
                }
            }
        }
    }
}

/// 表紙画像のアスペクト比フィットリサイズ
pub fn fit_cover_image(src: &RgbaImage, target_w: u32, target_h: u32) -> RgbaImage {
    let sw = src.width() as f32;
    let sh = src.height() as f32;
    let tw = target_w as f32;
    let th = target_h as f32;

    let scale = (tw / sw).max(th / sh);
    let scaled_w = (sw * scale).round() as u32;
    let scaled_h = (sh * scale).round() as u32;

    let resized = image::imageops::resize(
        src,
        scaled_w,
        scaled_h,
        image::imageops::FilterType::Lanczos3,
    );

    // centering: (0.5, 0.3) で切り抜き
    let crop_x = (((scaled_w as f32 - tw) * 0.5).round() as u32).min(scaled_w.saturating_sub(target_w));
    let crop_y = (((scaled_h as f32 - th) * 0.3).round() as u32).min(scaled_h.saturating_sub(target_h));

    image::imageops::crop_imm(&resized, crop_x, crop_y, target_w, target_h).to_image()
}

/// クラシック洋書風カバーの幾何学模様と布地生成
pub fn render_classic_cover_base(
    width: u32,
    height: u32,
    seed: u64,
) -> (RgbaImage, [u8; 3]) {
    let idx = (seed as usize) % CLOTH_PALETTE.len();
    let (cloth_hex, gold_hex) = CLOTH_PALETTE[idx];
    let cloth_rgb = parse_hex_color(cloth_hex);
    let gold_rgb = parse_hex_color(gold_hex);

    let mut im = ImageBuffer::new(width, height);
    for p in im.pixels_mut() {
        *p = Rgba([cloth_rgb[0], cloth_rgb[1], cloth_rgb[2], 255]);
    }

    // グレインノイズ
    let mut rng = SimpleRng::new(seed);
    for y in 0..height {
        for x in 0..width {
            let n = rng.next_f32() * 255.0;
            if n > 110.0 {
                let alpha = (((n - 110.0) / 2.0).min(70.0) as u8) as f32 / 255.0;
                let p = im.get_pixel_mut(x, y);
                p[0] = ((p[0] as f32) * (1.0 - alpha)).round() as u8;
                p[1] = ((p[1] as f32) * (1.0 - alpha)).round() as u8;
                p[2] = ((p[2] as f32) * (1.0 - alpha)).round() as u8;
            }
        }
    }

    // 金箔枠・オーナメントの描画
    let k = 2;
    let kw = width * k;
    let kh = height * k;
    let mut gold_layer = ImageBuffer::new(kw, kh);

    let lw = (k as f32).max((width * k) as f32 / 110.0).round() as u32;
    let m1 = (kw as f32 * 0.09).round() as u32;
    let m2 = (kw as f32 * 0.13).round() as u32;

    let gold_color = Rgba([gold_rgb[0], gold_rgb[1], gold_rgb[2], 235]);

    // 外枠と内枠
    let draw_rect_outline = |img: &mut RgbaImage, x0: u32, y0: u32, x1: u32, y1: u32, w: u32, col: Rgba<u8>| {
        for t in 0..w {
            draw_horizontal_line(img, x0 + t, x1.saturating_sub(t), y0 + t, col);
            draw_horizontal_line(img, x0 + t, x1.saturating_sub(t), (y1 - 1).saturating_sub(t), col);
            draw_vertical_line(img, x0 + t, y0 + t, y1.saturating_sub(t), col);
            draw_vertical_line(img, (x1 - 1).saturating_sub(t), y0 + t, y1.saturating_sub(t), col);
        }
    };

    draw_rect_outline(&mut gold_layer, m1, m1, kw - m1, kh - m1, lw, gold_color);
    draw_rect_outline(&mut gold_layer, m2, m2, kw - m2, kh - m2, (lw / 2).max(1), gold_color);

    // 縮小して合成
    let gold_resized = image::imageops::resize(
        &gold_layer,
        width,
        height,
        image::imageops::FilterType::Lanczos3,
    );
    alpha_blend(&mut im, &gold_resized, 0, 0);

    (im, gold_rgb)
}

/// 完全な本アイコン (book_photo) のレンダリング
pub fn render_book_cover(
    thumb_bytes: Option<&[u8]>,
    width: u32,
    height: u32,
    seed: u64,
    binding: bool,
    radius: u32,
) -> RgbaImage {
    let mut cover = if let Some(bytes) = thumb_bytes {
        if let Ok(dyn_img) = image::load_from_memory(bytes) {
            fit_cover_image(&dyn_img.to_rgba8(), width, height)
        } else {
            render_classic_cover_base(width, height, seed).0
        }
    } else {
        render_classic_cover_base(width, height, seed).0
    };

    if binding {
        apply_book_binding(&mut cover);
    }
    if radius > 0 {
        apply_rounded_corners(&mut cover, radius);
    }

    cover
}

// ==============================================================================
// 6. UIパーツ (IndexCard, Plate, Ribbon, Pill, Glow, Page, Icon 等)
// ==============================================================================

/// 図書カード風画像 (index_card_photo)
pub fn render_index_card(w: u32, h: u32, paper_rgb: [u8; 3]) -> RgbaImage {
    let pad = 6;

    // 1. 影
    let mut shadow = generate_shadow(w, h, pad, 4.0, 0.6, [0, 0, 0]);

    // 2. カード本文
    let mut card = ImageBuffer::new(w, h);
    for p in card.pixels_mut() {
        *p = Rgba([paper_rgb[0], paper_rgb[1], paper_rgb[2], 255]);
    }

    // 水平罫線 (水色・赤)
    let line_blue = Rgba([0xb9, 0xc4, 0xcf, 255]);
    let line_red = Rgba([0xb9, 0x52, 0x4a, 255]);

    let mut y = 54;
    while y < h {
        draw_horizontal_line(&mut card, 14, w.saturating_sub(14), y, line_blue);
        y += 19;
    }
    draw_horizontal_line(&mut card, 14, w.saturating_sub(14), 44, line_red);

    apply_rounded_corners(&mut card, 4);
    alpha_blend(&mut shadow, &card, pad as i32, pad as i32);

    shadow
}

/// ピル型画像 (pill_photo)
pub fn render_pill(
    w: u32,
    h: u32,
    fill: Option<[u8; 3]>,
    outline: [u8; 3],
    glow: Option<[u8; 3]>,
) -> RgbaImage {
    let g = if glow.is_some() { 6 } else { 1 };
    let total_w = w + 2 * g;
    let total_h = h + 2 * g;
    let mut im = ImageBuffer::new(total_w, total_h);

    if let Some(gc) = glow {
        let gl_shadow = generate_shadow(w, h, g, 3.0, 0.8, gc);
        alpha_blend(&mut im, &gl_shadow, 0, 0);
    }

    let radius = h / 2;
    let mut pill = ImageBuffer::new(w, h);
    if let Some(fc) = fill {
        for p in pill.pixels_mut() {
            *p = Rgba([fc[0], fc[1], fc[2], 255]);
        }
    }
    apply_rounded_corners(&mut pill, radius);

    // 外枠
    let out_color = Rgba([outline[0], outline[1], outline[2], 255]);
    draw_horizontal_line(&mut pill, radius, w.saturating_sub(radius), 0, out_color);
    draw_horizontal_line(&mut pill, radius, w.saturating_sub(radius), h.saturating_sub(1), out_color);

    alpha_blend(&mut im, &pill, g as i32, g as i32);
    im
}

/// ネームプレート (plate_photo)
pub fn render_plate(w: u32, h: u32) -> RgbaImage {
    let mut im = ImageBuffer::new(w, h);
    for p in im.pixels_mut() {
        *p = Rgba([0xb0, 0x8a, 0x3e, 255]); // 外枠の真鍮ゴールド
    }
    if w >= 4 && h >= 4 {
        for y in 2..(h - 2) {
            for x in 2..(w - 2) {
                im.put_pixel(x, y, Rgba([0xef, 0xe3, 0xc4, 255])); // 内枠クリーム
            }
        }
    }
    apply_rounded_corners(&mut im, 2);
    im
}

/// しおりリボン (ribbon_photo)
pub fn render_ribbon(w: u32, h: u32, color: [u8; 3]) -> RgbaImage {
    let mut im = ImageBuffer::new(w, h);
    let notch = (h as f32 * 0.82).round() as u32;
    let mid_x = w / 2;
    let c = Rgba([color[0], color[1], color[2], 255]);

    for y in 0..h {
        for x in 0..w {
            if y < notch {
                im.put_pixel(x, y, c);
            } else {
                // V字の切り欠き
                let dy = y - notch;
                let max_dy = h - notch;
                let dx = (x as i32 - mid_x as i32).abs() as u32;
                if dx as f32 / mid_x as f32 > (dy as f32 / max_dy as f32) {
                    im.put_pixel(x, y, c);
                }
            }
        }
    }
    im
}

/// 本の見開きページ (page_image)
pub fn render_page(w: u32, h: u32, side_is_left: bool, paper_rgb: [u8; 3]) -> RgbaImage {
    let mut im = ImageBuffer::new(w, h);
    for p in im.pixels_mut() {
        *p = Rgba([paper_rgb[0], paper_rgb[1], paper_rgb[2], 255]);
    }
    let band = (w as f32 * 0.12).round() as u32;
    for i in 0..band.min(w) {
        let alpha = (95.0 * (1.0 - i as f32 / band as f32).powi(2)).round() as u8;
        let x = if side_is_left { w - 1 - i } else { i };
        let sa = alpha as f32 / 255.0;
        for y in 0..h {
            let p = im.get_pixel_mut(x, y);
            p[0] = ((p[0] as f32) * (1.0 - sa) + 60.0 * sa).round() as u8;
            p[1] = ((p[1] as f32) * (1.0 - sa) + 40.0 * sa).round() as u8;
            p[2] = ((p[2] as f32) * (1.0 - sa) + 15.0 * sa).round() as u8;
        }
    }
    im
}

// ==============================================================================
// 7. C ABI (FFI) エクスポート関数群
// ==============================================================================

/// バッファ解放
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_free_buffer(ptr: *mut u8, len: usize) {
    if !ptr.is_null() && len > 0 {
        unsafe {
            let _ = Box::from_raw(std::slice::from_raw_parts_mut(ptr, len));
        }
    }
}

/// 木目テクスチャ生成
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_generate_wood_texture(
    width: u32,
    height: u32,
    seed: u32,
    contrast: f32,
    out_len: *mut usize,
) -> *mut u8 {
    let img = generate_wood_texture(
        width,
        height,
        hex_to_rgb(0x3d2717),
        hex_to_rgb(0x1f130a),
        true,
        seed as u64,
        contrast,
    );
    match to_png_bytes(&img) {
        Ok(bytes) => export_bytes(bytes, out_len),
        Err(_) => std::ptr::null_mut(),
    }
}

/// シャドウ生成
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_generate_shadow(
    width: u32,
    height: u32,
    pad: u32,
    sigma: f32,
    strength: f32,
    out_len: *mut usize,
) -> *mut u8 {
    let img = generate_shadow(width, height, pad, sigma, strength, [0, 0, 0]);
    match to_png_bytes(&img) {
        Ok(bytes) => export_bytes(bytes, out_len),
        Err(_) => std::ptr::null_mut(),
    }
}

/// ページめくり透視投影変形
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_turning_page(
    input_ptr: *const u8,
    input_len: usize,
    width: u32,
    height: u32,
    spine_is_left: bool,
    lift: f32,
    out_grow: *mut u32,
    out_len: *mut usize,
) -> *mut u8 {
    if input_ptr.is_null() || input_len == 0 {
        return std::ptr::null_mut();
    }
    let input_bytes = unsafe { std::slice::from_raw_parts(input_ptr, input_len) };
    match turning_page_render(input_bytes, width, height, spine_is_left, lift, 0.0) {
        Ok((img, grow)) => {
            if !out_grow.is_null() {
                unsafe {
                    *out_grow = grow;
                }
            }
            match to_png_bytes(&img) {
                Ok(bytes) => export_bytes(bytes, out_len),
                Err(_) => std::ptr::null_mut(),
            }
        }
        Err(_) => std::ptr::null_mut(),
    }
}

/// 本棚の区画背景 (bay)
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_generate_bay(
    width: u32,
    height: u32,
    seed: u32,
    out_len: *mut usize,
) -> *mut u8 {
    let img = render_bay(width, height, seed as u64);
    match to_png_bytes(&img) {
        Ok(bytes) => export_bytes(bytes, out_len),
        Err(_) => std::ptr::null_mut(),
    }
}

/// 本棚の上部飾り板 (crown)
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_generate_crown(
    width: u32,
    out_len: *mut usize,
) -> *mut u8 {
    let img = render_crown(width);
    match to_png_bytes(&img) {
        Ok(bytes) => export_bytes(bytes, out_len),
        Err(_) => std::ptr::null_mut(),
    }
}

/// 本アイコン (book_cover)
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_generate_book_cover(
    thumb_ptr: *const u8,
    thumb_len: usize,
    width: u32,
    height: u32,
    seed: u64,
    binding: bool,
    radius: u32,
    out_len: *mut usize,
) -> *mut u8 {
    let thumb_opt = if !thumb_ptr.is_null() && thumb_len > 0 {
        Some(unsafe { std::slice::from_raw_parts(thumb_ptr, thumb_len) })
    } else {
        None
    };
    let img = render_book_cover(thumb_opt, width, height, seed, binding, radius);
    match to_png_bytes(&img) {
        Ok(bytes) => export_bytes(bytes, out_len),
        Err(_) => std::ptr::null_mut(),
    }
}

/// 図書カード (index_card)
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_generate_index_card(
    width: u32,
    height: u32,
    paper_rgb_hex: u32,
    out_len: *mut usize,
) -> *mut u8 {
    let img = render_index_card(width, height, hex_to_rgb(paper_rgb_hex));
    match to_png_bytes(&img) {
        Ok(bytes) => export_bytes(bytes, out_len),
        Err(_) => std::ptr::null_mut(),
    }
}

/// ピル (pill)
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_generate_pill(
    width: u32,
    height: u32,
    fill_hex: u32,
    has_fill: bool,
    outline_hex: u32,
    glow_hex: u32,
    has_glow: bool,
    out_len: *mut usize,
) -> *mut u8 {
    let fill = if has_fill { Some(hex_to_rgb(fill_hex)) } else { None };
    let outline = hex_to_rgb(outline_hex);
    let glow = if has_glow { Some(hex_to_rgb(glow_hex)) } else { None };

    let img = render_pill(width, height, fill, outline, glow);
    match to_png_bytes(&img) {
        Ok(bytes) => export_bytes(bytes, out_len),
        Err(_) => std::ptr::null_mut(),
    }
}

/// ネームプレート (plate)
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_generate_plate(
    width: u32,
    height: u32,
    out_len: *mut usize,
) -> *mut u8 {
    let img = render_plate(width, height);
    match to_png_bytes(&img) {
        Ok(bytes) => export_bytes(bytes, out_len),
        Err(_) => std::ptr::null_mut(),
    }
}

/// しおりリボン (ribbon)
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_generate_ribbon(
    width: u32,
    height: u32,
    color_hex: u32,
    out_len: *mut usize,
) -> *mut u8 {
    let img = render_ribbon(width, height, hex_to_rgb(color_hex));
    match to_png_bytes(&img) {
        Ok(bytes) => export_bytes(bytes, out_len),
        Err(_) => std::ptr::null_mut(),
    }
}

/// 見開きページ (page)
#[unsafe(no_mangle)]
pub unsafe extern "C" fn gfx_generate_page(
    width: u32,
    height: u32,
    side_is_left: bool,
    paper_rgb_hex: u32,
    out_len: *mut usize,
) -> *mut u8 {
    let img = render_page(width, height, side_is_left, hex_to_rgb(paper_rgb_hex));
    match to_png_bytes(&img) {
        Ok(bytes) => export_bytes(bytes, out_len),
        Err(_) => std::ptr::null_mut(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_wood_texture() {
        let img = generate_wood_texture(100, 100, [100, 80, 50], [30, 20, 10], true, 42, 1.0);
        assert_eq!(img.width(), 100);
        assert_eq!(img.height(), 100);
        let png = to_png_bytes(&img).unwrap();
        assert!(!png.is_empty());
    }

    #[test]
    fn test_shadow() {
        let img = generate_shadow(50, 50, 10, 5.0, 0.7, [0, 0, 0]);
        assert_eq!(img.width(), 70);
        assert_eq!(img.height(), 70);
        let png = to_png_bytes(&img).unwrap();
        assert!(!png.is_empty());
    }

    #[test]
    fn test_shelf_parts() {
        let bay = render_bay(200, 150, 1);
        assert_eq!(bay.width(), 200);
        assert_eq!(bay.height(), 150);

        let crown = render_crown(200);
        assert_eq!(crown.width(), 200);
        assert_eq!(crown.height(), CROWN_H);
    }

    #[test]
    fn test_book_and_card() {
        let book = render_book_cover(None, 80, 120, 1234, true, 3);
        assert_eq!(book.width(), 80);
        assert_eq!(book.height(), 120);

        let card = render_index_card(120, 80, [240, 235, 220]);
        assert_eq!(card.width(), 120 + 12);
        assert_eq!(card.height(), 80 + 12);
    }
}
