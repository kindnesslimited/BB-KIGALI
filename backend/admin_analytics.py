"""Admin analytics + PDF receipt helpers."""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors as pdf_colors
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT

logger = logging.getLogger(__name__)


# ---------- Analytics ----------
async def compute_dashboard(db) -> dict[str, Any]:
    """One roll-up call the admin dashboard uses."""
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = (today - timedelta(days=7)).isoformat()
    month_ago = (today - timedelta(days=30)).isoformat()
    now_iso = now.isoformat()

    total_users = await db.users.count_documents({})
    admin_users = await db.users.count_documents({"role": "admin"})
    active_subs = await db.users.count_documents({
        "tier": {"$in": ["basic", "premium"]},
        "subscriptionExpiresAt": {"$gt": now_iso},
    })
    expired_subs = await db.users.count_documents({
        "tier": {"$in": ["basic", "premium"]},
        "subscriptionExpiresAt": {"$lte": now_iso},
    })
    new_users_week = await db.users.count_documents({"createdAt": {"$gte": week_ago}})

    # Payment aggregates by status
    async def _sum_by_status(status: str, since: str | None = None) -> dict:
        match: dict[str, Any] = {"status": status}
        if since:
            match["createdAt"] = {"$gte": since}
        pipe = [
            {"$match": match},
            {"$group": {
                "_id": {"currency": "$currency", "method": "$method"},
                "count": {"$sum": 1},
                "amount": {"$sum": "$amount"},
            }},
        ]
        rows = await db.payments.aggregate(pipe).to_list(200)
        return rows

    success_all = await _sum_by_status("success")
    success_month = await _sum_by_status("success", month_ago)
    success_week = await _sum_by_status("success", week_ago)
    success_today = await _sum_by_status("success", today.isoformat())
    pending = await _sum_by_status("pending")
    failed_month = await _sum_by_status("failed", month_ago)

    def _flat_total(rows: list[dict]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for r in rows:
            cur = (r["_id"] or {}).get("currency") or "?"
            totals[cur] = totals.get(cur, 0) + (r.get("amount") or 0)
        return totals

    tx_month = sum((r.get("count") or 0) for r in success_month)
    tx_pending = sum((r.get("count") or 0) for r in pending)
    tx_failed = sum((r.get("count") or 0) for r in failed_month)

    # Content counters
    total_shows = await db.shows.count_documents({})
    total_programs = await db.programs.count_documents({}) if "programs" in await db.list_collection_names() else 0
    total_news = await db.news.count_documents({})

    return {
        "generatedAt": now_iso,
        "users": {
            "total": total_users,
            "admins": admin_users,
            "newThisWeek": new_users_week,
        },
        "subscriptions": {
            "active": active_subs,
            "expired": expired_subs,
        },
        "revenue": {
            "allTime": _flat_total(success_all),
            "last30Days": _flat_total(success_month),
            "last7Days": _flat_total(success_week),
            "today": _flat_total(success_today),
        },
        "transactions": {
            "successThisMonth": tx_month,
            "pending": tx_pending,
            "failedThisMonth": tx_failed,
            "breakdownByMethod": [
                {"method": (r["_id"] or {}).get("method"), "currency": (r["_id"] or {}).get("currency"),
                 "count": r.get("count", 0), "amount": r.get("amount", 0)}
                for r in success_month
            ],
        },
        "content": {
            "shows": total_shows,
            "programs": total_programs,
            "news": total_news,
        },
    }


async def revenue_series(db, granularity: str = "day", days: int = 30) -> list[dict]:
    """Group successful payments by day/week/month."""
    fmt = {"day": "%Y-%m-%d", "week": "%G-W%V", "month": "%Y-%m"}.get(granularity, "%Y-%m-%d")
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipe = [
        {"$match": {"status": "success", "createdAt": {"$gte": since}}},
        {"$addFields": {"createdAtDt": {"$dateFromString": {"dateString": "$createdAt"}}}},
        {"$group": {
            "_id": {"period": {"$dateToString": {"format": fmt, "date": "$createdAtDt"}}, "currency": "$currency"},
            "count": {"$sum": 1},
            "amount": {"$sum": "$amount"},
        }},
        {"$sort": {"_id.period": 1}},
    ]
    rows = await db.payments.aggregate(pipe).to_list(500)
    return [
        {"period": r["_id"]["period"], "currency": r["_id"]["currency"], "count": r["count"], "amount": r["amount"]}
        for r in rows
    ]


# ---------- PDF receipt ----------
BRAND = pdf_colors.HexColor("#E10600")


def render_receipt_pdf(user: dict, payments: list[dict], month_label: str) -> bytes:
    """Render a monthly payment receipt PDF. Returns raw bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"BB FM Kigali — Receipt {month_label}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=22, textColor=BRAND, spaceAfter=6, leading=26)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, textColor=pdf_colors.grey)
    right = ParagraphStyle("right", parent=styles["Normal"], fontSize=10, alignment=TA_RIGHT)
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=10, textColor=pdf_colors.HexColor("#333333"))

    story: list[Any] = []
    # Header
    story.append(Paragraph("BB FM KIGALI", h1))
    story.append(Paragraph("Live Radio · Podcasts · VOD — Kigali, Rwanda", small))
    story.append(Spacer(1, 8 * mm))

    # Customer + Period box
    customer_lines = [
        ["Statement for", user.get("displayName") or "—"],
        ["Phone", user.get("phone") or "—"],
        ["Email", user.get("email") or "—"],
        ["User ID", user.get("id", "")[:12] + "…"],
        ["Period", month_label],
        ["Issued", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
    ]
    t = Table(customer_lines, colWidths=[35 * mm, 130 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), pdf_colors.HexColor("#555555")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 8 * mm))

    # Payments table
    story.append(Paragraph("Payments this month", styles["Heading3"]))
    header = ["Date", "Description", "Method", "Reference", "Status", "Amount"]
    rows = [header]
    total_by_currency: dict[str, float] = {}
    for p in payments:
        date = (p.get("createdAt") or "")[:10]
        desc = p.get("planLabel") or p.get("purchaseType") or "Payment"
        method = (p.get("method") or "").replace("_", " ").upper()
        ref = (p.get("reference") or p.get("stripeSessionId") or p.get("id") or "")[:14]
        status = (p.get("status") or "").upper()
        cur = p.get("currency") or ""
        amt = p.get("amount") or 0
        rows.append([date, desc, method, ref, status, f"{amt:.2f} {cur}"])
        if p.get("status") == "success":
            total_by_currency[cur] = total_by_currency.get(cur, 0) + amt
    tbl = Table(rows, colWidths=[24 * mm, 45 * mm, 25 * mm, 30 * mm, 20 * mm, 30 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), pdf_colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [pdf_colors.whitesmoke, pdf_colors.white]),
        ("ALIGN", (5, 1), (5, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 8 * mm))

    # Totals
    story.append(Paragraph("Successful total", styles["Heading3"]))
    if total_by_currency:
        for cur, amt in total_by_currency.items():
            story.append(Paragraph(f"<b>{amt:.2f} {cur}</b>", right))
    else:
        story.append(Paragraph("No successful payments this month.", right))

    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph("Thank you for supporting BB FM Kigali. This receipt was auto-generated and does not require a signature. Questions? contact billing@bbkigali.com", small))

    doc.build(story)
    return buf.getvalue()


def render_business_report_pdf(
    range_label: str,
    kpis: dict,
    revenue_rows: list[dict],
    subscribers: list[dict],
    payments: list[dict],
) -> bytes:
    """Render an owner-facing business report as PDF. Returns raw bytes.

    Layout:
      1. Header
      2. Range + KPI block (users, subs, revenue, tx counts by status)
      3. Revenue table (grouped by day/week/month row)
      4. Top subscribers table (limited)
      5. Payments table (limited)
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=f"BB FM Kigali — Business Report {range_label}",
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=22, textColor=BRAND, spaceAfter=6, leading=26)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, textColor=pdf_colors.grey)
    right = ParagraphStyle("right", parent=styles["Normal"], fontSize=10, alignment=TA_RIGHT)

    story: list[Any] = []
    story.append(Paragraph("BB FM KIGALI — BUSINESS REPORT", h1))
    story.append(Paragraph(f"Period: <b>{range_label}</b> · Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", small))
    story.append(Spacer(1, 6 * mm))

    # KPI block
    def kpi_row(label: str, value: Any) -> list[Any]:
        return [Paragraph(f"<b>{label}</b>", styles["Normal"]), Paragraph(str(value), right)]

    kpi_rows = [
        kpi_row("Total customers", kpis.get("totalUsers", 0)),
        kpi_row("Active subscribers", kpis.get("activeSubscribers", 0)),
        kpi_row("Expired subscribers", kpis.get("expiredSubscribers", 0)),
        kpi_row("Packages purchased (this period)", kpis.get("purchases", 0)),
        kpi_row("Successful transactions", kpis.get("txSuccess", 0)),
        kpi_row("Pending transactions", kpis.get("txPending", 0)),
        kpi_row("Failed transactions", kpis.get("txFailed", 0)),
        kpi_row("Revenue (EUR — Stripe/PayPal)", f"{kpis.get('revenueEur', 0):.2f} €"),
        kpi_row("Revenue (RWF — MoMo)", f"{kpis.get('revenueRwf', 0):,.0f} RWF"),
    ]
    kpi_table = Table(kpi_rows, colWidths=[80 * mm, 90 * mm])
    kpi_table.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [pdf_colors.whitesmoke, pdf_colors.white]),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 8 * mm))

    # Revenue table
    if revenue_rows:
        story.append(Paragraph("Revenue over time", styles["Heading3"]))
        rev_header = ["Period", "Currency", "# Transactions", "Amount"]
        rev_rows: list[list[Any]] = [rev_header]
        for r in revenue_rows[:120]:
            rev_rows.append([r.get("period"), r.get("currency"), r.get("count"), f"{r.get('amount', 0):,.2f}"])
        rev_tbl = Table(rev_rows, colWidths=[35 * mm, 30 * mm, 45 * mm, 60 * mm], repeatRows=1)
        rev_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), pdf_colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [pdf_colors.whitesmoke, pdf_colors.white]),
            ("ALIGN", (3, 1), (3, -1), "RIGHT"),
        ]))
        story.append(rev_tbl)
        story.append(Spacer(1, 6 * mm))

    # Subscribers table
    if subscribers:
        story.append(Paragraph(f"Subscribers ({len(subscribers)})", styles["Heading3"]))
        sub_header = ["Name", "Phone / Email", "Plan", "Status", "Expires"]
        sub_rows: list[list[Any]] = [sub_header]
        for u in subscribers[:80]:
            sub_rows.append([
                u.get("displayName") or "—",
                (u.get("phone") or u.get("email") or "—")[:24],
                (u.get("currentPlan") or u.get("tier") or "—").replace("_", " "),
                (u.get("status") or "—").upper(),
                (u.get("subscriptionExpiresAt") or "")[:10],
            ])
        sub_tbl = Table(sub_rows, colWidths=[38 * mm, 45 * mm, 38 * mm, 20 * mm, 30 * mm], repeatRows=1)
        sub_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), pdf_colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [pdf_colors.whitesmoke, pdf_colors.white]),
        ]))
        story.append(sub_tbl)
        story.append(Spacer(1, 6 * mm))

    # Payments table (last 40)
    if payments:
        story.append(Paragraph(f"Latest payments (showing up to 40 of {len(payments)})", styles["Heading3"]))
        pay_header = ["Date", "Customer", "Method", "Plan", "Status", "Amount"]
        pay_rows: list[list[Any]] = [pay_header]
        for p in payments[:40]:
            pay_rows.append([
                (p.get("createdAt") or "")[:10],
                p.get("customerLabel") or (p.get("userId") or "")[:10],
                (p.get("method") or "").replace("_", " ").upper(),
                (p.get("planLabel") or p.get("plan") or "—"),
                (p.get("status") or "—").upper(),
                f"{p.get('amount', 0):,.2f} {p.get('currency', '')}",
            ])
        pay_tbl = Table(pay_rows, colWidths=[22 * mm, 35 * mm, 25 * mm, 40 * mm, 22 * mm, 30 * mm], repeatRows=1)
        pay_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BRAND),
            ("TEXTCOLOR", (0, 0), (-1, 0), pdf_colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [pdf_colors.whitesmoke, pdf_colors.white]),
            ("ALIGN", (5, 1), (5, -1), "RIGHT"),
        ]))
        story.append(pay_tbl)

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "Generated by BB FM Kigali admin console · Confidential — for internal business use only.",
        small))

    doc.build(story)
    return buf.getvalue()
