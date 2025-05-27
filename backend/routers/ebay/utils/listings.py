from backend.routers.ebay.models import listings
import xml.etree.ElementTree as ET

def parse_active_listings(xml_text: str) -> listings.ActiveListingResponse:
    ns = {'e': 'urn:ebay:apis:eBLBaseComponents'}
    root = ET.fromstring(xml_text)
    items = root.findall(".//e:Item", ns)

    listings = []
    for item in items:
        try:
            listing = listing.ActiveListing(
                item_id=item.find("e:ItemID", ns).text,
                title=item.find("e:Title", ns).text,
                buy_it_now_price=float(item.find("e:BuyItNowPrice", ns).text),
                currency=item.find("e:BuyItNowPrice", ns).attrib.get("currencyID"),
                start_time=item.find("e:ListingDetails/e:StartTime", ns).text,
                time_left=item.find("e:TimeLeft", ns).text,
                quantity=int(item.find("e:Quantity", ns).text),
                quantity_available=int(item.find("e:QuantityAvailable", ns).text),
                current_price=float(item.find("e:SellingStatus/e:CurrentPrice", ns).text),
                view_url=item.find("e:ListingDetails/e:ViewItemURL", ns).text,
                image_url=(item.find("e:PictureDetails/e:GalleryURL", ns).text
                           if item.find("e:PictureDetails/e:GalleryURL", ns) is not None else None)
            )
            listings.append(listing)
        except Exception as e:
            print(f"Error parsing item: {e}")

    return listings
