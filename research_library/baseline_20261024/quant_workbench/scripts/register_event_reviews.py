"""Encode the 2026-10-24 source review; this is not a general auto-approval rule."""
import json
import re

import pandas as pd
from pypdf import PdfReader

from quant_workbench.data import ROOT, write_json

notices = json.loads((ROOT / "artifacts/held_event_notices.json").read_text(encoding="utf-8"))
notices += json.loads((ROOT / "artifacts/other_event_notices.json").read_text(encoding="utf-8"))
actions = json.loads((ROOT / "data/panels/actions.json").read_text(encoding="utf-8"))
rights = {
    ("000728.SZ", "20201022"), ("000977.SZ", "20170727"), ("002074.SZ", "20171127"),
    ("002202.SZ", "20190329"), ("002466.SZ", "20191226"), ("002466.SZ", "20171226"),
    ("002673.SZ", "20170411"), ("600089.SH", "20170609"), ("600219.SH", "20181101"),
    ("600919.SH", "20201217"), ("600999.SH", "20200720"), ("601012.SH", "20190417"),
    ("601162.SH", "20200319"), ("601236.SH", "20210804"), ("601555.SH", "20200323"),
    ("601555.SH", "20211223"), ("600030.SH", "20220127"), ("600958.SH", "20220429"),
    ("601108.SH", "20220412"), ("601377.SH", "20220825"),
    ("000661.SZ", "20160427"), ("000686.SZ", "20160415"), ("000750.SZ", "20200114"),
    ("000970.SZ", "20220224"), ("000977.SZ", "20200319"), ("002142.SZ", "20211202"),
    ("002500.SZ", "20200629"), ("600008.SH", "20200929"), ("600489.SH", "20160524"),
    ("600803.SH", "20180212"), ("600909.SH", "20210610"), ("601016.SH", "20221128"),
    ("601099.SH", "20160125"), ("601377.SH", "20160107"), ("601916.SH", "20230627"),
}
# The reference amounts below are NOT the shareholder cash or bonus entitlement.
references = {
    ("000157.SZ", "20190805"): (.2348967, 0, "回购股不参与；公告第4-5页列出参考扣减0.2348967元，普通股东仍获0.25元。"),
    ("000157.SZ", "20230721"): (.32 * 6672070922 / (6672070922 + 423956766), 0,
                                 "公告第1页披露普通股东0.32元，参与分配A股6672070922股、回购股423956766股；按A股总股本摊薄参考金额。"),
    ("002602.SZ", "20190606"): (228185939.60 / 2334756244, 1369115637 / 2334756244,
                                 "实施公告及6月6日补充公告：回购股剔除，普通账户0.1元及0.6股；按修订总派息及总转增摊薄参考价。"),
    ("002602.SZ", "20200713"): (0, .196870, "公告第1-2页：普通账户每股转增0.2股，除权计算使用0.196870。"),
    ("600025.SH", "20190705"): (.15022, 0, "社会公众股0.178元；原股东补足扶贫支出；市场参考价扣减全体平均0.15022元。"),
    ("600025.SH", "20200619"): (.15, 0, "社会公众股0.18元；公告第2页参考价扣减0.15元。"),
    ("600346.SH", "20190627"): (.29, .39, "回购股不参与；普通股东0.3元及0.4股，公告第2页明确参考计算0.29元及0.39。"),
    ("601225.SH", "20210709"): (.7756, 0, "普通股东0.8元；公告第2页以96.95亿/100亿股摊薄，参考扣减0.7756元。"),
    ("603858.SH", "20190819"): (1.55, .29, "普通股东1.614元及0.3股；回购股剔除，公告第2页参考计算1.55元及0.29。"),
    ("600989.SH", "20220512"): (.28, 0, "流通股普通账户0.321元，限售股0.2648元；公告第2页参考价扣减0.28元。"),
    ("600989.SH", "20221227"): (.14, 0, "流通股普通账户0.1841元，限售股0.1216元；公告参考价扣减0.14元。"),
    ("600989.SH", "20240724"): (.28, 0, "普通中小股东0.3158元，大股东0.265元；公告第2页参考价扣减0.28元。"),
    ("300308.SZ", "20240606"): (.4408015, .3918236, "回购股不参与；普通账户0.45元及0.4股，公告第1/4页参考计算0.4408015元及0.3918236。"),
    ("000651.SZ", "20210823"): (2.784787, 0, "回购股不参与；普通账户3元，公告第3页市场参考价扣减2.784787元。"),
    ("000703.SZ", "20260918"): (.8164176, 0, "回购股不参与；普通账户0.9元，公告第1/4页市场参考价扣减0.8164176元。"),
    ("000718.SZ", "20190514"): (.283518, 0, "回购股不参与；普通账户0.3元，公告第3-4页参考价扣减0.283518元。"),
    ("000718.SZ", "20200518"): (.271551, 0, "回购股不参与；普通账户0.3元，公告第3页参考价扣减0.271551元。"),
    ("002831.SZ", "20190513"): (.5963459, 1.1926917, "回购股不参与；普通账户0.6元及1.2股，公告第3页市场参考计算0.5963459元及1.1926917。"),
    ("300274.SZ", "20240613"): (.9552535, .39596, "回购股不参与；普通账户0.965元及0.4股，公告第1页市场参考计算0.9552535元及0.39596。"),
    ("300888.SZ", "20230602"): (1.8699083, .3936649, "回购股不参与；普通账户1.9元及0.4股，公告第1/5页市场参考计算1.8699083元及0.3936649。"),
    ("600900.SH", "20160719"): (.35696, 0, "重组新老股东分配不同；原社会公众股每股合计0.4元，公告第3页220亿股摊薄后参考扣减0.35696元。"),
    ("600989.SH", "20250513"): (.41, 0, "中小股东0.4598元，大股东0.3891元；公告第2页参考价扣减0.41元。"),
    ("600989.SH", "20260428"): (.42, 0, "中小股东0.4921元，大股东0.3906元；公告第2页参考价扣减0.42元。"),
    ("688005.SH", "20250306"): (0, .4798, "普通账户每股转增0.49股；回购股不参与，公告第2-3页参考转增比例0.4798。"),
}
reviews = []
for event in notices:
    code, date = event["code"], event["date"].replace("-", "")
    key = (code, date)
    if key not in rights and key not in references:
        continue
    if key in rights:
        chosen = next(n for n in event["notices"] if "配股发行结果" in n["title"] and "更正" not in n["title"])
    else:
        chosen = next(n for n in event["notices"] if "实施公告" in n["title"] and "法律意见" not in n["title"])
    receipt = chosen["receipt"]
    reader = PdfReader(ROOT / receipt["path"])
    pages = [re.sub(r"\s+", "", p.extract_text() or "") for p in reader.pages]
    relevant = [a for a in actions if a["code"] == code and a["ex_date"] == date]
    row = {"code": code, "date": date, "source": receipt["url"], "source_path": receipt["path"],
           "source_sha256": receipt["sha256"], "source_title": chosen["title"],
           "reviewed_on": "2026-10-24", "account_cash": sum(a["cash_per_share"] for a in relevant),
           "account_stock_ratio": sum(a["stock_ratio"] for a in relevant)}
    if key in rights:
        day = pd.Timestamp(date)
        date_text = f"{day.year}年{day.month}月{day.day}日"
        source_pages = [i + 1 for i, text in enumerate(pages) if date_text in text and "除权" in text]
        assert source_pages, key
        assert not relevant, key
        daily = pd.read_parquet(ROOT / f"data/normalized/daily/{code}.parquet")
        reference = float(daily.loc[daily.trade_date.eq(date), "pre_close"].iloc[0])
        row.update(issue_type="unexplained_factor_change", classification="rights_not_subscribed",
                   observed_reference=reference, source_pages=source_pages,
                   evidence_note="发行结果公告核实配股成功及该日除权。研究账户统一不参与配股，不增加股份、不支出认购款，保留原始价格稀释损失。此项仅解释因子变动，不证明参与配股的收益。")
    else:
        cash, stock, note = references[key]
        row.update(issue_type="action_factor_mismatch", classification="differential_reference",
                   reference_cash=cash, reference_stock_ratio=stock, evidence_note=note,
                   source_pages=[i + 1 for i, text in enumerate(pages) if "除权" in text or "回购" in text])
    reviews.append(row)
assert len(reviews) == len(rights) + len(references)
write_json("config/event_reviews.json", reviews)

override_file = ROOT / "config/action_overrides.json"
overrides = json.loads(override_file.read_text(encoding="utf-8"))
taibao = {"code": "601601.SH", "record_date": "20210629", "ex_date": "20210630",
          "cash_per_share": 1.3, "stock_ratio": 0, "pay_date": "20210630", "list_date": "",
          "source": "https://pdf.dfcfw.com/pdf/H2_AN202106211499157648_1.pdf",
          "reason": "公司实施公告第1页确认年度1.2元及30周年特别0.1元合计1.3元。接口0.1与1.3为部分与合计，不应合计成1.4元。"}
overrides = [r for r in overrides if (r["code"], r["ex_date"]) != (taibao["code"], taibao["ex_date"])]
write_json("config/action_overrides.json", overrides + [taibao])
print(f"Registered {len(reviews)} scoped reviews and {len(overrides) + 1} action overrides.")
