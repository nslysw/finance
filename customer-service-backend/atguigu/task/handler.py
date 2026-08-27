from atguigu.domain.messages import BotMessage
from atguigu.domain.state import DialogueState
from atguigu.task.action.runner import ActionRunner
from atguigu.task.commands.command import Command
from atguigu.task.commands.processor import CommandProcessor
from atguigu.task.flows.executor import FlowExecutor
from atguigu.task.flows.flows import FlowList


class TaskHandler:

    def __init__(self,
                 flow_list: FlowList,
                 command_processor: CommandProcessor,
                 flow_executor: FlowExecutor,
                 action_runner: ActionRunner
                 ):
        self.flow_list = flow_list
        self.command_processor = command_processor
        self.flow_executor = flow_executor
        self.action_runner = action_runner

    async def handle(self,
                     commands: list[Command],
                     dialogue_state: DialogueState) -> list[BotMessage]:
        """
        职责：业务流程处理器处理业务流程
        1. 使用CommandProcessor修改state中和流程任务相关的属性（改状态）
        2、使用FlowExecutor 读取state中的任务属性，从而推进业务流程以及系统流程 (读状态)  T
        Args:
            commands:
            dialogue_state:

        Returns:

        """

        # 1. 修改状态
        self.command_processor.process_command(commands, dialogue_state, self.flow_list)

        # 2. 读状态
        bot_messages = await self.flow_executor.execute_flow(
            dialogue_state,
            action_runner=self.action_runner,
            flow_list=self.flow_list)

        return bot_messages
