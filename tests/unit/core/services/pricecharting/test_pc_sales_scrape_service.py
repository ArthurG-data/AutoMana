"""Unit tests for the PriceCharting sold-listing HTML parser.

These guard the pure parsing helpers in ``pc_sales_scrape_service`` against the
real PriceCharting DOM shape. The fixture below mirrors the live markup:

  * each grade section renders **two** divs sharing the grade class — a tab
    label (carries ``tab``) and a content panel holding ``table.hoverable-rows``;
  * each sold row is ``date | image | title | numeric(price) | numeric.listed-price | thumb-down``
    — the price lives in ``td.numeric > span.js-price``, NOT a positional cell;
  * the title cell carries a ``[TCGPlayer]`` / ``[eBay]`` source marker;
  * the TCGPlayer product id is reachable only after URL-decoding an affiliate
    redirect href.

Regression context: a prior version read the price from ``td.price`` (which does
not exist) and fell back to the positional third cell (the *title*), so
``float()`` raised on every row and the parser silently returned zero sales.
"""
import pytest

from automana.core.services.app_integration.pricecharting.pc_sales_scrape_service import (
    _consensus_tcg_id,
    _detect_source,
    _parse_sales_page,
)

# A trimmed but structurally faithful PriceCharting card page.
_SALES_HTML = """
<html><body>
  <a class="js-tcgplayer-completed-sale"
     href="https://partner.tcgplayer.com/c/1/2/3?u=https%3A%2F%2Fwww.tcgplayer.com%2Fproduct%2F239857%2F-&subId1=x">buy</a>

  <!-- tab label: shares the grade class but must be skipped -->
  <div class="completed-auctions-used tab">Ungraded</div>

  <!-- content panel: the real data table -->
  <div class="completed-auctions-used">
    <table class="hoverable-rows"><tbody>
      <tr>
        <td class="date">2026-05-30</td>
        <td class="image"></td>
        <td class="title"><a href="/x">Ragavan Near Mint</a>[TCGPlayer]</td>
        <td class="numeric"><span class="js-price">$45.38</span></td>
        <td class="numeric listed-price"></td>
        <td class="thumb-down"></td>
      </tr>
      <tr>
        <td class="date">2026-05-28</td>
        <td class="image"></td>
        <td class="title"><a href="/y">Ragavan MH2</a>[eBay]</td>
        <td class="numeric"><span class="js-price">$39.99</span></td>
        <td class="numeric listed-price"></td>
        <td class="thumb-down"></td>
      </tr>
      <tr>
        <!-- malformed: no parseable price -> must be skipped, not crash -->
        <td class="date">2026-05-27</td>
        <td class="image"></td>
        <td class="title"><a href="/z">Best offer</a></td>
        <td class="numeric"><span class="js-price">Best Offer</span></td>
      </tr>
    </tbody></table>
  </div>

  <div class="completed-auctions-graded tab">Graded</div>
  <div class="completed-auctions-graded">
    <table class="hoverable-rows"><tbody>
      <tr>
        <td class="date">2026-05-29</td>
        <td class="image"></td>
        <td class="title"><a href="/g">Ragavan PSA 9</a>[eBay]</td>
        <td class="numeric"><span class="js-price">$120.00</span></td>
      </tr>
    </tbody></table>
  </div>
</body></html>
"""


@pytest.fixture
def parsed():
    return _parse_sales_page(_SALES_HTML, product_id="2254550")


def test_extracts_all_valid_rows(parsed):
    # 2 ungraded valid + 1 graded valid; the malformed-price row is dropped.
    assert len(parsed["sales"]) == 3


def test_price_comes_from_numeric_cell_not_title(parsed):
    """Regression: price must be read from td.numeric>span.js-price in cents."""
    prices = sorted(s["price_cents"] for s in parsed["sales"])
    assert prices == [3999, 4538, 12000]


def test_grade_labels_mapped(parsed):
    grades = sorted(s["grade"] for s in parsed["sales"])
    assert grades == ["grade9", "ungraded", "ungraded"]


def test_titles_taken_from_anchor_without_source_marker(parsed):
    titles = {s["title"] for s in parsed["sales"]}
    assert "Ragavan Near Mint" in titles
    assert not any("[TCGPlayer]" in t or "[eBay]" in t for t in titles)


def test_source_detected_per_row(parsed):
    by_price = {s["price_cents"]: s["source"] for s in parsed["sales"]}
    assert by_price[4538] == "tcgplayer"
    assert by_price[3999] == "ebay"
    assert by_price[12000] == "ebay"


def test_tab_label_div_is_skipped(parsed):
    # If the tab-label div were parsed, the ungraded rows would be double counted.
    ungraded = [s for s in parsed["sales"] if s["grade"] == "ungraded"]
    assert len(ungraded) == 2


def test_tcgplayer_id_decoded_from_affiliate_href(parsed):
    # Requires URL-decoding the redirect href before matching /product/{id}.
    assert parsed["tcgplayer_id"] == "239857"


def test_empty_page_yields_no_sales():
    out = _parse_sales_page("<html><body>no tables</body></html>", product_id="0")
    assert out["sales"] == []
    assert out["tcgplayer_id"] is None
    assert out["tcgplayer_id_votes"] == 0


# ── _consensus_tcg_id (per-listing votes vs page-level fallback) ──────────────
def test_consensus_prefers_majority_of_per_listing():
    tid, votes = _consensus_tcg_id("111111", ["239857", "239857", "239857", "999999"])
    assert tid == "239857"      # majority wins over the page-level link
    assert votes == 3


def test_consensus_falls_back_to_page_level_when_no_listings():
    tid, votes = _consensus_tcg_id("111111", [])
    assert tid == "111111"
    assert votes == 0


def test_consensus_none_when_nothing():
    assert _consensus_tcg_id(None, []) == (None, 0)


@pytest.mark.parametrize(
    "markup,expected",
    [
        ('<td class="title">Card [TCGPlayer]</td>', "tcgplayer"),
        ('<td class="title">Card [eBay]</td>', "ebay"),
        ('<td class="title"><a href="https://www.tcgplayer.com/p">Card</a></td>', "tcgplayer"),
        ('<td class="title"><a href="https://www.ebay.com/itm/1">Card</a></td>', "ebay"),
        ('<td class="title">Card with no marker</td>', "unknown"),
    ],
)
def test_detect_source(markup, expected):
    from bs4 import BeautifulSoup

    td = BeautifulSoup(markup, "html.parser").find("td")
    assert _detect_source(td) == expected
