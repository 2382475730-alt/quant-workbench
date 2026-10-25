"""Apply narrowly scoped, source-backed adjudications without discarding flags."""
from __future__ import annotations

import hashlib
import json
import math

import pandas as pd

from .data import ROOT


def load_reviews():
    path = ROOT / "config/event_reviews.json"
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    reviews = {}
    for row in rows:
        key = (row["code"], row["date"], row["issue_type"])
        if key in reviews:
            raise ValueError(f"Duplicate event review {key}")
        source = (ROOT / row["source_path"]).resolve()
        if not source.is_relative_to(ROOT.resolve()) or not source.is_file():
            raise ValueError(f"Missing review evidence {key}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != row["source_sha256"]:
            raise ValueError(f"Changed review evidence {key}")
        reviews[key] = row
    return reviews


def validate_review(review, previous, reference, factor_ratio, event_actions):
    """Re-check the reviewed economics against current inputs on every preparation."""
    if not all(math.isfinite(float(x)) and float(x) > 0 for x in [previous, reference, factor_ratio]):
        return False
    cash = sum(a.cash_per_share for a in event_actions)
    bonus = sum(a.stock_ratio for a in event_actions)
    if any(a.uncertain_entitlement for a in event_actions):
        return False
    if not math.isclose(cash, review["account_cash"], abs_tol=1e-8):
        return False
    if not math.isclose(bonus, review["account_stock_ratio"], abs_tol=1e-8):
        return False
    # Factor/quotation consistency is independent of the account entitlement.
    if abs(factor_ratio / (previous / reference) - 1) > max(.002, .02 / previous):
        return False
    if review["classification"] == "rights_not_subscribed":
        # No gift shares or subscription cashflows are allowed under this policy.
        return not event_actions and abs(reference - review["observed_reference"]) <= .005
    if review["classification"] == "differential_reference":
        expected = (previous - review["reference_cash"]) / (1 + review["reference_stock_ratio"])
        return abs(reference - expected) <= .011
    if review["classification"] == "reorganization_no_distribution":
        return (cash == bonus == 0 and abs(previous - review["observed_previous"]) <= .005
                and abs(reference - review["source_reference"]) <= .005)
    return False


def validate_gap_review(review, panels, actions):
    code = review["code"]
    before, after = pd.Timestamp(review["previous_quote"]), pd.Timestamp(review["resumption_quote"])
    close = panels["close"][code]
    if before not in close.index or after not in close.index or close.loc[before:after].iloc[1:-1].notna().any():
        return False
    relevant = sorted([a for a in actions if a.code == code and before < pd.Timestamp(a.ex_date) <= after],
                      key=lambda a: a.ex_date)
    economic = [{"date": a.ex_date, "cash": a.cash_per_share, "stock": a.stock_ratio} for a in relevant]
    if economic != review["gap_actions"] or any(a.uncertain_entitlement for a in relevant):
        return False
    previous, reference = float(close.loc[before]), float(panels["pre_close"].at[after, code])
    factor = panels["adj_factor"].at[after, code] / panels["adj_factor"].at[before, code]
    if not all(math.isfinite(x) and x > 0 for x in [previous, reference, factor]):
        return False
    if abs(factor / (previous / reference) - 1) > max(.002, .02 / previous):
        return False
    if review["classification"] == "rights_not_subscribed_during_suspension":
        return not relevant and abs(reference - review["source_reference"]) <= .005
    if review["classification"] == "distributions_during_suspension":
        mark = previous
        for day in sorted({a.ex_date for a in relevant}):
            current = [a for a in relevant if a.ex_date == day]
            mark = (mark - sum(a.cash_per_share for a in current)) / (1 + sum(a.stock_ratio for a in current))
        return abs(mark - reference) <= .011
    return False


def adjudicate(issues, panels, actions, reviews):
    result = []
    for original in issues:
        dates = original.get("dates")
        events = dates or [original.get("date", original.get("ex_date"))]
        for date in events:
            issue = dict(original)
            if dates:
                issue.pop("dates")
                issue["date"] = date
            review = reviews.get((issue["code"], date, issue["type"]))
            if review:
                timestamp = pd.Timestamp(date)
                series = panels["close"][issue["code"]]
                previous = series.loc[series.index < timestamp].dropna()
                factors = panels["adj_factor"][issue["code"]].dropna()
                before = factors.loc[factors.index < timestamp]
                relevant = [a for a in actions if a.code == issue["code"] and a.ex_date == date]
                if review["classification"] in {"distributions_during_suspension", "rights_not_subscribed_during_suspension"}:
                    passed = validate_gap_review(review, panels, actions)
                elif len(previous) and len(before) and timestamp in factors.index:
                    ref = panels["pre_close"].at[timestamp, issue["code"]]
                    ratio = factors.loc[timestamp] / before.iloc[-1]
                    passed = validate_review(review, previous.iloc[-1], ref, ratio, relevant)
                else:
                    passed = False
                issue["review"] = {**review, "status": "accepted" if passed else "inputs_changed_or_inconsistent"}
                if passed:
                    issue["original_severity"] = issue["severity"]
                    issue["severity"] = "info"
            result.append(issue)
    return result
