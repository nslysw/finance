"""
封装自定义action统一发请求的工具函数
"""



from urllib.parse import quote
from atguigu.config.settings import settings
from atguigu.infrastructure import http_client


def _base_url() -> str:
    """
    职责：获取中台服务的地址
    Returns:

    """
    return settings.commerce_api_base_url.rstrip("/")


def _extract_data(result: dict | None) -> dict | None:
    """
    职责：从响应结果中获取真实的字典数据
    Args:
        result:

    Returns:

    """
    data = result.get("data") if isinstance(result, dict) else None
    return data if isinstance(data, dict) else None


async def fetch_order(order_id: str) -> dict | None:
    """
    职责：根据订单ID 获取订单的数据
    Args:
        order_id:

    Returns:

    """
    try:
        r = await http_client.http_client.get(f"{_base_url()}/orders/{quote(order_id)}")
        return _extract_data(r.json())
    except Exception:
        return None


async def fetch_logistics(order_id: str) -> dict | None:
    """
     职责：根据订单ID 获取订单物流的数据
    Args:
        order_id:

    Returns:

    """
    try:
        r = await http_client.http_client.get(f"{_base_url()}/orders/{quote(order_id)}/logistics")
        return _extract_data(r.json())
    except Exception:
        return None


async def fetch_product(product_id: str) -> dict | None:
    """
    职责： 根据商品ID 获取商品的数据
    Args:
        product_id:

    Returns:

    """
    try:
        r = await http_client.http_client.get(f"{_base_url()}/products/{quote(product_id)}")
        return _extract_data(r.json())
    except Exception:
        return None