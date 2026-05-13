"""Crop p.1 (international freight + domestic fuel) into panels."""
from PIL import Image
import os
SRC = r"C:\Users\yoonseok.moon\OneDrive - (주) ST International\Projects\인도네시아 해운 BI\logs\sbs_p1_hi.png"
OUT = r"C:\Users\yoonseok.moon\OneDrive - (주) ST International\Projects\인도네시아 해운 BI\logs\panels"
os.makedirs(OUT, exist_ok=True)
im = Image.open(SRC)
W, H = im.size
print(f"src {W}x{H}")
# p.1 has 2 columns + multiple rows
# rough Y bands (350dpi A4):
#   600..950 = Baltic TCE dry / tanker (2 cols)
#  1100..1500 = BDI/BCI / scrap dry / scrap tanker  (3 cols)
#  1700..2400 = secondhand sales (2 cols)
#  2520..2630 = Domestic Freight header
#  2640..3300 = Tug & Barge TC (col1) / Solar B40 (col2 top) / HFO 180 (col2 bottom)
#  3350..3900 = NB Domestic / NB China / 2nd / Scrap (4 cols)
panels = [
  ("p1_baltic_tce_dry",   600,  1090,  40, 1450),
  ("p1_baltic_tce_tnk",   600,  1090, 1450, 2870),
  ("p1_bdi_bci",         1100,  1700,  40,  990),
  ("p1_scrap_dry",       1100,  1700, 990, 1900),
  ("p1_scrap_tanker",    1100,  1700, 1900, 2870),
  ("p1_sale_purchase_dry",1700, 2400,  40, 1450),
  ("p1_sale_purchase_tnk",1700, 2400, 1450, 2870),
  ("p1_tug_barge_tc",    2630,  3340,  40, 1450),
  ("p1_solar_b40",       2630,  2950, 1450, 2870),
  ("p1_hfo_180_mfo",     3020,  3340, 1450, 2870),
  ("p1_nb_tb_domestic",  3340,  3950,  40,  720),
  ("p1_nb_tb_china",     3340,  3950, 720, 1450),
  ("p1_2nd_tb",          3340,  3950, 1450, 2200),
  ("p1_scrap_domestic",  3340,  3950, 2200, 2870),
]
for n, y1, y2, x1, x2 in panels:
    crop = im.crop((x1, y1, x2, y2))
    crop.save(os.path.join(OUT, n + ".png"))
    print(f"saved {n}.png  {crop.size}")
