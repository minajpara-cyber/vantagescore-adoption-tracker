"""Field layouts for the UMBS-aligned single-family MBS disclosure files.

Fannie Mae and Freddie Mac publish identical layouts (pipe-delimited, header row, zipped).
Source: Freddie Mac Single-Family MBS Disclosure Guide v6.3 (effective 2026-10-19) and the
November 2025 credit score disclosure update. Headers are matched to canonical column names;
when a file has no header row we fall back to attribute position.

Credit score history in these files:
  * Nov 17, 2025: "Borrower Credit Score" renamed "Classic FICO" (L-023); new "VS4" field (L-025).
    VS4 is 7777 (Not Applicable) for securities issued before Dec 2025.
  * May 1, 2026: limited VantageScore 4.0 rollout (mainly Rocket, UWM).
  * Sep 2026: VantageScore 4.0 opened to all GSE sellers.
  * Oct 19, 2026: "Pricing Indicator" (L-117, C/V/9) says which score priced the loan, because
    loans may now carry both scores. Also Fannie Score (L-118) and Freddie Score (L-119).
"""
import re


def norm(header: str) -> str:
    """Normalize a header for matching: lowercase alphanumerics only (drops ®, ™, spaces, punctuation)."""
    return re.sub(r"[^a-z0-9]", "", header.lower().replace("™", "").replace("℠", ""))


def slug(header: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")
    return s or "blank"


# (attribute id, official attribute name, canonical column, extra header aliases)
# Canonical None means "keep under its slugified header name".
LOAN_FIELDS = [
    ("L-001", "Loan Identifier", "loan_id", []),
    ("L-002", "Loan Correction Indicator", "loan_correction", []),
    ("L-003", "Prefix", "prefix", []),
    ("L-004", "Security Identifier", "security_id", []),
    ("L-005", "CUSIP", "cusip", []),
    ("L-006", "Mortgage Loan Amount", "orig_loan_amt", []),
    ("L-007", "Issuance Investor Loan UPB", "issuance_upb", []),
    ("L-008", "Current Investor Loan UPB", "current_upb", []),
    ("L-009", "Amortization Type", "amort_type", []),
    ("L-010", "Original Interest Rate", "orig_rate", []),
    ("L-011", "Issuance Interest Rate", "issuance_rate", []),
    ("L-012", "Current Interest Rate", "current_rate", []),
    ("L-013", "Issuance Net Interest Rate", "issuance_net_rate", []),
    ("L-014", "Current Net Interest Rate", "current_net_rate", []),
    ("L-015", "First Payment Date", "first_pay_date", []),
    ("L-016", "Maturity Date", "maturity_date", []),
    ("L-017", "Loan Term", "loan_term", []),
    ("L-018", "Remaining Months to Maturity", "rem_months", []),
    ("L-019", "Loan Age", "loan_age", []),
    ("L-020", "Loan-To-Value (LTV)", "ltv", ["LTV"]),
    ("L-021", "Combined Loan-To-Value (CLTV)", "cltv", ["CLTV"]),
    ("L-022", "Debt-To-Income (DTI)", "dti", ["DTI"]),
    ("L-023", "Classic FICO", "classic_fico", ["Borrower Credit Score"]),
    ("L-024", "Filler", None, []),
    ("L-025", "VantageScore 4.0", "vs4", ["VS4"]),
    ("L-026", "Filler", None, []),
    ("L-027", "Number of Borrowers", "num_borrowers", []),
    ("L-028", "First Time Home Buyer Indicator", "fthb", []),
    ("L-029", "Loan Purpose", "purpose", []),
    ("L-030", "Occupancy Status", "occupancy", []),
    ("L-031", "Number of Units", "units", []),
    ("L-032", "Property Type", "property_type", []),
    ("L-033", "Channel", "channel", []),
    ("L-034", "Property State", "state", []),
    ("L-035", "Seller Name", "seller", []),
    ("L-036", "Servicer Name", "servicer", []),
    ("L-037", "Mortgage Insurance Percent", "mi_pct", []),
    ("L-038", "Mortgage Insurance Cancellation Indicator", None, []),
    ("L-039", "Government Insured Guarantee", None, []),
    ("L-040", "Assumability Indicator", None, []),
    ("L-041", "Interest Only Loan Indicator", "io_flag", []),
    ("L-042", "Interest Only First Principal and Interest Payment Date", None, []),
    ("L-043", "Months to Amortization", None, []),
    ("L-044", "Prepayment Penalty Indicator", None, []),
    ("L-045", "Prepayment Penalty Total Term", None, []),
    ("L-046", "Index", None, []),
    ("L-047", "Mortgage Margin", None, []),
    ("L-048", "MBS/PC Margin", None, []),
    ("L-049", "Interest Rate Adjustment Frequency", None, []),
    ("L-050", "Interest Rate Lookback", None, []),
    ("L-051", "Interest Rate Rounding Method", None, []),
    ("L-052", "Interest Rate Rounding Method Percent", None, []),
    ("L-053", "Convertibility Indicator", None, []),
    ("L-054", "Initial Fixed Rate Period", None, []),
    ("L-055", "Next Interest Rate Adjustment Date", None, []),
    ("L-056", "Months to Next Interest Rate Adjustment Date", None, []),
    ("L-057", "Life Ceiling Interest Rate", None, []),
    ("L-058", "Life Ceiling Net Interest Rate", None, []),
    ("L-059", "Life Floor Interest Rate", None, []),
    ("L-060", "Life Floor Net Interest Rate", None, []),
    ("L-061", "Initial Interest Rate Cap Up Percent", None, []),
    ("L-062", "Initial Interest Rate Cap Down Percent", None, []),
    ("L-063", "Periodic Interest Rate Cap Up Percent", None, []),
    ("L-064", "Periodic Interest Rate Cap Down Percent", None, []),
    ("L-065", "Modification Program", None, []),
    ("L-066", "Modification Type", None, []),
    ("L-067", "Number of Modifications", None, []),
    ("L-068", "Total Capitalized Amount", None, []),
    ("L-069", "Interest Bearing Mortgage Loan Amount", None, []),
    ("L-070", "Original Deferred Amount", None, []),
    ("L-071", "Current Deferred UPB", None, []),
    ("L-072", "Loan Age as Of Modification", None, []),
    ("L-073", "Estimated Loan-To-Value (ELTV)", None, []),
    ("L-074", "Updated Classic FICO", "updated_classic_fico", ["Updated Credit Score"]),
    ("L-075", "Filler", None, []),
    ("L-076", "Interest Rate Step Indicator", None, []),
    ("L-077", "Initial Step Fixed-Rate Period", None, []),
    ("L-078", "Total Number of Steps", None, []),
    ("L-079", "Number of Remaining Steps", None, []),
    ("L-080", "Next Step Rate", None, []),
    ("L-081", "Terminal Step Rate", None, []),
    ("L-082", "Terminal Step Date", None, []),
    ("L-083", "Step Rate Adjustment Frequency", None, []),
    ("L-084", "Next Step Rate Adjustment Date", None, []),
    ("L-085", "Months to Next Step Rate Adjustment Date", None, []),
    ("L-086", "Periodic Step Cap Up Percent", None, []),
    ("L-087", "Origination Mortgage Loan Amount", None, []),
    ("L-088", "Origination Interest Rate", None, []),
    ("L-089", "Origination Amortization Type", None, []),
    ("L-090", "Origination Interest Only Loan Indicator", None, []),
    ("L-091", "Origination First Payment Date", None, []),
    ("L-092", "Origination Maturity Date", None, []),
    ("L-093", "Origination Loan Term", None, []),
    ("L-094", "Origination Loan-To-Value (LTV)", None, []),
    ("L-095", "Origination Combined Loan-To-Value (CLTV)", None, []),
    ("L-096", "Origination Debt-To-Income Ratio", None, []),
    ("L-097", "Origination Classic FICO", "orig_classic_fico", ["Origination Credit Score"]),
    ("L-098", "Filler", None, []),
    ("L-099", "Origination VantageScore 4.0", "orig_vs4", ["Origination VS4"]),
    ("L-100", "Updated VantageScore 4.0", "updated_vs4", ["Updated VS4"]),
    ("L-101", "Origination Loan Purpose", None, []),
    ("L-102", "Origination Occupancy Status", None, []),
    ("L-103", "Origination Channel", None, []),
    ("L-104", "Days Delinquent", "days_delinquent", []),
    ("L-105", "Loan Performance History", None, []),
    ("L-106", "Loan Participation Percent", None, []),
    ("L-107", "Property Valuation Method", "valuation_method", []),
    ("L-108", "Alternative Delinquency Resolution", None, []),
    ("L-109", "Number of Alternative Delinquency Resolutions", None, []),
    ("L-110", "Total Deferral Amount", None, []),
    ("L-111", "Borrower Assistance Plan", None, []),
    ("L-112", "Seller City", "seller_city", []),
    ("L-113", "Seller State", "seller_state", []),
    ("L-114", "Servicer City", None, []),
    ("L-115", "Servicer State", None, []),
    ("L-116", "Special Eligibility Program", "special_program", []),
    ("L-117", "Pricing Indicator", "pricing_indicator", ["Credit Score Pricing Indicator"]),
    ("L-118", "Fannie Score", "fannie_score", []),
    ("L-119", "Freddie Score", "freddie_score", []),
]

SECURITY_FIELDS = [
    ("S-01", "Prefix", "prefix", []),
    ("S-02", "Security Identifier", "security_id", []),
    ("S-03", "CUSIP", "cusip", []),
    ("S-04", "Security Factor Date", "factor_date", []),
    ("S-05", "Security Factor", "factor", []),
    ("S-06", "Payment Delay Days", None, []),
    ("S-07", "Security Data Correction Indicator", "correction", []),
    ("S-08", "Security Status Indicator", None, []),
    ("S-09", "Security Notification Indicator", None, []),
    ("S-10", "Security Description", "description", []),
    ("S-11", "Issuer", "issuer", []),
    ("S-12", "Issue Date", "issue_date", []),
    ("S-13", "Maturity Date", None, []),
    ("S-14", "Updated Longest Maturity Date", None, []),
    ("S-15", "Issuance Investor Security UPB", "issuance_upb", []),
    ("S-16", "Current Investor Security UPB", "current_upb", []),
    ("S-17", "WA Net Interest Rate", "wa_net_rate", []),
    ("S-18", "WA Issuance Interest Rate", "wa_issuance_rate", []),
    ("S-19", "WA Current Interest Rate", None, []),
    ("S-20", "WA Net Accrual Interest Rate", None, []),
    ("S-21", "WA Loan Term", "wa_loan_term", []),
    ("S-22", "WA Issuance Remaining Months to Maturity", None, []),
    ("S-23", "WA Current Remaining Months to Maturity", None, []),
    ("S-24", "WA Loan Age", "wa_loan_age", []),
    ("S-25", "WA Mortgage Loan Amount", None, []),
    ("S-26", "Average Mortgage Loan Amount", None, []),
    ("S-27", "WA Loan-To-Value (LTV)", "wa_ltv", []),
    ("S-28", "WA Combined Loan-To-Value (CLTV)", None, []),
    ("S-29", "WA Debt-To-Income (DTI)", "wa_dti", []),
    ("S-30", "WA Classic FICO", "wa_classic_fico", ["WA Borrower Credit Score"]),
    ("S-31", "Filler", None, []),
    ("S-32", "WA VantageScore 4.0", "wa_vs4", ["WA VS4"]),
    ("S-33", "Loan Count", "loan_count", []),
    ("S-34", "Third Party Origination UPB Percent", None, []),
    ("S-35", "Seller Name", "seller", []),
    ("S-36", "Seller City", None, []),
    ("S-37", "Seller State", None, []),
    ("S-38", "Servicer Name", "servicer", []),
]


def _index(fields):
    by_norm, by_pos = {}, []
    for attr_id, name, canon, aliases in fields:
        col = canon or slug(name)
        by_pos.append(col)
        for h in [name, *aliases]:
            by_norm.setdefault(norm(h), col)
    return by_norm, by_pos


_LOAN_BY_NORM, LOAN_POSITIONAL = _index(LOAN_FIELDS)
_SEC_BY_NORM, SECURITY_POSITIONAL = _index(SECURITY_FIELDS)


def detect_level(first_row: list[str]) -> tuple[str | None, bool]:
    """Return (level, has_header) from the first row of a file."""
    normed = {norm(c) for c in first_row}
    if "loanidentifier" in normed:
        return "loan", True
    if "securityidentifier" in normed or "securityfactordate" in normed:
        return "security", True
    return None, False


def map_header(level: str, header: list[str]) -> list[str]:
    """Map raw header cells to unique canonical column names. Fillers and blanks become _drop_N."""
    by_norm = _LOAN_BY_NORM if level == "loan" else _SEC_BY_NORM
    out, seen = [], set()
    for i, h in enumerate(header):
        n = norm(h)
        if n in ("", "filler"):
            out.append(f"_drop_{i}")
            continue
        col = by_norm.get(n) or slug(h)
        if col in seen:
            col = f"{col}_{i}"
        seen.add(col)
        out.append(col)
    return out


def positional_header(level: str, ncols: int) -> list[str]:
    names = LOAN_POSITIONAL if level == "loan" else SECURITY_POSITIONAL
    out = []
    for i in range(ncols):
        col = names[i] if i < len(names) else f"col_{i + 1:03d}"
        out.append(f"_drop_{i}" if col == "filler" else col)
    return out
