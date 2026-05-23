from automana.core.repositories.app_integration.ebay.ebay_scrape_queries import (
    GET_SCRAPE_TARGETS,
    REFRESH_SCRAPE_TARGETS,
)


def test_get_scrape_targets_orders_by_staleness_weighted_score():
    assert "priority_score" in GET_SCRAPE_TARGETS
    assert "EXTRACT(EPOCH" in GET_SCRAPE_TARGETS
    assert "last_scraped_at" in GET_SCRAPE_TARGETS
    assert "LIMIT 500" in GET_SCRAPE_TARGETS
    assert "ORDER BY" in GET_SCRAPE_TARGETS
    assert "DESC" in GET_SCRAPE_TARGETS


def test_refresh_scrape_targets_sets_priority_score():
    assert "priority_score" in REFRESH_SCRAPE_TARGETS
    assert "MAX(po.sold_avg_cents)" in REFRESH_SCRAPE_TARGETS
    assert "GROUP BY" in REFRESH_SCRAPE_TARGETS
    assert "priority_score = EXCLUDED.priority_score" in REFRESH_SCRAPE_TARGETS
