"""
PayTraq MCP — Financial Reports Tools
----------------------------------------
Tools for generating financial reports built from PayTraq journal entries.

Account mapping follows the official NSIS.LV / PayTraq chart of accounts:
  1. Correct P&L hierarchy: Bruto -> Operacionala -> EBIT -> Net
  2. Account groupings aligned with COGS / Operational / Other sections
  3. DR/CR sign handling per account type
  4. Balance sheet uses only real balance accounts (transit accounts excluded)

When to use these tools:
  - profit_and_loss: generate an income statement for any date range
  - balance_sheet: generate a snapshot of assets and liabilities at a given date
  - quarterly_report: get combined P&L + balance sheet for a full quarter (fastest)
"""

import re
from collections import defaultdict
from typing import Annotated, Optional
from pydantic import Field
from mcp.server.fastmcp import FastMCP
from paytraq_client import get, format_response

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(value: Optional[str], field_name: str) -> Optional[str]:
    if value and not _DATE_RE.match(value):
        return f"Invalid {field_name} format '{value}'. Use YYYY-MM-DD (e.g. 2026-03-31)."
    return None


# ── Группировка счетов P&L (из официальных отчётов NSIS.LV) ──────────────────

# Доходы
REVENUE_ACCOUNTS = {"6110", "6120", "6130", "6140", "6150", "6160", "6170", "6180", "6190"}

# Себестоимость (COGS / Ražošanas izmaksas)
COGS_ACCOUNTS = {"7120", "7130", "7140", "7150", "7160", "7170", "7210", "7220",
                 "7310", "7320", "7330", "7340", "7350", "7360", "7370", "7380",
                 "7390", "7420", "7430"}

# Операционные — продажи
SALES_ACCOUNTS = {"7610", "7620", "7630", "7640", "7650"}

# Операционные — администрация
ADMIN_ACCOUNTS = {"7710", "7720", "7730", "7740", "7750", "7760", "7770", "7780", "7790"}

# Прочие операционные расходы
OTHER_OP_ACCOUNTS = {"7510", "7520", "7530", "7540", "7550", "7560", "7570", "7580",
                     "7590", "7600"}

# Финансовые расходы/доходы
FINANCE_ACCOUNTS = {"8110", "8120", "8130", "8140", "8150",
                    "8210", "8220", "8230", "8240", "8250", "8260",
                    "8510", "8520", "8530"}

# Налоги
TAX_ACCOUNTS = {"8810", "8820", "8830", "8840", "8850"}

# Чрезвычайные статьи
EXTRAORDINARY_ACCOUNTS = {"8610", "8620", "8630"}

# Балансовые счета (только реальные, без транзитных) ───────────────────────────

# Активы — ТОЛЬКО реальные балансовые (не транзитные)
ASSET_NONCURRENT = {
    "1110", "1120", "1130", "1140", "1150", "1160", "1170", "1180", "1190",
    "1191", "1192", "1193", "1194",
    "1210", "1220", "1230", "1240", "1250",
    "1291", "1292", "1293", "1294",
    "1310", "1320", "1330", "1340", "1350", "1360", "1370", "1380",
}

ASSET_CURRENT = {
    "2110", "2120", "2130", "2140", "2150", "2160",
    "2190",
    "2210", "2220", "2230",
    "2310", "2320", "2330", "2340", "2350", "2360", "2370",
    "2410",
    "2510", "2520", "2530",
    "2610", "2620", "2621", "2622", "2623", "2624", "2625",
    "2630",
}

# ИСКЛЮЧАЕМ транзитные/технические счета из баланса:
EXCLUDED_ASSET_ACCOUNTS = {
    "2670",  # Pārējie naudas līdzekļi (transit)
    "2680",  # Savstarpējas ieskaites tranzīta konts
    "2380",  # Prasības un īstermiņa aizdevumi (межкомпанийные)
    "1260",  # Avansa maksājumi par pamatlīdzekļiem (transit)
    "2197",  # Pārmaksas kreditoriem (overpayments - offset by liabilities)
}

# Собственный капитал
EQUITY_ACCOUNTS = {
    "3110", "3120", "3130", "3140", "3150",
    "3210", "3220", "3230", "3240",
    "3310", "3320",
    "3410", "3420",
}

# Обязательства краткосрочные (только реальные)
LIAB_CURRENT = {
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

# Обязательства долгосрочные
LIAB_NONCURRENT = {
    "4110", "4120", "4130", "4140",
    "4210", "4220", "4230",
    "4310", "4320",
    "4410",
}

# ИСКЛЮЧАЕМ технические счета из пассива:
EXCLUDED_LIAB_ACCOUNTS = {
    "5610",  # Norēķini par darba algu (часто транзит)
    "5724",  # Norēķini par PVN (transit offset)
}


def _load_accounts() -> dict:
    """Загружает план счетов: AccountID → {code, name, acc_type}."""
    result = get("accounts")
    raw = result.get("Accounts", {}).get("Account", [])
    if isinstance(raw, dict):
        raw = [raw]
    acc_map = {}
    for a in raw:
        if not isinstance(a, dict):
            continue
        acc_id = a.get("AccountID", "")
        if acc_id:
            acc_map[acc_id] = {
                "code":     a.get("Code", ""),
                "name":     a.get("Name", ""),
                "acc_type": a.get("AccountType", "DR"),
            }
    return acc_map


def _load_journal_balances(date_from: Optional[str] = None,
                            date_till: Optional[str] = None) -> dict:
    """
    Агрегирует балансы из журнальных проводок.
    Возвращает {AccountID: net_balance} где net = sum(DR) - sum(CR).
    """
    balances: dict = defaultdict(float)
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
                    # AmountJournal уже содержит знак:
                    #   DR-проводки → положительное значение
                    #   CR-проводки → отрицательное значение
                    # Используем напрямую без дополнительного инвертирования.
                    amount = float(
                        line.get("Amounts", {}).get("AmountJournal", 0) or 0
                    )
                    balances[acc_id] += amount
                except Exception:
                    pass
        if len(entries) < 100:
            break
        page += 1
    return dict(balances)


def _get_section_amounts(
    balances: dict,
    acc_map: dict,
    code_set: set,
    negate: bool = False,
) -> list[tuple]:
    """
    Возвращает список (code, name, amount) для заданного набора кодов счетов.
    negate=True инвертирует знак (для расходов, чтобы показывать как положительные).
    """
    items = []
    for acc_id, info in acc_map.items():
        code = info["code"]
        if code not in code_set:
            continue
        raw = balances.get(acc_id, 0.0)
        # Для DR-счетов: net = DR - CR (уже посчитано)
        # Для CR-счетов: реальный баланс = -(DR - CR)
        if info["acc_type"] == "CR":
            raw = -raw
        if negate:
            raw = -raw
        if abs(raw) > 0.005:
            items.append((code, info["name"], raw))
    items.sort(key=lambda x: x[0])
    return items


def register(mcp: FastMCP) -> None:

    # ── PROFIT & LOSS ─────────────────────────────────────────────────────────

    @mcp.tool()
    def profit_and_loss(
        date_from: Annotated[str, Field(
            description="Report period start date in YYYY-MM-DD format (e.g. 2026-01-01).",
        )],
        date_till: Annotated[str, Field(
            description="Report period end date in YYYY-MM-DD format (e.g. 2026-03-31).",
        )],
    ) -> str:
        """
        Generate a Profit & Loss (Income Statement) for a date range.

        Use this tool when you need to:
        - See total revenue, costs, and net profit/loss for any period
        - Check gross margin, operating profit, and EBIT
        - Prepare monthly, quarterly, or annual income statements

        Report structure (follows NSIS.LV / PayTraq official format):
          Net Revenue
          - Cost of Goods Sold (COGS)
          = Gross Profit
          - Operating Expenses (Sales + Admin)
          = Operating Profit
          - Other Operating Expenses
          = EBIT (Earnings Before Interest & Tax)
          - Finance Costs & Interest
          - Taxes
          = Net Profit / Loss for the period
        """
        try:
            err = _validate_date(date_from, "date_from")
            if err:
                return f"Error: {err}"
            err = _validate_date(date_till, "date_till")
            if err:
                return f"Error: {err}"

            acc_map = _load_accounts()
            bal = _load_journal_balances(date_from=date_from, date_till=date_till)

            def total(items: list) -> float:
                return sum(i[2] for i in items)

            def fmt_section(title: str, items: list, sign_prefix: str = "") -> str:
                if not items:
                    return f"\n  {title}: 0.00\n"
                lines = [f"\n  {title}"]
                for code, name, amt in items:
                    lines.append(f"    {code}  {name[:42]:<42} {amt:>12,.2f}")
                t = total(items)
                lines.append(f"    {'─'*56}")
                lines.append(f"    {sign_prefix}{'KOPĀ':<46} {t:>12,.2f}")
                return "\n".join(lines)

            # Sign convention:
            #   Revenue (CR accounts): raw = negative -> invert -> positive
            #   Expenses (DR accounts): raw = positive -> use as-is for subtraction

            def costs(code_set: set) -> list[tuple]:
                """Return expense items as positive numbers."""
                items = []
                for acc_id, info in acc_map.items():
                    code = info["code"]
                    if code not in code_set:
                        continue
                    raw = bal.get(acc_id, 0.0)
                    # DR expense accounts: raw > 0 = spent
                    if info["acc_type"] == "CR":
                        raw = -raw
                    if abs(raw) > 0.005:
                        items.append((code, info["name"], raw))
                items.sort(key=lambda x: x[0])
                return items

            def revenues(code_set: set) -> list[tuple]:
                """Return revenue items as positive numbers."""
                items = []
                for acc_id, info in acc_map.items():
                    code = info["code"]
                    if code not in code_set:
                        continue
                    raw = bal.get(acc_id, 0.0)
                    # CR revenue accounts: raw < 0 -> -raw > 0
                    if info["acc_type"] == "DR":
                        val = raw    # DR revenue (rare)
                    else:
                        val = -raw   # CR revenue - invert
                    if abs(val) > 0.005:
                        items.append((code, info["name"], val))
                items.sort(key=lambda x: x[0])
                return items

            # Revenue
            rev_items = revenues(REVENUE_ACCOUNTS)
            t_revenue = sum(i[2] for i in rev_items)

            # COGS
            cogs_items = costs(COGS_ACCOUNTS)
            t_cogs = total(cogs_items)
            t_bruto = t_revenue - t_cogs          # Gross = Revenue - COGS

            # Operating - sales
            sales_items = costs(SALES_ACCOUNTS)
            t_sales = total(sales_items)

            # Operating - admin
            admin_items = costs(ADMIN_ACCOUNTS)
            t_admin = total(admin_items)

            t_operational = t_sales + t_admin
            t_op_profit = t_bruto - t_operational  # Operating profit

            # Other operating expenses
            other_items = costs(OTHER_OP_ACCOUNTS)
            t_other = total(other_items)
            t_ebit = t_op_profit - t_other         # EBIT

            # Finance items
            fin_items = costs(FINANCE_ACCOUNTS)
            t_fin = total(fin_items)

            # Taxes
            tax_items = costs(TAX_ACCOUNTS)
            t_tax = total(tax_items)

            # Net
            t_net = t_ebit - t_fin - t_tax

            sep = "═" * 60
            lines = [
                sep,
                f"  PEĻŅAS VAI ZAUDĒJUMU PĀRSKATS",
                f"  Periods: {date_from} — {date_till}",
                sep,
            ]

            lines.append(fmt_section("NETO APGROZĪJUMS / IEŅĒMUMI", rev_items))
            lines.append(f"\n  {'Neto apgrozījums KOPĀ':<46} {t_revenue:>12,.2f}")

            lines.append(fmt_section("RAŽOŠANAS IZMAKSAS (−)", cogs_items))
            lines.append(f"\n  {'─'*58}")
            icon_b = "+" if t_bruto >= 0 else "-"
            lines.append(f"  [{icon_b}] BRUTO PEĻŅA{'':>35} {t_bruto:>12,.2f}")

            lines.append(fmt_section("  Pārdošanas izmaksas (−)", sales_items))
            lines.append(fmt_section("  Administrācijas izmaksas (−)", admin_items))
            lines.append(f"\n  {'─'*58}")
            icon_o = "+" if t_op_profit >= 0 else "-"
            lines.append(f"  [{icon_o}] OPERACIONĀLĀ PEĻŅA{'':>27} {t_op_profit:>12,.2f}")

            lines.append(fmt_section("PĀRĒJAS SAIMNIECISKĀS DARBĪBAS IZMAKSAS (−)", other_items))
            lines.append(f"\n  {'─'*58}")
            icon_e = "+" if t_ebit >= 0 else "-"
            lines.append(f"  [{icon_e}] PEĻŅA PIRMS NODOKĻIEM UN PROCENTIEM (EBIT) {t_ebit:>10,.2f}")

            if fin_items:
                lines.append(fmt_section("PROCENTU UN FINANŠU IZMAKSAS (−)", fin_items))
            if tax_items:
                lines.append(fmt_section("NODOKĻI (−)", tax_items))

            lines.append(f"\n  {'═'*58}")
            icon_n = "+" if t_net >= 0 else "-"
            label = "PĀRSKATA PERIODA PEĻŅA" if t_net >= 0 else "PĀRSKATA PERIODA ZAUDĒJUMI"
            lines.append(f"  [{icon_n}] {label}{'':>{max(0,31-len(label))}} {t_net:>12,.2f}")
            lines.append(f"  {'═'*58}")

            return "\n".join(lines)
        except Exception as e:
            raise

    # ── BALANCE SHEET ─────────────────────────────────────────────────────────

    @mcp.tool()
    def balance_sheet(
        date_till: Annotated[str, Field(
            description=(
                "Balance sheet date in YYYY-MM-DD format. "
                "All balances are calculated up to and including this date. "
                "Use end-of-month dates (e.g. 2026-03-31, 2026-12-31)."
            ),
        )],
    ) -> str:
        """
        Generate a Balance Sheet (Statement of Financial Position) as of a given date.

        Use this tool when you need to:
        - See total assets, liabilities, and equity at a specific date
        - Verify that the balance sheet balances (Assets = Liabilities + Equity)
        - Prepare end-of-period financial statements

        Only real balance sheet accounts are included — transit and technical
        accounts (2670, 2680, 1260, etc.) are excluded to prevent distortion.
        """
        try:
            err = _validate_date(date_till, "date_till")
            if err:
                return f"Error: {err}"

            acc_map = _load_accounts()

            # CRITICAL: Balance sheet requires ALL historical journals from company
            # inception — not just the current period. Without date_from the
            # PayTraq API defaults to the current year, causing wrong cumulative
            # balances for assets (e.g. 1230), receivables (2310), and
            # liabilities (5721). Always load from a sufficiently early date.
            bal = _load_journal_balances(date_from="2000-01-01", date_till=date_till)

            def asset_val(acc_id: str, info: dict) -> float:
                raw = bal.get(acc_id, 0.0)
                return raw  # DR accounts: positive balance = asset

            def liab_val(acc_id: str, info: dict) -> float:
                raw = bal.get(acc_id, 0.0)
                return -raw  # CR accounts: negative DR-balance = liability

            def build_section(
                code_set: set,
                excluded: set,
                val_fn,
            ) -> list[tuple]:
                items = []
                for acc_id, info in acc_map.items():
                    code = info["code"]
                    if code not in code_set or code in excluded:
                        continue
                    v = val_fn(acc_id, info)
                    if abs(v) > 0.005:
                        items.append((code, info["name"], v))
                items.sort(key=lambda x: x[0])
                return items

            def fmt_bs_section(title: str, items: list) -> tuple[str, float]:
                t = sum(i[2] for i in items)
                lines = [f"\n  > {title}"]
                for code, name, amt in items:
                    lines.append(f"    {code}  {name[:42]:<42} {amt:>12,.2f}")
                lines.append(f"    {'─'*56}")
                lines.append(f"    {'KOPĀ':<46} {t:>12,.2f}")
                return "\n".join(lines), t

            # Assets
            nc_items = build_section(ASSET_NONCURRENT, EXCLUDED_ASSET_ACCOUNTS, asset_val)
            c_items  = build_section(ASSET_CURRENT,    EXCLUDED_ASSET_ACCOUNTS, asset_val)

            nc_str, t_nc = fmt_bs_section("Ilgtermiņa ieguldījumi", nc_items)
            c_str,  t_c  = fmt_bs_section("Apgrozāmie līdzekļi",    c_items)
            t_assets = t_nc + t_c

            # Current-period retained earnings: net of ALL P&L accounts
            # (6xxx revenue + 7xxx/8xxx expenses not yet formally closed to 3420).
            # Formula: -sum(AmountJournal for all P&L accounts) because
            #   revenue accounts are CR (negative AmountJournal) → -(-x) = +x
            #   expense accounts are DR (positive AmountJournal) → -(+x) = -x
            ALL_PL_ACCOUNTS = (
                REVENUE_ACCOUNTS | COGS_ACCOUNTS | SALES_ACCOUNTS |
                ADMIN_ACCOUNTS | OTHER_OP_ACCOUNTS | FINANCE_ACCOUNTS |
                TAX_ACCOUNTS | EXTRAORDINARY_ACCOUNTS
            )
            current_net = 0.0
            for acc_id, info in acc_map.items():
                if info["code"] in ALL_PL_ACCOUNTS:
                    current_net -= bal.get(acc_id, 0.0)

            # Liabilities & Equity
            eq_items  = build_section(EQUITY_ACCOUNTS,  set(), liab_val)
            ncl_items = build_section(LIAB_NONCURRENT,  set(), liab_val)
            cl_items  = build_section(LIAB_CURRENT, EXCLUDED_LIAB_ACCOUNTS, liab_val)

            # Append current-period net to equity items
            if abs(current_net) > 0.005:
                label = "Pārskata perioda peļņa" if current_net >= 0 else "Pārskata perioda zaudējumi"
                eq_items.append(("----", label, current_net))

            eq_str,  t_eq  = fmt_bs_section("Pašu kapitāls",        eq_items)
            ncl_str, t_ncl = fmt_bs_section("Ilgtermiņa kreditori", ncl_items)
            cl_str,  t_cl  = fmt_bs_section("Īstermiņa kreditori",  cl_items)
            t_liab = t_eq + t_ncl + t_cl

            diff = abs(t_assets - t_liab)
            balance_check = (
                f"  [OK] Bilance sadalas: {t_assets:,.2f} = {t_liab:,.2f}"
                if diff < 1
                else f"  [!] Starpiba: {diff:,.2f} (iespejams negrāmatoti ieraksti)"
            )

            sep = "═" * 60
            lines = [
                sep,
                f"  BILANCE — uz {date_till}",
                sep,
                "\n  ## AKTĪVS",
                nc_str,
                c_str,
                f"\n  {'AKTĪVS KOPĀ':<48} {t_assets:>12,.2f}",
                f"\n  {'═'*58}",
                "\n  ## PASĪVS",
                eq_str,
            ]
            if ncl_items:
                lines.append(ncl_str)
            lines += [
                cl_str,
                f"\n  {'PASĪVS KOPĀ':<48} {t_liab:>12,.2f}",
                f"\n  {'═'*58}",
                balance_check,
                sep,
            ]
            return "\n".join(lines)
        except Exception as e:
            raise

    # ── QUARTERLY REPORT ──────────────────────────────────────────────────────

    @mcp.tool()
    def quarterly_report(
        year: Annotated[int, Field(
            description="Year for the report (e.g. 2026).",
            ge=2000,
            le=2100,
        )],
        quarter: Annotated[int, Field(
            description="Quarter number: 1 (Jan-Mar), 2 (Apr-Jun), 3 (Jul-Sep), 4 (Oct-Dec).",
            ge=1,
            le=4,
        )],
    ) -> str:
        """
        Generate a combined quarterly P&L report plus balance sheet snapshot.

        Use this tool as the fastest way to get a full financial overview for a
        calendar quarter. Equivalent to calling profit_and_loss + balance_sheet
        for the same quarter, but in a single call.

        Returns the income statement for the quarter followed by the balance
        sheet as of the last day of that quarter.
        """
        try:
            q_starts = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}
            q_ends   = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}

            if quarter not in q_starts:
                return f"Error: quarter must be 1, 2, 3, or 4. Got: {quarter}"

            date_from = f"{year}-{q_starts[quarter]}"
            date_till = f"{year}-{q_ends[quarter]}"

            pl = profit_and_loss(date_from=date_from, date_till=date_till)
            bs = balance_sheet(date_till=date_till)

            return f"{pl}\n\n{bs}"
        except Exception as e:
            raise
