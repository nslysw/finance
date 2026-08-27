from atguigu.domain.messages import BotMessage
from atguigu.domain.state import DialogueState
from atguigu.knowledge.intents import KnowledgeIntent
from atguigu.knowledge.provider.register import KnowledgeRegister
from atguigu.knowledge.resonder import KnowledgeResponder


class KnowledgeHandler:
    def __init__(self,
                 knowledge_intents: dict[str, KnowledgeIntent],
                 knowledge_register: KnowledgeRegister,
                 knowledge_responder: KnowledgeResponder
                 ):
        self.knowledge_intents = knowledge_intents
        self.knowledge_register = knowledge_register
        self.knowledge_responder = knowledge_responder

    async def handle(self,
                     intents: list[str],
                     state: DialogueState) -> list[BotMessage]:
        """
        职责：根据知识意图查询提供者的检索结果，并且通过LLM润色返回
        Args:
            intents:
            state:

        Returns:

        """

        # 1. 根据知识意图查询提供者ID
        provider_ids = self._get_provider_ids_by_intents(intents)

        # 2. 根据提供者ID 查询提供者对象
        final_chunks = []
        for provider_id in provider_ids:
            provider = self.knowledge_register.get_provider_by_id(provider_id)
                # 3. 调用提供者的检索方法
            knowledge_chunks = await provider.retrival(state=state)
            final_chunks.extend(knowledge_chunks)

        # 4. 将检索结果交给LLM使用

        bot_messages = await self.knowledge_responder.response(final_chunks, state)

        # 5. 封装数据结果返回
        return bot_messages

    def _get_provider_ids_by_intents(self, intents: list[str]) -> list[str]:
        """
        职责：根据知识意图查询提供者ID
        Args:
            intents:

        Returns:

        """

        final_providers = []
        for intent in intents:
            knowledge_intent_obj = self.knowledge_intents[intent]

            final_providers.extend(knowledge_intent_obj.provider_ids)

        return list(set(final_providers))
