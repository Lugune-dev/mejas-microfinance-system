"""
Generates a circular medallion logo with an elegant gold border ring matching the web design,
saved to static/images/logo_emblem.png for use in PDF document generation and UI elements.
"""
import os
from PIL import Image, ImageDraw, ImageFilter

def create_circular_logo():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(base_dir, 'static', 'logo.png')
    out_dir = os.path.join(base_dir, 'static', 'images')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'logo_emblem.png')

    if not os.path.exists(src_path):
        print(f"Source logo {src_path} not found.")
        return

    # Open base logo (1024x1024)
    img = Image.open(src_path).convert("RGBA")
    size = min(img.size)
    # Center crop if not square
    left = (img.width - size) // 2
    top = (img.height - size) // 2
    img = img.crop((left, top, left + size, top + size))

    # Work at high resolution (1024x1024) with supersampling
    high_res = (1024, 1024)
    img = img.resize(high_res, Image.Resampling.LANCZOS)

    # Create supersampled circular mask (2048x2048) for ultra-crisp antialiasing
    scale = 2
    canvas_size = high_res[0] * scale
    mask = Image.new("L", (canvas_size, canvas_size), 0)
    draw_mask = ImageDraw.Draw(mask)

    # Inset slightly for border
    border_width_hi = int(24 * scale)
    outer_pad = int(8 * scale)
    draw_mask.ellipse(
        (outer_pad, outer_pad, canvas_size - outer_pad, canvas_size - outer_pad),
        fill=255
    )
    mask = mask.resize(high_res, Image.Resampling.LANCZOS)

    # Create transparent result image
    result = Image.new("RGBA", high_res, (0, 0, 0, 0))
    result.paste(img, (0, 0), mask=mask)

    # Draw the gold circular border ring
    border_img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw_border = ImageDraw.Draw(border_img)

    gold_primary = (223, 177, 60, 255)     # #dfb13c
    gold_dark = (184, 134, 11, 255)        # #b8860b (bevel)
    gold_light = (250, 225, 130, 255)      # Highlight

    # Outer border ring
    r_pad = outer_pad
    draw_border.ellipse(
        (r_pad, r_pad, canvas_size - r_pad, canvas_size - r_pad),
        outline=gold_primary,
        width=border_width_hi
    )
    # Subtle inner bevel
    inner_pad = r_pad + border_width_hi
    draw_border.ellipse(
        (inner_pad, inner_pad, canvas_size - inner_pad, canvas_size - inner_pad),
        outline=gold_dark,
        width=int(4 * scale)
    )

    border_img = border_img.resize(high_res, Image.Resampling.LANCZOS)
    result = Image.alpha_composite(result, border_img)

    # Resize to standard crisp 512x512
    final_img = result.resize((512, 512), Image.Resampling.LANCZOS)
    final_img.save(out_path, "PNG", optimize=True)
    print(f"Successfully generated circular gold emblem: {out_path}")

if __name__ == '__main__':
    create_circular_logo()
