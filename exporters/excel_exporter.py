from datetime import datetime, timezone
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

FIELDS = [
 ("Amazon Seller ID","seller_id"), ("Seller/Storefront Name","seller_name"),
 ("Total Seller Feedback Ratings","lifetime_feedback"), ("Business/Legal Name","business_name"),
 ("Full Business Address","business_address"), ("Country","country"), ("Contact Number","phone_number"),
 ("Amazon Seller Profile Link","profile_url"), ("Marketplace","marketplace"),
 ("Data Source","source_provider"), ("Data Collection Date","enriched_at"),
 ("Verification Status","verification_status")
]

def write_sheet(ws, rows):
    ws.append([label for label, _ in FIELDS])
    for row in rows:
        ws.append([row.get(key) for _, key in FIELDS])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.alignment = Alignment(wrap_text=True)
    for col in ws.columns:
        width = min(max(max(len(str(c.value or "")) for c in col) + 2, 14), 48)
        ws.column_dimensions[get_column_letter(col[0].column)].width = width

def export(qualified, incomplete, counts, folder):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"Amazon_US_Sellers_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Qualified Sellers"
    write_sheet(ws, qualified)
    missing = wb.create_sheet("Missing Information")
    write_sheet(missing, incomplete)
    summary = wb.create_sheet("Run Summary")
    summary.append(["Metric", "Value"])
    items = [
        ("Seller IDs discovered", counts["discovered"]),
        ("Qualified sellers (verified 0-49)", len(qualified)),
        ("Incomplete qualified profiles", len(incomplete)),
        ("Pending enrichment", counts["pending"]),
        ("Marketplace", "Amazon.com (US)"),
        ("Feedback rule", "Strictly fewer than 50 (0-49)"),
        ("Country rule", "Business address in United States only"),
        ("Email collection", "Disabled"),
        ("Coverage", "Keepa-indexed; not a complete Amazon census"),
        ("Generated at UTC", datetime.now(timezone.utc).isoformat())
    ]
    for item in items:
        summary.append(list(item))
    for cell in summary[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    summary.column_dimensions["A"].width = 34
    summary.column_dimensions["B"].width = 70
    wb.save(path)
    return path
