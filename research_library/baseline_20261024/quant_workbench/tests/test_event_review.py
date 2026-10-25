from dataclasses import replace

import pandas as pd
from quant_workbench.engine import Action
from quant_workbench.event_review import validate_gap_review, validate_review


def test_differential_distribution_keeps_account_cash_and_rejects_changes():
    action = Action("x", "20240723", "20240724", cash_per_share=.3158, pay_date="20240724")
    review = {"classification": "differential_reference", "account_cash": .3158,
              "account_stock_ratio": 0, "reference_cash": .28, "reference_stock_ratio": 0}
    assert validate_review(review, 16.29, 16.01, 16.29 / 16.01, [action])
    assert not validate_review(review, 16.29, 16.01, 16.29 / 16.01, [replace(action, cash_per_share=.28)])
    assert not validate_review(review, 16.29, 15.0, 16.29 / 15, [action])
    assert not validate_review(review, 16.29, 16.01, 16.29 / 16.01, [replace(action, uncertain_entitlement=True)])


def test_rights_review_cannot_approve_free_bonus_shares_or_different_date_price():
    review = {"classification": "rights_not_subscribed", "account_cash": 0,
              "account_stock_ratio": 0, "observed_reference": 9.36}
    assert validate_review(review, 10.52, 9.36, 10.52 / 9.36, [])
    assert not validate_review(review, 10.52, 9.36, 10.52 / 9.36,
                               [Action("x", "20201013", "20201022", stock_ratio=.3)])
    assert not validate_review(review, 10.52, 9.35, 10.52 / 9.35, [])


def test_suspended_distributions_reconcile_sequence_and_do_not_hide_missing_actions():
    dates = pd.to_datetime(["20240102", "20240103", "20240104", "20240105"])
    panels = {"close": pd.DataFrame({"x": [20., None, None, 8.]}, index=dates),
              "pre_close": pd.DataFrame({"x": [20., None, None, 8.5]}, index=dates),
              "adj_factor": pd.DataFrame({"x": [1., 2., 20 / 8.5, 20 / 8.5]}, index=dates)}
    actions = [Action("x", "20240102", "20240103", stock_ratio=1, list_date="20240105"),
               Action("x", "20240103", "20240104", cash_per_share=1.5, pay_date="20240104")]
    review = {"code": "x", "classification": "distributions_during_suspension",
              "previous_quote": "20240102", "resumption_quote": "20240105",
              "gap_actions": [{"date": "20240103", "cash": 0, "stock": 1},
                              {"date": "20240104", "cash": 1.5, "stock": 0}]}
    assert validate_gap_review(review, panels, actions)
    assert not validate_gap_review(review, panels, actions[:1])
    panels["close"].at[dates[1], "x"] = 11
    assert not validate_gap_review(review, panels, actions)
