"""
generate_test_documents.py
---------------------------
Renders synthetic test document images whose text content is taken
DIRECTLY from the existing CSV dataset (merchant_reference.csv,
bank_account_validation.csv) — never independently generated. This is
the fix for the mismatch problem: two separately-generated sources
(an image tool and a text tool) never guarantee agreement, so instead
there is exactly one source of truth (the CSVs), and the images are a
rendering of it, not a second guess at it.

GSTIN handling: none of the source CSVs contain a GST number, so this
script derives a format-valid GSTIN from each merchant's own PAN
number (real GSTINs embed the PAN this way), guaranteeing the PAN
inside the GST certificate always matches the PAN card for the same
merchant.

Usage:
    python generate_test_documents.py \
        --merchant-reference merchant_reference.csv \
        --bank-validation bank_account_validation.csv \
        --output-dir test_documents

Output: test_documents/<holder name>/PAN.png, GST.png, BANK_PROOF.png
        plus a summary.csv mapping each merchant to their file paths
        and expected outcome, for traceability. Folders are named after
        the PAN holder (Session 30) so testers can pick documents by the
        person's name instead of decoding a PAN number.
"""

import argparse
import csv
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_PATH_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
IMAGE_SIZE = (1000, 600)
BG_COLOR = "white"
TEXT_COLOR = "black"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH_BOLD if bold else FONT_PATH, size)


def _render_labeled_document(title: str, fields: list[tuple[str, str]]) -> Image.Image:
    """
    Draws a plain, clearly-labeled test document: a bold disclaimer
    header, a title, then one "Label: Value" line per field. This is
    intentionally NOT a visual replica of any real ID — just clean,
    high-contrast, OCR-friendly text so extraction is reliable.
    """
    image = Image.new("RGB", IMAGE_SIZE, BG_COLOR)
    draw = ImageDraw.Draw(image)

    draw.text((40, 30), "SAMPLE TEST DOCUMENT — NOT A REAL ID", font=_font(20, bold=True), fill="red")
    draw.line((40, 65, 960, 65), fill="black", width=2)
    draw.text((40, 90), title, font=_font(28, bold=True), fill=TEXT_COLOR)

    y = 160
    for label, value in fields:
        draw.text((40, y), f"{label}:", font=_font(22, bold=True), fill=TEXT_COLOR)
        draw.text((320, y), value, font=_font(22), fill=TEXT_COLOR)
        y += 60

    return image


def derive_gstin(pan_number: str) -> str:
    """
    Constructs a format-valid GSTIN embedding the given PAN, matching
    the pattern in backend/config.py's GST_REGEX:
    2 digits + 10-char PAN + 1 digit + 'Z' + 1 alphanumeric.
    Not a cryptographically real checksum — just format-valid, which is
    all the Decision Engine's pattern check requires.
    """
    return f"27{pan_number}1Z5"


def render_pan_card(name: str, pan_number: str, dob: str) -> Image.Image:
    return _render_labeled_document(
        "PAN CARD",
        [("Name", name), ("PAN Number", pan_number), ("Date of Birth", dob)],
    )


def render_gst_certificate(business_name: str, pan_number: str) -> Image.Image:
    return _render_labeled_document(
        "GST REGISTRATION CERTIFICATE",
        [("Business Name", business_name), ("GSTIN", derive_gstin(pan_number))],
    )


def render_bank_proof(name: str, account_number: str, ifsc: str) -> Image.Image:
    return _render_labeled_document(
        "BANK ACCOUNT PROOF",
        [("Account Holder Name", name), ("Account Number", account_number), ("IFSC Code", ifsc)],
    )


def sanitize_dir_name(name: str) -> str:
    """Makes a holder name safe as a folder name (keeps spaces readable)."""
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "'")).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merchant-reference", required=True)
    parser.add_argument("--bank-validation", required=True)
    parser.add_argument("--output-dir", default="test_documents")
    args = parser.parse_args()

    with open(args.merchant_reference, newline="", encoding="utf-8") as f:
        merchants = list(csv.DictReader(f))
    with open(args.bank_validation, newline="", encoding="utf-8") as f:
        bank_rows = list(csv.DictReader(f))

    if len(bank_rows) != len(merchants):
        raise SystemExit(
            f"Row count mismatch: {len(merchants)} merchants but {len(bank_rows)} bank rows. "
            "bank_account_validation.csv has no merchant-linking column, so this script relies "
            "on row order matching merchant_reference.csv exactly — see the earlier data-quality "
            "note. Fix the row counts/order before generating images."
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_rows = []
    used_names: set[str] = set()
    for merchant, bank in zip(merchants, bank_rows):
        pan = merchant["pan_number"]
        # Folder per holder NAME (Session 30), disambiguated with the PAN
        # if two merchants ever share a name.
        base = sanitize_dir_name(merchant["name"])
        name = base
        i = 2
        while name in used_names:
            name = f"{base} {i}"
            i += 1
        used_names.add(name)
        merchant_dir = output_dir / name
        merchant_dir.mkdir(parents=True, exist_ok=True)

        pan_path = merchant_dir / "PAN.png"
        gst_path = merchant_dir / "GST.png"
        bank_path = merchant_dir / "BANK_PROOF.png"

        render_pan_card(merchant["name"], pan, merchant["dob"]).save(pan_path)
        render_gst_certificate(merchant["business_name"], pan).save(gst_path)
        render_bank_proof(merchant["name"], bank["account_number"], bank["ifsc"]).save(bank_path)

        summary_rows.append({
            "pan_number": pan,
            "expected_outcome": merchant["expected_outcome"],
            "pan_image": str(pan_path),
            "gst_image": str(gst_path),
            "bank_image": str(bank_path),
        })

    summary_path = output_dir / "summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Generated {len(summary_rows)} merchants x 3 documents = {len(summary_rows) * 3} images in {output_dir}/")
    print(f"Summary written to {summary_path}")


if __name__ == "__main__":
    main()
