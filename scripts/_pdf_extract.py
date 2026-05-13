"""Extract text + tables from SBS Weekly PDF for Market tab seeding."""
import pdfplumber, json, sys
PDF = r"C:\Users\yoonseok.moon\OneDrive - (주) ST International\Projects\인도네시아 해운 BI\[SBS] Weekly Marketing Report 2026.05.07.pdf"

with pdfplumber.open(PDF) as pdf:
    for i, page in enumerate(pdf.pages, 1):
        print(f"\n===== PAGE {i} =====")
        print(page.extract_text() or "(no text)")
        tables = page.extract_tables()
        for j, t in enumerate(tables):
            print(f"\n--- table {i}.{j} ---")
            for row in t:
                print(row)
