"""Source decisions for nonstandard events, after register_event_reviews.py."""
import json

from quant_workbench.sources import archive

from quant_workbench.data import ROOT, write_json

rows = json.loads((ROOT / "config/event_reviews.json").read_text(encoding="utf-8"))
actions = json.loads((ROOT / "data/panels/actions.json").read_text(encoding="utf-8"))
notices = json.loads((ROOT / "artifacts/other_event_notices.json").read_text(encoding="utf-8"))


def save(row, receipt):
    row.update(source=receipt["url"], source_path=receipt["path"], source_sha256=receipt["sha256"], reviewed_on="2026-10-24")
    key = (row["code"], row["date"], row["issue_type"])
    rows[:] = [r for r in rows if (r["code"], r["date"], r["issue_type"]) != key]
    rows.append(row)


for code, date, previous, resumed, kind in [
    ("000630.SZ", "20150924", "20150306", "20151023", "action_factor_mismatch"),
    ("601877.SH", "20151014", "20150515", "20151127", "action_factor_mismatch"),
    ("600717.SH", "20260618", "20260608", "20260623", "action_factor_mismatch"),
    ("600717.SH", "20260623", "20260608", "20260623", "unexplained_factor_change"),
    ("600256.SH", "20180328", "20180319", "20180410", "unexplained_factor_change"),
]:
    event = next(n for n in notices if n["code"] == code and n["date"] == date)
    notice = next(n for n in event["notices"] if "实施公告" in n["title"] or "配股发行结果" in n["title"])
    relevant = sorted([a for a in actions if a["code"] == code and previous < a["ex_date"] <= resumed], key=lambda a: a["ex_date"])
    economic = [{"date": a["ex_date"], "cash": a["cash_per_share"], "stock": a["stock_ratio"]} for a in relevant]
    rights = code == "600256.SH"
    row = {"code": code, "date": date, "issue_type": kind, "previous_quote": previous, "resumption_quote": resumed,
           "gap_actions": economic, "account_cash": 0, "account_stock_ratio": 0,
           "classification": "rights_not_subscribed_during_suspension" if rights else "distributions_during_suspension",
           "source_title": notice["title"], "source_pages": list(range(1, notice["receipt"]["pages"] + 1)),
           "evidence_note": ("公告第3页确认3月28日配股除权、预计4月10日复牌；研究不参与配股。以无报价区间两端因子和复牌参考价交叉核对，不能凭无报价日因子推断免费股份。" if rights else
                             "公告核实分配日期及权益；停牌期间逐次调整每股记账价，将无报价区间两端累计因子、复牌参考价与全部分配事件交叉核对。不得直接用数月前未调整收盘价校验第二次除权，也不将现金发放日期推迟至复牌日。")}
    if rights:
        row["source_reference"] = 3.81
    save(row, notice["receipt"])

for code, date, previous, reference, url in [
    ("000793.SZ", "20260622", 2.63, 2.51, "https://pdf.dfcfw.com/pdf/H2_AN202606171823639955_1.pdf"),
    ("600666.SH", "20230220", 2.84, 1.79, "https://pdf.dfcfw.com/pdf/H2_AN202302161583251323_1.pdf"),
    ("601258.SH", "20191230", 1.46, 1.42, None),
]:
    if code == "601258.SH":
        event = next(n for n in notices if n["code"] == code)
        receipt = next(n["receipt"] for n in event["notices"] if "提示性公告" in n["title"])
    else:
        receipt = archive(url)
    save({"code": code, "date": date, "issue_type": "action_factor_mismatch",
          "classification": "reorganization_no_distribution", "account_cash": 0, "account_stock_ratio": 0,
          "observed_previous": previous, "source_reference": reference,
          "source_pages": list(range(1, receipt["pages"] + 1)),
          "evidence_note": "重整文件明确转增股份不向普通原股东分配，并核实特别除权参考价；持仓股数不变，原始股价稀释完整计入净值。"}, receipt)
write_json("config/event_reviews.json", rows)
print("Total scoped source reviews:", len(rows))
