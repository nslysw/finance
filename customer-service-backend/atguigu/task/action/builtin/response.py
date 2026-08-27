from typing import Any

from jinja2 import Template
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from atguigu.domain.messages import BotMessage
from atguigu.domain.state import DialogueState
from atguigu.infrastructure.db_client import main_test
from atguigu.task.action.base import Action, ActionResult
from atguigu.infrastructure.llm_client import llm_client
from atguigu.chat_history.builder import ChatHistoryBuilder


class ActionResponse(Action):
    name = "action_response"

    async def run(self, action_kwargs: dict[str, Any], state: DialogueState) -> ActionResult:
        """
        根据action_kwargs的文本内容，解析占位，封装到ActionResult的messages中BotMessage内容
        职责：响应YAML文件内容（user_flows.yml以及system_flows.yml中的action_response的args中内容展示出来）
        展示的内容注意以下几点：
        1. 展示的结构是什么类型：dict/str
        2. 展示的内容（字符串）：
        2.1 有需要格式化的变量：
            ①：例如 "好的，我们先处理{{ context.started_flow_name }}"。(占位特点是双{{}}占位：jinja2模版)变量名有context
            ②：例如 "订单{{ slots.order_number }}当前状态是：{{ slots.order_status }}。{{ slots.order_summary }}" (占位特点是双{{}}占位：jinja2模版)变量名有slots
        2.2 没有需要格式化的变量： 例如："请简单说一下退款原因"
        
        Args:
            action_kwargs: 
            state: 

        Returns:

        """

        # 1. 获取响应模式
        mode = action_kwargs.get('mode', 'static')

        # 2. 获取要展示的文本（占位）

        # 3. 判断模式
        text = action_kwargs['text']
        if mode == "rephrase":
            # a) 获取提示词
            prompt = action_kwargs['prompt']

            # b) 渲染的文本目标
            render_text = self._render_text(text, state)

            # c) 调用LLM
            rewritten = await self._call_llm(prompt, state, render_text)

            return ActionResult(messages=[BotMessage(text=rewritten)])

        elif mode == "generate":
            # a) 获取提示词

            prompt = action_kwargs['prompt']
            # b) 调用LLM
            rewritten = await self._call_llm(prompt, state, render_text="")

            return ActionResult(messages=[BotMessage(text=rewritten)])

        else:
            render_text = self._render_text(text, state)
            return ActionResult(messages=[BotMessage(text=render_text)])

    def _render_text(self,
                     text: str,
                     state: DialogueState) -> str:
        pass
        """
        职责：格式化响应文本中的变量
        Args:
            text:
        Returns:

        """
        template = Template(text)
        rendered_text = template.render(slots=state.active_task.slots if state.active_task is not None else None,
                                        context=state.active_system_task)
        return rendered_text

    async def _call_llm(self,
                        prompt_template_str: str,
                        state: DialogueState,
                        render_text="") -> str:

        prompt_template = PromptTemplate.from_template(template=prompt_template_str)

        chain = prompt_template | llm_client | StrOutputParser()

        result = await  chain.ainvoke({
            "history": ChatHistoryBuilder.build(state.current_session().turns[-5:]),
            "user_message": ChatHistoryBuilder.build_user_message_str(state.pending_turn.user_message),
            "current_response": render_text

        })

        return result


if __name__ == '__main__':
    template = Template("abc")
    rendered_text = template.render(context=None)
    print(rendered_text)
