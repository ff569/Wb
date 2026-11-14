import re

CATALOG_PATTERN = re.compile(r"catalog/(\d{4,12})")
BARE_ARTICLE_PATTERN = re.compile(r"^(\d{4,12})$")

WB_URL_TEMPLATE = "https://www.wildberries.ru/catalog/{nm}/detail.aspx"


def parse_article(text: str) -> int | None:
    """Extract WB article number from a link or a bare number."""
    match = CATALOG_PATTERN.search(text)
    if match:
        return int(match.group(1))
    match = BARE_ARTICLE_PATTERN.match(text.strip())
    if match:
        return int(match.group(1))
    return None


def parse_target(text: str) -> int:
    """Extract trailing target price: 'https://... 1500' -> 1500."""
    match = re.search(r"\s(\d{2,7})\s*$", text.strip())
    return int(match.group(1)) if match else 0


def split_link_and_target(text: str) -> tuple[int | None, int]:
    """Return (article, target_price) from a user message."""
    article = parse_article(text)
    if article is None:
        return None, 0
    target = parse_target(text)
    return article, target


def product_url(nm: int) -> str:
    return WB_URL_TEMPLATE.format(nm=nm)
