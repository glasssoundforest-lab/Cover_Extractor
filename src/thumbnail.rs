//! 画像デコード → 向き補正 → 縮小 → JPEGエンコードのパイプライン。

use std::io::Cursor;

use image::codecs::jpeg::JpegEncoder;
use image::metadata::Orientation;
use image::{DynamicImage, ImageDecoder, ImageReader, Limits, Rgb, RgbImage};

use crate::error::ThumbnailError;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ThumbnailConfig {
    pub max_long_edge: u32,
    pub jpeg_quality: u8,
    pub min_source_edge: u32,
    pub max_source_dimension: u32,
    pub max_decode_alloc: u64,
    pub background: [u8; 3],
}

impl Default for ThumbnailConfig {
    fn default() -> Self {
        Self {
            max_long_edge: 600,
            jpeg_quality: 85,
            min_source_edge: 150,
            max_source_dimension: 10_000,
            max_decode_alloc: 300 * 1024 * 1024,
            background: [255, 255, 255],
        }
    }
}

#[derive(Debug, Clone)]
pub struct Thumbnail {
    pub jpeg: Vec<u8>,
    pub width: u32,
    pub height: u32,
    pub source_width: u32,
    pub source_height: u32,
    pub dominant_ratio: f32,
}

pub fn probe_dimensions(bytes: &[u8]) -> Result<(u32, u32), ThumbnailError> {
    let reader = ImageReader::new(Cursor::new(bytes)).with_guessed_format()?;
    Ok(reader.into_dimensions()?)
}

pub fn make_thumbnail(bytes: &[u8], cfg: &ThumbnailConfig) -> Result<Thumbnail, ThumbnailError> {
    let mut reader = ImageReader::new(Cursor::new(bytes)).with_guessed_format()?;
    let mut limits = Limits::default();
    limits.max_image_width = Some(cfg.max_source_dimension);
    limits.max_image_height = Some(cfg.max_source_dimension);
    limits.max_alloc = Some(cfg.max_decode_alloc);
    reader.limits(limits);

    let mut decoder = reader.into_decoder()?;
    let (w, h) = decoder.dimensions();
    if w == 0 || h == 0 || w.min(h) < cfg.min_source_edge {
        return Err(ThumbnailError::TooSmall {
            width: w,
            height: h,
            min_edge: cfg.min_source_edge,
        });
    }

    let orientation = decoder.orientation().unwrap_or(Orientation::NoTransforms);
    let mut img = DynamicImage::from_decoder(decoder)?;
    img.apply_orientation(orientation);
    finish_thumbnail(img, cfg)
}

pub(crate) fn finish_thumbnail(
    mut img: DynamicImage,
    cfg: &ThumbnailConfig,
) -> Result<Thumbnail, ThumbnailError> {
    let (source_width, source_height) = (img.width(), img.height());

    let max = cfg.max_long_edge;
    if source_width.max(source_height) > max {
        img = img.thumbnail(max, max);
    }

    let rgb = flatten_to_rgb(&img, cfg.background);
    let jpeg = encode_jpeg(&rgb, cfg.jpeg_quality)?;
    let dominant_ratio = dominant_color_ratio(&rgb);

    Ok(Thumbnail {
        jpeg,
        width: rgb.width(),
        height: rgb.height(),
        source_width,
        source_height,
        dominant_ratio,
    })
}

pub fn dominant_color_ratio(img: &RgbImage) -> f32 {
    let total = (img.width() as u64 * img.height() as u64).max(1);
    let mut bins = vec![0u32; 16 * 16 * 16];
    for p in img.pixels() {
        let [r, g, b] = p.0;
        bins[((r as usize >> 4) << 8) | ((g as usize >> 4) << 4) | (b as usize >> 4)] += 1;
    }
    *bins.iter().max().unwrap_or(&0) as f32 / total as f32
}

fn flatten_to_rgb(img: &DynamicImage, bg: [u8; 3]) -> RgbImage {
    if !img.color().has_alpha() {
        return img.to_rgb8();
    }
    let rgba = img.to_rgba8();
    let mut out = RgbImage::new(rgba.width(), rgba.height());
    for (dst, src) in out.pixels_mut().zip(rgba.pixels()) {
        let a = src[3] as u32;
        let blend = |c: u8, b: u8| ((c as u32 * a + b as u32 * (255 - a) + 127) / 255) as u8;
        *dst = Rgb([
            blend(src[0], bg[0]),
            blend(src[1], bg[1]),
            blend(src[2], bg[2]),
        ]);
    }
    out
}

pub(crate) fn encode_jpeg(img: &RgbImage, quality: u8) -> Result<Vec<u8>, ThumbnailError> {
    let mut buf = Vec::new();
    JpegEncoder::new_with_quality(&mut buf, quality.clamp(1, 100)).encode_image(img)?;
    Ok(buf)
}