"""
generate_specs.py
-----------------
Generates one PDF spec sheet per screen-type group, saved to the `specs/` folder.

Usage:
    python3 generate_specs.py
"""

import json
import math
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white, black
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import simpleSplit

# ── Paths ─────────────────────────────────────────────────────

TEMPLATE_DIR = Path(__file__).parent / "templates"
SPECS_DIR    = Path(__file__).parent / "specs"
SPECS_DIR.mkdir(exist_ok=True)

# ── Colours ───────────────────────────────────────────────────

C_HEADER_BG   = HexColor("#1e3a5f")
C_HEADER_TEXT = white
C_ACCENT      = HexColor("#3b82f6")
C_GREEN       = HexColor("#22c55e")
C_GREEN_FILL  = HexColor("#dcfce7")
C_RED_FILL    = HexColor("#fee2e2")
C_RED         = HexColor("#ef4444")
C_CARD_BG     = HexColor("#f8fafc")
C_CARD_BORDER = HexColor("#e2e8f0")
C_TEXT        = HexColor("#1e293b")
C_SUBTEXT     = HexColor("#64748b")
C_GOLD        = HexColor("#d97706")

PAGE_W, PAGE_H = A4   # 595 x 842 pt
MARGIN = 40

# ── Template loader ────────────────────────────────────────────

def load_templates():
    out = []
    for p in sorted(TEMPLATE_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text())
            out.append({
                "name":       data["name"],
                "formats":    [tuple(f) for f in data["formats"]],
                "safe_zones": data.get("safe_zones", []),
                "description": data.get("description", ""),
            })
        except Exception as e:
            print(f"  Skipping {p.name}: {e}")
    return out

# ── Classification ─────────────────────────────────────────────

def classify(w, h):
    r = w / h
    if r > 4.0:   return "ultra_wide"
    if r > 2.2:   return "slim"
    if r > 1.1:   return "landscape"
    if r < 0.85:  return "portrait"
    return "square"

# ── Group metadata ─────────────────────────────────────────────

GROUPS = {
    "landscape": {
        "title":  "Landscape Screens",
        "master": "1920×1080 (Full HD) or 3840×2160 (4K)",
        "safe":   (0.10, 0.10, 0.80, 0.80),
        "tips": [
            "Deliver master at 1920×1080 or 3840×2160 — the app scales down automatically.",
            "Keep logos, text and key visuals within the centre 80% of the frame.",
            "Avoid placing critical content in the top or bottom 10% — may be cropped on taller screens.",
            "Use large, bold text — screens are viewed from 3–10 m away.",
            "Recommended frame rate: 25 fps. Avoid interlaced formats.",
            "Audio is usually muted in malls — visuals must communicate without sound.",
            "Minimum text height: 80px at 1920×1080 output.",
        ],
    },
    "slim": {
        "title":  "Slim / Banner Screens",
        "master": "3200×768 or wider — match your widest output resolution",
        "safe":   (0.08, 0.25, 0.84, 0.50),
        "tips": [
            "Very wide, short banner screens — extremely limited vertical space.",
            "Keep all key content in the vertical centre 50% — top/bottom edges are cropped.",
            "Deliver master at least as wide as the widest output in the template.",
            "Avoid tall imagery or vertical layouts — only a narrow horizontal strip is visible.",
            "Use minimal, large copy — viewers have 2–3 seconds maximum.",
            "Horizontal motion graphics work best. Avoid vertical movement.",
            "Logo placement: centre or left-aligned, never at top/bottom edges.",
        ],
    },
    "ultra_wide": {
        "title":  "Ultra-Wide Screens",
        "master": "Match the exact output resolution — no standard master applies",
        "safe":   (0.05, 0.30, 0.90, 0.40),
        "tips": [
            "Extreme aspect ratio — design specifically for these screens.",
            "Keep all content within the centre 40% of height — very little vertical space.",
            "Horizontal scrolling or marquee-style animations work well.",
            "Provide a master matching the exact pixel dimensions required.",
            "Text must be extremely concise — one short line maximum.",
        ],
    },
    "portrait": {
        "title":  "Portrait Screens",
        "master": "1080×1920 (Full HD portrait — 9:16)",
        "safe":   (0.10, 0.20, 0.80, 0.60),
        "tips": [
            "Deliver master at 1080×1920 (9:16 portrait Full HD).",
            "Keep logos and text within the centre 80% width and 60% height.",
            "Top and bottom 20% may be cropped on screens with different aspect ratios.",
            "Portrait screens are often viewed close-range — medium text sizes are fine.",
            "Vertical motion graphics, product reveals, and scrolling text work well.",
            "Do not adapt a landscape master — design natively in portrait orientation.",
        ],
    },
    "square": {
        "title":  "Near-Square Screens",
        "master": "1080×1080 or match the exact output resolution",
        "safe":   (0.10, 0.10, 0.80, 0.80),
        "tips": [
            "Design master at 1080×1080 or the exact output resolution.",
            "Keep content within a centre 80% square safe zone.",
            "Landscape masters will be heavily cropped — design natively for square.",
            "Centred compositions work best for this format.",
        ],
    },
}

# ── Drawing helpers ────────────────────────────────────────────

def draw_safe_zone(c, x, y, box_w, box_h, sx, sy, sw, sh):
    """Draw a safe zone diagram inside box (x,y,box_w,box_h). y = bottom of box."""
    # Outer frame (danger zone tint)
    c.setFillColor(C_RED_FILL)
    c.setStrokeColor(C_CARD_BORDER)
    c.setLineWidth(1)
    c.roundRect(x, y, box_w, box_h, 4, fill=1, stroke=1)

    # Safe zone fill
    sz_x = x + sx * box_w
    sz_y = y + (1 - sy - sh) * box_h
    sz_w = sw * box_w
    sz_h = sh * box_h

    c.setFillColor(C_GREEN_FILL)
    c.roundRect(sz_x, sz_y, sz_w, sz_h, 3, fill=1, stroke=0)

    # Safe zone border (dashed green)
    c.setStrokeColor(C_GREEN)
    c.setLineWidth(1.5)
    c.setDash(5, 3)
    c.roundRect(sz_x, sz_y, sz_w, sz_h, 3, fill=0, stroke=1)
    c.setDash()

    # "SAFE ZONE" label inside
    c.setFillColor(HexColor("#166534"))
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(sz_x + sz_w / 2, sz_y + sz_h / 2 + 2, "SAFE ZONE")
    c.setFont("Helvetica", 7)
    c.setFillColor(C_GREEN)
    c.drawCentredString(sz_x + sz_w / 2, sz_y + sz_h / 2 - 8,
                        f"{int(sw*100)}% × {int(sh*100)}%")

    # Margin % labels in danger zones
    c.setFont("Helvetica", 7)
    c.setFillColor(C_RED)
    # Left margin
    if sx > 0.03:
        c.drawCentredString(x + sx * box_w / 2, y + box_h / 2, f"{int(sx*100)}%")
    # Right margin
    if sx > 0.03:
        c.drawCentredString(x + box_w - sx * box_w / 2, y + box_h / 2, f"{int(sx*100)}%")
    # Top margin (remember: reportlab y goes up)
    if sy > 0.03:
        c.drawCentredString(x + box_w / 2, y + box_h - sy * box_h / 2, f"{int(sy*100)}%")


def draw_header(c, title, subtitle=""):
    c.setFillColor(C_HEADER_BG)
    c.rect(0, PAGE_H - 70, PAGE_W, 70, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(MARGIN, PAGE_H - 35, title)
    if subtitle:
        c.setFont("Helvetica", 9)
        c.setFillColor(HexColor("#93c5fd"))
        c.drawString(MARGIN, PAGE_H - 52, subtitle)
    # Accent bar
    c.setFillColor(C_ACCENT)
    c.rect(0, PAGE_H - 73, PAGE_W, 3, fill=1, stroke=0)


def draw_section_label(c, x, y, text):
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(C_SUBTEXT)
    c.drawString(x, y, text.upper())


def draw_card(c, x, y, w, h):
    c.setFillColor(C_CARD_BG)
    c.setStrokeColor(C_CARD_BORDER)
    c.setLineWidth(0.5)
    c.roundRect(x, y, w, h, 5, fill=1, stroke=1)


def wrap_text(c, text, x, y, max_w, font, size, color=None, line_height=None):
    """Draw wrapped text, return y after last line."""
    if color:
        c.setFillColor(color)
    c.setFont(font, size)
    if line_height is None:
        line_height = size * 1.35
    lines = simpleSplit(text, font, size, max_w)
    for line in lines:
        c.drawString(x, y, line)
        y -= line_height
    return y

# ── PDF builder ────────────────────────────────────────────────

def build_group_pdf(group_key, members, out_path: Path):
    g = GROUPS[group_key]
    sx, sy, sw, sh = g["safe"]

    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    content_w = PAGE_W - 2 * MARGIN

    # ── Page 1: overview ──────────────────────────────────────
    draw_header(c,
                f"AdScreen Client Specs  —  {g['title']}",
                "Technical specifications & safe zone guide · Primedia Out of Home")

    cursor = PAGE_H - 90

    # Master file box
    draw_card(c, MARGIN, cursor - 44, content_w, 44)
    draw_section_label(c, MARGIN + 10, cursor - 10, "Recommended master file")
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(C_ACCENT)
    c.drawString(MARGIN + 10, cursor - 28, g["master"])
    cursor -= 58

    # Two-column: tips (left) | safe zone (right)
    col_gap  = 16
    left_w   = content_w * 0.55
    right_w  = content_w - left_w - col_gap
    section_h = 220

    # Tips box (left)
    draw_card(c, MARGIN, cursor - section_h, left_w, section_h)
    c.setFillColor(C_GOLD)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(MARGIN + 10, cursor - 14, "DESIGN TIPS")
    tip_y = cursor - 30
    for tip in g["tips"]:
        c.setFillColor(C_ACCENT)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(MARGIN + 10, tip_y, "→")
        tip_y = wrap_text(c, tip, MARGIN + 22, tip_y,
                          left_w - 32, "Helvetica", 8, C_TEXT, 11)
        tip_y -= 3
        if tip_y < cursor - section_h + 10:
            break

    # Safe zone diagram (right)
    rz_x = MARGIN + left_w + col_gap
    rz_y = cursor - section_h
    draw_card(c, rz_x, rz_y, right_w, section_h)

    draw_section_label(c, rz_x + 8, cursor - 10, "Safe zone diagram")

    # Draw diagram centred in right column
    diag_pad = 14
    diag_w = right_w - diag_pad * 2
    aspect = members[0]["formats"][0][1] / members[0]["formats"][0][0]
    diag_h = min(diag_w * aspect, section_h - 40)
    diag_w = diag_h / aspect if diag_h < diag_w * aspect else diag_w
    diag_x = rz_x + (right_w - diag_w) / 2
    diag_y_bottom = rz_y + (section_h - 30 - diag_h) / 2 + 10

    ex = members[0]
    if ex["safe_zones"]:
        z = ex["safe_zones"][0]
        d_sx, d_sy, d_sw, d_sh = z["x"], z["y"], z["width"], z["height"]
    else:
        d_sx, d_sy, d_sw, d_sh = sx, sy, sw, sh

    draw_safe_zone(c, diag_x, diag_y_bottom, diag_w, diag_h, d_sx, d_sy, d_sw, d_sh)

    # Resolution label under diagram
    c.setFont("Helvetica", 7)
    c.setFillColor(C_SUBTEXT)
    ex_w, ex_h = ex["formats"][0][0], ex["formats"][0][1]
    c.drawCentredString(rz_x + right_w / 2, rz_y + 6, f"Example: {ex_w}×{ex_h}px")

    # Legend
    c.setFillColor(C_GREEN)
    c.rect(rz_x + 8, rz_y + 18, 8, 6, fill=1, stroke=0)
    c.setFillColor(C_SUBTEXT)
    c.setFont("Helvetica", 6.5)
    c.drawString(rz_x + 19, rz_y + 20, "Safe zone")
    c.setFillColor(C_RED)
    c.rect(rz_x + 65, rz_y + 18, 8, 6, fill=1, stroke=0)
    c.setFillColor(C_SUBTEXT)
    c.drawString(rz_x + 76, rz_y + 20, "Avoid here")

    cursor -= section_h + 16

    # ── Screens section ───────────────────────────────────────
    c.setFillColor(C_HEADER_BG)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(C_TEXT)
    c.drawString(MARGIN, cursor, f"Screens in this group  ({len(members)} templates)")
    c.setStrokeColor(C_CARD_BORDER)
    c.setLineWidth(0.5)
    c.line(MARGIN, cursor - 4, PAGE_W - MARGIN, cursor - 4)
    cursor -= 18

    # Template cards — 2 columns
    card_w   = (content_w - 12) / 2
    card_h   = 90
    col_idx  = 0

    for tmpl in sorted(members, key=lambda t: t["name"]):
        max_w = max(f[0] for f in tmpl["formats"])
        max_h = max(f[1] for f in tmpl["formats"])

        if col_idx == 0:
            card_x = MARGIN
        else:
            card_x = MARGIN + card_w + 12

        card_y = cursor - card_h
        if card_y < MARGIN:
            c.showPage()
            draw_header(c, f"AdScreen Client Specs  —  {g['title']} (cont.)")
            cursor = PAGE_H - 90
            card_y = cursor - card_h
            col_idx = 0
            card_x = MARGIN

        draw_card(c, card_x, card_y, card_w, card_h)

        # Template name
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(C_TEXT)
        name_lines = simpleSplit(tmpl["name"], "Helvetica-Bold", 9, card_w - 16)
        name_y = card_y + card_h - 14
        for nl in name_lines[:2]:
            c.drawString(card_x + 8, name_y, nl)
            name_y -= 11

        # Suggested master
        c.setFont("Helvetica", 7.5)
        c.setFillColor(C_SUBTEXT)
        c.drawString(card_x + 8, name_y - 2, "Suggested master:")
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(C_ACCENT)
        c.drawString(card_x + 82, name_y - 2, f"{max_w}×{max_h}")

        # Format list
        fmt_y = name_y - 14
        for fmt in tmpl["formats"][:5]:
            label = fmt[2] if len(fmt) > 2 else f"{fmt[0]}×{fmt[1]}"
            ar    = fmt[0] / fmt[1]
            c.setFont("Helvetica", 6.5)
            c.setFillColor(C_TEXT)
            c.drawString(card_x + 8, fmt_y, f"• {fmt[0]}×{fmt[1]}")
            c.setFillColor(C_SUBTEXT)
            c.drawString(card_x + 56, fmt_y, f"({ar:.2f}:1)  {label}")
            fmt_y -= 9
            if fmt_y < card_y + 4:
                break

        if len(tmpl["formats"]) > 5:
            c.setFont("Helvetica", 6)
            c.setFillColor(C_SUBTEXT)
            c.drawString(card_x + 8, card_y + 4, f"+ {len(tmpl['formats'])-5} more format(s)")

        col_idx += 1
        if col_idx == 2:
            cursor -= card_h + 10
            col_idx = 0

    if col_idx == 1:
        cursor -= card_h + 10

    # Footer
    c.setFont("Helvetica", 7)
    c.setFillColor(C_SUBTEXT)
    c.drawCentredString(PAGE_W / 2, MARGIN / 2,
                        "AdScreen Converter · Primedia Out of Home · Confidential")

    c.save()
    print(f"  ✓ {out_path.name}  ({len(members)} templates)")


# ── Main ──────────────────────────────────────────────────────

def main():
    templates = load_templates()
    grouped = {k: [] for k in GROUPS}

    for tmpl in templates:
        if tmpl["formats"]:
            w, h = tmpl["formats"][0][0], tmpl["formats"][0][1]
            g = classify(w, h)
            if g in grouped:
                grouped[g].append(tmpl)

    print(f"\nGenerating PDFs in: {SPECS_DIR}\n")
    for gk, members in grouped.items():
        if not members:
            continue
        out_path = SPECS_DIR / f"{GROUPS[gk]['title'].replace('/', '-').replace(' ', '_')}.pdf"
        build_group_pdf(gk, members, out_path)

    print(f"\nDone — {sum(1 for m in grouped.values() if m)} PDF(s) saved to specs/")


if __name__ == "__main__":
    main()
