"""Render PDF p.1-2 to high-res PNGs for visual inspection / OCR."""
import fitz, os, sys
PDF = r"C:\Users\yoonseok.moon\OneDrive - (주) ST International\Projects\인도네시아 해운 BI\[SBS] Weekly Marketing Report 2026.05.07.pdf"
OUT = r"C:\Users\yoonseok.moon\OneDrive - (주) ST International\Projects\인도네시아 해운 BI\logs"
os.makedirs(OUT, exist_ok=True)
doc = fitz.open(PDF)
for i in range(min(5, doc.page_count)):
    page = doc[i]
    pix = page.get_pixmap(dpi=220)
    out = os.path.join(OUT, f"sbs_p{i+1}.png")
    pix.save(out)
    print(f"saved {out}  {pix.width}x{pix.height}")
