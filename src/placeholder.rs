//! 表紙が取れなかったときの「書籍風」プレースホルダー画像。
//!
//! 外部ファイルに依存しないよう、コードで描画する。

use image::{Rgb, RgbImage};

use crate::error::ThumbnailError;
use crate::thumbnail::encode_jpeg;

const BG: Rgb<u8> = Rgb([0x2b, 0x3a, 0x55]);
const SPINE: Rgb<u8> = Rgb([0x1f, 0x2a, 0x3e]);
const GOLD: Rgb<u8> = Rgb([0xc9, 0xa9, 0x61]);

/// 長辺 `long_edge` の縦長（A判比率 1:√2）プレースホルダーをJPEGで返す。
pub fn placeholder_jpeg(
    long_edge: u32,
    quality: u8,
) -> Result<(Vec<u8>, u32, u32), ThumbnailError> {
    let h = long_edge.max(64);
    let w = ((h as f64) / std::f64::consts::SQRT_2).round().max(45.0) as u32;
    let img = draw_book(w, h);
    Ok((encode_jpeg(&img, quality)?, w, h))
}

fn draw_book(w: u32, h: u32) -> RgbImage {
    let mut img = RgbImage::from_pixel(w, h, BG);
    let unit = (h / 60).max(1);

    // 背表紙（左端の濃い帯）
    fill(&mut img, 0, 0, (unit * 4).min(w), h, SPINE);

    // 金色の二重枠
    let inset = unit * 7;
    if w > inset * 2 && h > inset * 2 {
        stroke(
            &mut img,
            inset,
            inset,
            w - inset,
            h - inset,
            unit / 2 + 1,
            GOLD,
        );
        let inset2 = inset + unit * 2;
        if w > inset2 * 2 && h > inset2 * 2 {
            stroke(&mut img, inset2, inset2, w - inset2, h - inset2, 1, GOLD);
        }
    }

    // 中央のタイトル枠と、その下の飾り線
    let cx0 = w / 4;
    let cx1 = w - w / 4;
    let cy0 = h * 3 / 10;
    let cy1 = h * 9 / 20;
    if cx1 > cx0 && cy1 > cy0 {
        stroke(&mut img, cx0, cy0, cx1, cy1, unit / 2 + 1, GOLD);
    }
    let line_y = h * 11 / 20;
    let line_x0 = w * 3 / 8;
    let line_x1 = w * 5 / 8;
    if line_x1 > line_x0 && line_y < h {
        fill(
            &mut img,
            line_x0,
            line_y,
            line_x1,
            (line_y + unit / 2 + 1).min(h),
            GOLD,
        );
    }

    img
}

/// 矩形 [x0, x1) × [y0, y1) を塗る。
fn fill(img: &mut RgbImage, x0: u32, y0: u32, x1: u32, y1: u32, c: Rgb<u8>) {
    let (w, h) = img.dimensions();
    for y in y0.min(h)..y1.min(h) {
        for x in x0.min(w)..x1.min(w) {
            img.put_pixel(x, y, c);
        }
    }
}

/// 矩形の枠線を描く。
fn stroke(img: &mut RgbImage, x0: u32, y0: u32, x1: u32, y1: u32, t: u32, c: Rgb<u8>) {
    fill(img, x0, y0, x1, (y0 + t).min(y1), c);
    fill(img, x0, y1.saturating_sub(t).max(y0), x1, y1, c);
    fill(img, x0, y0, (x0 + t).min(x1), y1, c);
    fill(img, x1.saturating_sub(t).max(x0), y0, x1, y1, c);
}