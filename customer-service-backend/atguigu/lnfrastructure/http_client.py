import asyncio

from httpx import AsyncClient

"""
定义HTTP客户端（异步）
"""

http_client:AsyncClient|None =None

#初始化http_client资源
def init_http_client():
    global http_client
    http_client = AsyncClient(timeout=120,trust_env=False)


#释放http_client资源
async def disposed_http_client():
    await http_client.aclose()

async def main_test():
    init_http_client()

    response = await http_client.get(url="http://192.168.200.128:18081/orders/A20260408002")

    print(response.json())
    data=response.json()["data"]

    print(data)

if __name__=="__main__":
    asyncio.run(main_test())