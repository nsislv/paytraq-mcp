"""
PayTraq MCP — Financial reports built from general-ledger journal entries.

Account groupings follow the official NSIS.LV / PayTraq chart of accounts.
Reports are computed by aggregating journal postings; they do NOT call any
"balance" endpoint (PayTraq v2.57 doesn't expose one). This means figures can
differ slightly from PayTraq's own PDF reports, which use the sub-ledger.

Design notes:
  1. P&L follows the Baltic hierarchy: Bruto → Operacionala → EBIT → Net.
  2. Balance sheet excludes known transit / technical accounts so the two
     sides balance (Assets = Liabilities + Equity).
  3. Sign convention: AmountJournal has the DR (positive) / CR (negative) sign
     baked in. We compute net = sum(AmountJournal) and invert for CR-type
     accounts to get meaningful display values.

Both reports support response_format='markdown' (default pretty-printed table)
and 'json' (machine-readable sections with totals for programmatic use).
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Annotated, Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from paytraq_client import PAGE_SIZE, PaytraqError, get
from tools._common import ResponseFormat, ensure_date


READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)


# ── P&L account groupings (NSIS.LV / PayTraq chart) ───────────────────────────

REVENUE_ACCOUNTS: set[str] = {
    "6110", "6120", "6130", "6140", "6150", "6160", "6170", "6180", "6190",
}

# Cost of goods sold (COGS / production costs)
COGS_ACCOUNTS: set[str] = {
    "7120", "7130", "7140", "7150", "7160", "7170", "7210", "7220",
    "7310", "7320", "7330", "7340", "7350", "7360", "7370", "7380",
    "7390", "7420", "7430",
}

SALES_ACCOUNTS: set[str] = {"7610", "7620", "7630", "7640", "7650"}
ADMIN_ACCOUNTS: set[str] = {
    "7710", "7720", "7730", "7740", "7750", "7760", "7770", "7780", "7790",
}
OTHER_OP_ACCOUNTS: set[str] = {
    "7510", "7520", "7530", "7540", "7550", "7560", "7570", "7580", "7590", "7600",
}
FINANCE_ACCOUNTS: set[str] = {
    "8110", "8120", "8130", "8140", "8150",
    "8210", "8220", "8230", "8240", "8250", "8260",
    "8510", "8520", "8530",
}
TAX_ACCOUNTS: set[str] = {"8810", "8820", "8830", "8840", "8850"}
EXTRAORDINARY_ACCOUNTS: set[str] = {"8610", "8620", "8630"}


# ── Balance-sheet groupings (real accounts only; transits excluded) ───────────

ASSET_NONCURRENT: set[str] = {
    "1110", "1120", "1130", "1140", "1150", "1160", "1170", "1180", "1190",
    "1191", "1192", "1193", "1194",
    "1210", "1220", "1230", "1240", "1250",
    "1291", "1292", "1293", "1294",
    "1310", "1320", "1330", "1340", "1350", "1360", "1370", "1380",
}
ASSET_CURRENT: set[str] = {
    "2110", "2120", "2130", "2140", "2150", "2160", "2190",
    "2210", "2220", "2230",
    "2310", "2320", "2330", "2340", "2350", "2360", "2370",
    "2410",
    "2510", "2520", "2530",
    "2610", "2620", "2621", "2622", "2623", "2624", "2625",
    "2630",
}
# Transit / technical asset accounts — excluded from the balance sheet.
EXCLUDED_ASSET_ACCOUNTS: set[str] = {
    "2670",  # Other cash equivalents (transit)
    "2680",  # Inter-company clearing (transit)
    "2380",  # Inter-company loans / receivables
    "1260",  # Advance payments for fixed assets (transit)
    "2197",  # Overpayments to creditors (offset by liabilities)
}

EQUITY_ACCOUNTS: set[str] = {
    "3110", "3120", "3130", "3140", "3150",
    "3210", "3220", "3230", "3240",
    "3310", "3320",
    "3410", "3420",
}
LIAB_CURRENT: set[str] = {
    "5110", "5120", "5130", "5140",
    "5210", "5220", "5230",
    "5310", "5320", "5330",
    "5410", "5420",
    "5510", "5520", "5530", "5540", "5550", "5560",
    "5610", "5620",
    "5710", "5720", "5721", "5722", "5723", "5724",
    "5730", "5740", "5750", "5760",
    "5810", "5820",
}
LIAB_NONCURRENT: set[str] = {
    "4110", "4120", "4130", "4140",
    "4210", "4220", "4230",
    "4310", "4320",
    "4410",
}
EXCLUDED_LIAB_ACCOUNTS: set[str] = {
    "5610",  # Payroll settlements (transit)
    "5724",  # VAT settlement offset (transit)
}

ALL_PL_ACCOUNTS: set[str] = (
    REVENUE_ACCOUNTS | COGS_ACCOUNTS | SALES_ACCOUNTS | ADMIN_ACCOUNTS
    | OTHER_OP_ACCOUNTS | FINANCE_ACCOUNTS | TAX_ACCOUNTS | EXTRAORDINARY_ACCOUNTS
)


# ── Data loading ──────────────────────────────────────────────────────────────

def _load_accounts() -> dict[str, dict[str, str]]:
    """Load the full chart of accounts (auto-paginated). Returns {AccountID: {code, name, acc_type}}."""
    acc_map: dict[str, dict[str, str]] = {}
    page = 0
    while True:
        raw = get("accounts", {"page": page})
        block = raw.get("Accounts", {})
        if not isinstance(block, dict) or not block:
            break
        accounts = block.get("Account", [])
        if isinstance(accounts, dict):
            accounts = [accounts]
        if not accounts:
            break
        for a in accounts:
            if not isinstance(a, dict):
                continue
            acc_id = a.get("AccountID", "")
            if acc_id:
                acc_map[acc_id] = {
                    "code": a.get("Code", ""),
                    "name": a.get("Name", ""),
                    "acc_type": a.get("AccountType", "DR"),
                }
        if len(accounts) < PAGE_SIZE:
            break
        page += 1
    return acc_map


def _load_journal_balances(
    date_from: Optional[str] = None,
    date_till: Optional[str] = None,
) -> dict[str, float]:
    """
    Aggregate account balances from journal entries over the given period.

    Returns {AccountID: net_balance} where net = sum(AmountJournal). PayTraq's
    AmountJournal already carries the sign:
      - DR postings → positive
      - CR postings → negative
    So a simple sum gives us the signed net per account.
    """
    balances: dict[str, float] = defaultdict(float)
    page = 0
    while True:
        params: dict = {"page": page}
        if date_from:
            params["date_from"] = date_from
        if date_till:
            params["date_till"] = date_till
        raw = get("journals", params)
        block = raw.get("Journals", {})
        if not isinstance(block, dict):
            break
        entries = block.get("Journal", [])
        if isinstance(entries, dict):
            entries = [entries]
        if not entries:
            break
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            je_block = entry.get("JournalEntries", {})
            if not isinstance(je_block, dict):
                continue
            lines = je_block.get("JournalEntry", [])
            if isinstance(lines, dict):
                lines = [lines]
            if not isinstance(lines, list):
                continue
            for line in lines:
                if not isinstance(line, dict):
                    continue
                acc_block = line.get("Account", {})
                if not isinstance(acc_block, dict):
                    continue
                acc_id = acc_block.get("AccountID", "")
                if not acc_id:
                    continue
                try:
                    amount = float(
                        line.get("Amounts", {}).get("AmountJournal", 0) or 0
                    )
                except (TypeError, ValueError):
                    continue
                balances[acc_id] += amount
        if len(entries) < PAGE_SIZE:
            break
        page += 1
    return dict(balances)


# ── Section helpers ───────────────────────────────────────────────────────────

def _expense_items(
    balances: dict[str, float],
    acc_map: dict[str, dict[str, str]],
    code_set: set[str],
) -> list[tuple[str, str, float]]:
    """Expense accounts: DR balance shown as positive."""
    items = []
    for acc_id, info in acc_map.items():
        if info["code"] not in code_set:
            continue
        raw = balances.get(acc_id, 0.0)
        if info["acc_type"] == "CR":
            raw = -raw
        if abs(raw) > 0.005:
            items.append((info["code"], info["name"], raw))
    items.sort(key=lambda x: x[0])
    return items


def _revenue_items(
    balances: dict[str, float],
    acc_map: dict[str, dict[str, str]],
    code_set: set[str],
) -> list[tuple[str, str, float]]:
    """Revenue accounts: CR balance inverted so revenue shows as positive."""
    items = []
    for acc_id, info in acc_map.items():
        if info["code"] not in code_set:
            continue
        raw = balances.get(acc_id, 0.0)
        val = raw if info["acc_type"] == "DR" else -raw
        if abs(val) > 0.005:
            items.append((info["code"], info["name"], val))
    items.sort(key=lambda x: x[0])
    return items


def _balance_items(
    balances: dict[str, float],
    acc_map: dict[str, dict[str, str]],
    code_set: set[str],
    excluded: set[str],
    is_liability: bool,
) -> list[tuple[str, str, float]]:
    """Balance-sheet items: assets show raw DR balance; liabilities show -DR."""
    items = []
    for acc_id, info in acc_map.items():
        code = info["code"]
        if code not in code_set or code in excluded:
            continue
        raw = balances.get(acc_id, 0.0)
        val = -raw if is_liability else raw
        if abs(val) > 0.005:
            items.append((code, info["name"], val))
    items.sort(key=lambda x: x[0])
    return items


def _total(items: list[tuple[str, str, float]]) -> float:
    return sum(amt for _, _, amt in items)


def _items_to_json(items: list[tuple[str, str, float]]) -> list[dict]:
    return [{"code": c, "name": n, "amount": round(a, 2)} for c, n, a in items]


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_section_md(title: str, items: list[tuple[str, str, float]]) -> str:
    if not items:
        return f"\n  {title}: 0.00"
    lines = [f"\n  {title}"]
    for code, name, amt in items:
        lines.append(f"    {code}  {name[:42]:<42} {amt:>12,.2f}")
    lines.append(f"    {'─' * 56}")
    lines.append(f"    {'TOTAL':<46} {_total(items):>12,.2f}")
    return "\n".join(lines)


def _fmt_bs_section_md(title: str, items: list[tuple[str, str, float]]) -> tuple[str, float]:
    total = _total(items)
    lines = [f"\n  > {title}"]
    for code, name, amt in items:
        lines.append(f"    {code}  {name[:42]:<42} {amt:>12,.2f}")
    lines.append(f"    {'─' * 56}")
    lines.append(f"    {'TOTAL':<46} {total:>12,.2f}")
    return "\n".join(lines), total


# ── Report implementations ────────────────────────────────────────────────────

def _profit_and_loss_sections(
    date_from: str, date_till: str
) -> dict[str, Any]:
    """Compute all P&L sections and totals. Used by both markdown and JSON output."""
    acc_map = _load_accounts()
    bal = _load_journal_balances(date_from=date_from, date_till=date_till)

    rev_items = _revenue_items(bal, acc_map, REVENUE_ACCOUNTS)
    cogs_items = _expense_items(bal, acc_map, COGS_ACCOUNTS)
    sales_items = _expense_items(bal, acc_map, SALES_ACCOUNTS)
    admin_items = _expense_items(bal, acc_map, ADMIN_ACCOUNTS)
    other_items = _expense_items(bal, acc_map, OTHER_OP_ACCOUNTS)
    fin_items = _expense_items(bal, acc_map, FINANCE_ACCOUNTS)
    tax_items = _expense_items(bal, acc_map, TAX_ACCOUNTS)

    t_revenue = _total(rev_items)
    t_cogs = _total(cogs_items)
    t_sales = _total(sales_items)
    t_admin = _total(admin_items)
    t_other = _total(other_items)
    t_fin = _total(fin_items)
    t_tax = _total(tax_items)

    t_gross = t_revenue - t_cogs
    t_op = t_gross - (t_sales + t_admin)
    t_ebit = t_op - t_other
    t_net = t_ebit - t_fin - t_tax

    return {
        "period": {"date_from": date_from, "date_till": date_till},
        "sections": {
            "revenue": {"items": rev_items, "total": t_revenue},
            "cogs": {"items": cogs_items, "total": t_cogs},
            "sales_expenses": {"items": sales_items, "total": t_sales},
            "admin_expenses": {"items": admin_items, "total": t_admin},
            "other_operating_expenses": {"items": other_items, "total": t_other},
            "finance_expenses": {"items": fin_items, "total": t_fin},
            "taxes": {"items": tax_items, "total": t_tax},
        },
        "subtotals": {
            "gross_profit": t_gross,
            "operating_profit": t_op,
            "ebit": t_ebit,
            "net_profit": t_net,
        },
    }


def _profit_and_loss_md(data: dict[str, Any]) -> str:
    s = data["sections"]
    st = data["subtotals"]
    p = data["period"]

    sep = "═" * 60
    lines = [
        sep,
        "  PROFIT & LOSS STATEMENT",
        f"  Period: {p['date_from']} — {p['date_till']}",
        sep,
    ]
    lines.append(_fmt_section_md("REVENUE", s["revenue"]["items"]))
    lines.append(f"\n  {'Total revenue':<46} {s['revenue']['total']:>12,.2f}")
    lines.append(_fmt_section_md("COGS (−)", s["cogs"]["items"]))
    lines.append(f"\n  {'─' * 58}")
    lines.append(f"  [{'+' if st['gross_profit'] >= 0 else '-'}] GROSS PROFIT{'':>35} {st['gross_profit']:>12,.2f}")
    lines.append(_fmt_section_md("  Sales expenses (−)", s["sales_expenses"]["items"]))
    lines.append(_fmt_section_md("  Admin expenses (−)", s["admin_expenses"]["items"]))
    lines.append(f"\n  {'─' * 58}")
    lines.append(f"  [{'+' if st['operating_profit'] >= 0 else '-'}] OPERATING PROFIT{'':>30} {st['operating_profit']:>12,.2f}")
    lines.append(_fmt_section_md("OTHER OPERATING EXPENSES (−)", s["other_operating_expenses"]["items"]))
    lines.append(f"\n  {'─' * 58}")
    lines.append(f"  [{'+' if st['ebit'] >= 0 else '-'}] EBIT{'':>42} {st['ebit']:>12,.2f}")
    if s["finance_expenses"]["items"]:
        lines.append(_fmt_section_md("FINANCE EXPENSES (−)", s["finance_expenses"]["items"]))
    if s["taxes"]["items"]:
        lines.append(_fmt_section_md("TAXES (−)", s["taxes"]["items"]))
    lines.append(f"\n  {'═' * 58}")
    net_label = "NET PROFIT" if st["net_profit"] >= 0 else "NET LOSS"
    lines.append(f"  [{'+' if st['net_profit'] >= 0 else '-'}] {net_label:<40} {st['net_profit']:>12,.2f}")
    lines.append(f"  {'═' * 58}")
    return "\n".join(lines)


def _profit_and_loss_json(data: dict[str, Any]) -> str:
    out = {
        "period": data["period"],
        "subtotals": {k: round(v, 2) for k, v in data["subtotals"].items()},
        "sections": {
            name: {
                "total": round(block["total"], 2),
                "items": _items_to_json(block["items"]),
            }
            for name, block in data["sections"].items()
        },
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


def _balance_sheet_sections(date_till: str) -> dict[str, Any]:
    """Compute balance-sheet sections. date_from=2000-01-01 picks up all history."""
    acc_map = _load_accounts()
    # Balance-sheet figures require the full history — PayTraq's default
    # journal window is the current year only, which produces wildly wrong
    # cumulative balances for assets, receivables, and liabilities.
    bal = _load_journal_balances(date_from="2000-01-01", date_till=date_till)

    nc_items = _balance_items(bal, acc_map, ASSET_NONCURRENT, EXCLUDED_ASSET_ACCOUNTS, is_liability=False)
    c_items = _balance_items(bal, acc_map, ASSET_CURRENT, EXCLUDED_ASSET_ACCOUNTS, is_liability=False)

    eq_items = _balance_items(bal, acc_map, EQUITY_ACCOUNTS, set(), is_liability=True)
    ncl_items = _balance_items(bal, acc_map, LIAB_NONCURRENT, set(), is_liability=True)
    cl_items = _balance_items(bal, acc_map, LIAB_CURRENT, EXCLUDED_LIAB_ACCOUNTS, is_liability=True)

    # Running P&L (revenue − expenses) gets reported inside equity as the
    # current-period result until the ledger is formally closed into 3420.
    # For a P&L account: raw balance is negative for revenue (CR),
    # positive for expenses (DR). Profit = -sum(raw) over all P&L codes.
    current_net = 0.0
    for acc_id, info in acc_map.items():
        if info["code"] in ALL_PL_ACCOUNTS:
            current_net -= bal.get(acc_id, 0.0)

    if abs(current_net) > 0.005:
        label = "Current period profit" if current_net >= 0 else "Current period loss"
        eq_items.append(("----", label, current_net))

    t_assets = _total(nc_items) + _total(c_items)
    t_liab_equity = _total(eq_items) + _total(ncl_items) + _total(cl_items)

    return {
        "as_of": date_till,
        "assets": {
            "non_current": {"items": nc_items, "total": _total(nc_items)},
            "current": {"items": c_items, "total": _total(c_items)},
            "total": t_assets,
        },
        "equity_and_liabilities": {
            "equity": {"items": eq_items, "total": _total(eq_items)},
            "non_current_liabilities": {"items": ncl_items, "total": _total(ncl_items)},
            "current_liabilities": {"items": cl_items, "total": _total(cl_items)},
            "total": t_liab_equity,
        },
        "balance_check": {
            "difference": round(t_assets - t_liab_equity, 2),
            "balances": abs(t_assets - t_liab_equity) < 1,
        },
    }


def _balance_sheet_md(data: dict[str, Any]) -> str:
    a = data["assets"]
    el = data["equity_and_liabilities"]
    diff = data["balance_check"]["difference"]
    ok = data["balance_check"]["balances"]

    nc_str, _ = _fmt_bs_section_md("Non-current assets", a["non_current"]["items"])
    c_str, _ = _fmt_bs_section_md("Current assets", a["current"]["items"])
    eq_str, _ = _fmt_bs_section_md("Equity", el["equity"]["items"])
    ncl_str, _ = _fmt_bs_section_md("Non-current liabilities", el["non_current_liabilities"]["items"])
    cl_str, _ = _fmt_bs_section_md("Current liabilities", el["current_liabilities"]["items"])

    sep = "═" * 60
    lines = [
        sep,
        f"  BALANCE SHEET — as of {data['as_of']}",
        sep,
        "\n  ## ASSETS",
        nc_str,
        c_str,
        f"\n  {'TOTAL ASSETS':<48} {a['total']:>12,.2f}",
        f"\n  {'═' * 58}",
        "\n  ## EQUITY & LIABILITIES",
        eq_str,
    ]
    if el["non_current_liabilities"]["items"]:
        lines.append(ncl_str)
    lines.extend([
        cl_str,
        f"\n  {'TOTAL EQUITY & LIABILITIES':<48} {el['total']:>12,.2f}",
        f"\n  {'═' * 58}",
        (
            f"  [OK] Balance sheet balances: "
            f"{a['total']:,.2f} = {el['total']:,.2f}"
            if ok
            else f"  [!] Difference: {diff:,.2f} (possibly unposted entries)"
        ),
        sep,
    ])
    return "\n".join(lines)


def _balance_sheet_json(data: dict[str, Any]) -> str:
    def _json_block(block: dict[str, Any]) -> dict[str, Any]:
        return {
            "total": round(block["total"], 2),
            "items": _items_to_json(block["items"]),
        }

    out = {
        "as_of": data["as_of"],
        "assets": {
            "non_current": _json_block(data["assets"]["non_current"]),
            "current": _json_block(data["assets"]["current"]),
            "total": round(data["assets"]["total"], 2),
        },
        "equity_and_liabilities": {
            "equity": _json_block(data["equity_and_liabilities"]["equity"]),
            "non_current_liabilities": _json_block(
                data["equity_and_liabilities"]["non_current_liabilities"]
            ),
            "current_liabilities": _json_block(
                data["equity_and_liabilities"]["current_liabilities"]
            ),
            "total": round(data["equity_and_liabilities"]["total"], 2),
        },
        "balance_check": data["balance_check"],
    }
    return json.dumps(out, ensure_ascii=False, indent=2)


# ── Tool registration ────────────────────────────────────────────────────────

def register(mcp: FastMCP) -> None:

    @mcp.tool(
        name="paytraq_profit_and_loss",
        title="Generate a Profit & Loss statement",
        annotations=READ_ONLY,
    )
    def paytraq_profit_and_loss(
        date_from: Annotated[str, Field(
            description="Period start date (YYYY-MM-DD), e.g. 2026-01-01.",
        )],
        date_till: Annotated[str, Field(
            description="Period end date (YYYY-MM-DD), e.g. 2026-03-31.",
        )],
        response_format: Annotated[ResponseFormat, Field(
            description="'markdown' for a pretty report (default), 'json' for structured data.",
        )] = ResponseFormat.MARKDOWN,
    ) -> str:
        """
        Generate a Profit & Loss (Income Statement) for any date range.

        Structure (NSIS.LV / PayTraq layout):
          Revenue
          − COGS
          = Gross profit
          − Operating expenses (sales + admin)
          = Operating profit
          − Other operating expenses
          = EBIT
          − Finance costs
          − Taxes
          = Net profit / loss

        Computed by aggregating journal entries in range. For a combined quarter
        report (P&L + balance sheet) use paytraq_quarterly_report.
        """
        ensure_date(date_from, "date_from")
        ensure_date(date_till, "date_till")
        try:
            data = _profit_and_loss_sections(date_from, date_till)
        except PaytraqError:
            raise
        if response_format == ResponseFormat.JSON:
            return _profit_and_loss_json(data)
        return _profit_and_loss_md(data)

    @mcp.tool(
        name="paytraq_balance_sheet",
        title="Generate a Balance Sheet",
        annotations=READ_ONLY,
    )
    def paytraq_balance_sheet(
        date_till: Annotated[str, Field(
            description=(
                "Balance-sheet date (YYYY-MM-DD). All balances are cumulative up to "
                "and including this date. Use end-of-period dates like 2026-03-31."
            ),
        )],
        response_format: Annotated[ResponseFormat, Field(
            description="'markdown' for a pretty report (default), 'json' for structured data.",
        )] = ResponseFormat.MARKDOWN,
    ) -> str:
        """
        Generate a Balance Sheet (Statement of Financial Position) as of a date.

        Only real balance-sheet accounts are included — known transit and
        technical accounts (2670, 2680, 1260, 5724, ...) are excluded to keep
        Assets = Equity + Liabilities. A balance-check line at the bottom flags
        any residual difference.
        """
        ensure_date(date_till, "date_till")
        data = _balance_sheet_sections(date_till)
        if response_format == ResponseFormat.JSON:
            return _balance_sheet_json(data)
        return _balance_sheet_md(data)

    @mcp.tool(
        name="paytraq_quarterly_report",
        title="Combined quarterly P&L + balance sheet",
        annotations=READ_ONLY,
    )
    def paytraq_quarterly_report(
        year: Annotated[int, Field(
            ge=2000, le=2100, description="Year (e.g. 2026).",
        )],
        quarter: Annotated[int, Field(
            ge=1, le=4,
            description="Quarter: 1=Q1 (Jan-Mar), 2=Q2 (Apr-Jun), 3=Q3 (Jul-Sep), 4=Q4 (Oct-Dec).",
        )],
        response_format: Annotated[ResponseFormat, Field(
            description="'markdown' (default) or 'json'.",
        )] = ResponseFormat.MARKDOWN,
    ) -> str:
        """
        Generate the income statement for a calendar quarter plus a balance
        sheet as of the last day of that quarter, in one call.

        Equivalent to calling paytraq_profit_and_loss + paytraq_balance_sheet,
        but saves a round-trip.
        """
        quarter_ranges = {
            1: ("01-01", "03-31"),
            2: ("04-01", "06-30"),
            3: ("07-01", "09-30"),
            4: ("10-01", "12-31"),
        }
        start, end = quarter_ranges[quarter]
        date_from = f"{year}-{start}"
        date_till = f"{year}-{end}"

        pl_data = _profit_and_loss_sections(date_from, date_till)
        bs_data = _balance_sheet_sections(date_till)

        if response_format == ResponseFormat.JSON:
            return json.dumps(
                {
                    "year": year,
                    "quarter": quarter,
                    "profit_and_loss": json.loads(_profit_and_loss_json(pl_data)),
                    "balance_sheet": json.loads(_balance_sheet_json(bs_data)),
                },
                ensure_ascii=False,
                indent=2,
            )
        return f"{_profit_and_loss_md(pl_data)}\n\n{_balance_sheet_md(bs_data)}"
