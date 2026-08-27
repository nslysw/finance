from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser

from atguigu.config.settings import settings


"""
通过LangChain定义LLM客户端
模块之间的组件导入的标准写法：
1.导入sdk自带的
2.导入第三方的
3.导入自己定义
"""

llm_client: BaseChatModel = init_chat_model(
    model_provider="openai",
    model=settings.llm_model,
    api_key=settings.llm_api_key,
    base_url=settings.llm_base_url

)


async def main_test():
    pass


if __name__ == "__main__":
    """
    流式调用：stream：同步的流式    astream:异步流式
    非流式调用：invoke:同步非流式   ainvoke:异步非流式
    Runnable组件提供的：抽象接口：定义常用的三组方法 batch  abatch
    :return:
    """

    chain = llm_client | StrOutputParser()

    content = chain.invoke("请安慰我一下")
    print(content)
