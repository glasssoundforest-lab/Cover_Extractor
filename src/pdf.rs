use image::DynamicImage;
use crate::error::ThumbnailError;

#[cfg(feature = "pdf")]
pub fn render_first_page(data: Vec<u8>, long_edge: u32) -> Result<DynamicImage, ThumbnailError> {
    use hayro::hayro_interpret::InterpreterSettings;
    use hayro::hayro_syntax::Pdf;
    use hayro::vello_cpu::color::palette::css::WHITE;
    use hayro::{PixmapSettings, RenderCache, RenderSettings, render};
    use image::RgbaImage;

    let result = std::panic::catch_unwind(move || {
        let pdf = Pdf::new(data).map_err(|e| format!("cannot open PDF: {e:?}"))?;
        let pages = pdf.pages();
        if pages.is_empty() {
            return Err("PDF has no pages".into());
        }

        let mut best_pixmap = None;
        let mut max_color_variance = -1.0f32;

        // 先頭8ページから最もイラストらしいページを選択（1P目が白黒タイトル等の場合に対応）
        for (idx, page) in pages.iter().take(8).enumerate() {
            let (w, h) = page.render_dimensions();
            if !(w > 0.0 && h > 0.0) {
                continue;
            }

            let scale = (long_edge.min(u16::MAX as u32 - 1) as f32 + 0.5) / w.max(h);
            let pixmap = render(
                page,
                &RenderCache::new(),
                &InterpreterSettings::default(),
                &RenderSettings::default(),
                &PixmapSettings {
                    x_scale: scale,
                    y_scale: scale,
                    bg_color: WHITE,
                },
            );

            // 簡易色相分散判定（白紙やテキスト単色でなくカラー画像があるか）
            let data = pixmap.data_as_u8_slice();
            let mut colored_pixels = 0usize;
            for chunk in data.chunks_exact(4).step_by(8) {
                let r = chunk[0] as i32;
                let g = chunk[1] as i32;
                let b = chunk[2] as i32;
                if (r - g).abs() > 20 || (g - b).abs() > 20 || (b - r).abs() > 20 {
                    colored_pixels += 1;
                }
            }

            let score = (colored_pixels as f32) - (idx as f32 * 50.0);
            if score > max_color_variance || best_pixmap.is_none() {
                max_color_variance = score;
                best_pixmap = Some(pixmap);
            }
        }

        let pixmap = best_pixmap.ok_or("failed to render any page")?;
        let (pw, ph) = (pixmap.width() as u32, pixmap.height() as u32);
        let rgba = RgbaImage::from_raw(pw, ph, pixmap.data_as_u8_slice().to_vec())
            .ok_or("unexpected pixmap size")?;
        Ok::<_, String>(DynamicImage::ImageRgba8(rgba))
    });

    match result {
        Ok(Ok(img)) => Ok(img),
        Ok(Err(msg)) => Err(ThumbnailError::Pdf(msg)),
        Err(_) => Err(ThumbnailError::Pdf("PDF renderer panicked".into())),
    }
}

#[cfg(not(feature = "pdf"))]
pub fn render_first_page(_data: Vec<u8>, _long_edge: u32) -> Result<DynamicImage, ThumbnailError> {
    Err(ThumbnailError::Pdf(
        "PDF support is disabled (build with the `pdf` feature)".into(),
    ))
}