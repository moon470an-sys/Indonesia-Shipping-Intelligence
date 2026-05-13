"""Crop p.2 chart panels at 350 DPI (2895x4095). Rows expand to capture x-axis labels."""
from PIL import Image
import os
SRC = r"C:\Users\yoonseok.moon\OneDrive - (주) ST International\Projects\인도네시아 해운 BI\logs\sbs_p2_hi.png"
OUT = r"C:\Users\yoonseok.moon\OneDrive - (주) ST International\Projects\인도네시아 해운 BI\logs\panels"
os.makedirs(OUT, exist_ok=True)
im = Image.open(SRC)
W, H = im.size
print(f"src {W}x{H}")

# More accurate row boundaries (visual inspection of 350dpi page 2):
# header strip "Weekly Review" top: y=0..220
# CPO Market header: y=350..420
# row 1 panels (CPO TC / SHB OB / GAPKI): y=420..1000  (chart band y=550..950)
# row 2 panels (SPOB TC / SHB SPOB / NB SPOB): y=1000..1610 (chart band y=1150..1580)
# OIL TANKER header: y=1650..1730
# row 3 panels (Oil TC / SHB Oil / NB Oil): y=1730..2330 (chart band y=1870..2300)
# LCT header: y=2370..2440
# row 4 panels (2nd LCT / TC LCT / NB LCT): y=2470..3070
panels = [
  ("p2_r1c1_cpo_tc",   560, 1200,  40,  980),
  ("p2_r1c2_shb_ob",   560, 1200, 980, 1900),
  ("p2_r1c3_gapki",    560, 1200, 1900, 2870),
  ("p2_r2c1_spob_tc",  1280, 1900,  40,  980),
  ("p2_r2c2_shb_spob", 1280, 1900, 980, 1900),
  ("p2_r2c3_nb_spob",  1280, 1900, 1900, 2870),
  ("p2_r3c1_oil_tc",   2100, 2700,  40,  980),
  ("p2_r3c2_shb_oil",  2100, 2700, 980, 1900),
  ("p2_r3c3_nb_oil",   2100, 2700, 1900, 2870),
  ("p2_r4c1_2nd_lct",  3050, 3700,  40,  980),
  ("p2_r4c2_tc_lct",   3050, 3700, 980, 1900),
  ("p2_r4c3_nb_lct",   3050, 3700, 1900, 2870),
]
for n, y1, y2, x1, x2 in panels:
    crop = im.crop((x1, y1, x2, y2))
    crop.save(os.path.join(OUT, n + ".png"))
    print(f"saved {n}.png  {crop.size}")
