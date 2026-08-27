from dataclasses import asdict

from atguigu.domain.contexts import SystemCollectInformationContext
from atguigu.domain.messages import BotMessage
from atguigu.domain.state import DialogueState
from atguigu.task.action.runner import ActionRunner, ActionCall
from atguigu.task.flows.flows import FlowList
from atguigu.task.flows.links import FlowStepStaticLink, FlowStepConditionLink, FlowStepFallbackLink
from atguigu.task.flows.steps import FlowStep, StartFlowStep, EndFlowStep, ActionFlowStep, CollectionFlowStep


class FlowExecutor:

    async def execute_flow(self,
                           state: DialogueState,
                           *,
                           action_runner: ActionRunner,
                           flow_list: FlowList) -> list[BotMessage]:
        """
        职责：推进两份YAML中流程。目标：推进业务流程【顺便推进系统流程】
        两层循环：
        内层循环：find找action
        外层循环：execute执行action

        特点：
        1. 两个yaml中的流程在推进期间可能出现交替。
        2. 推进业务、系统流程的分界线是步骤类型为Action
        3. 遇到步骤类型是Action,都需要先停止。
        4. 步骤类型是Action 且名字是action_response或者action_xxx的时候，都需要通过action_runner找到action,执行action,获取槽位的更新值或者回复响应之后，在推进流程的后续步骤。
        5. 步骤类型是Action 名字是action_listen， 先把action_response的响应内容返回出去，然后用户填写槽位信息，等用户信息填写完毕，在推进流程的后续步骤。
        Args:
            state:
            action_runner:
            flow_list:

        Returns:

        """

        final_response_messages: list[BotMessage] = []
        while True:

            # 1. 找流程步骤是Action
            action_call = self._advance_flow_util_action(state, flow_list)

            # 2. action名字是listen
            if action_call.action_name == "action_listen":
                break

            # 3.action名字是action_response 或者action_xxx
            action_result = await action_runner.run(action_call, state)
            final_response_messages.extend(action_result.messages)
            state.set_slots(action_result.updated_slots)

        return final_response_messages

    def _advance_flow_util_action(self,
                                  state: DialogueState,
                                  flow_list: FlowList) -> ActionCall:
        """
        职责：推进流程并且在推进流程期间找步骤类型是action
        如果执行流程期间步骤类型不是action,继续执行下一步流程（继续推进流程）
        如果执行流程期间步骤类型是action,不能继续推，要构建action_call 并且返回
        Args:
            state:
            flow_list:

        Returns:

        """

        while True:
            # 1. 获取要推进的流程的上下文
            current_task = state.current_task()
            if current_task is None:
                return ActionCall(action_name="action_listen")

            # 2. 从上下文中流程ID(一个属性 双重身份)
            flow_id = current_task.flow_id

            # 3. 获取流程对象
            flow = flow_list.get_flow_by_id(flow_id)

            # 4. 获取步骤ID
            step_id = current_task.step_id

            # 5. 获取步骤对象
            step = flow.get_step_by_id(step_id)

            # 6. 运行步骤
            action_call = self._run_step(step, state)

            if action_call is not None:
                return action_call

    def _run_step(self,
                  step: FlowStep,
                  state: DialogueState) -> ActionCall | None:
        """
        职责：运行步骤
        Args:
            step:
            state:
            flow_list:

        Returns:

        """

        if isinstance(step, StartFlowStep):
            return self._run_start_step(step, state)
        elif isinstance(step, EndFlowStep):
            return self._run_end_step(state)
        elif isinstance(step, ActionFlowStep):
            return self._run_action_step(step, state)
        elif isinstance(step, CollectionFlowStep):
            return self.run_collection_step(step, state)
        else:
            return None

    def _run_start_step(self,
                        step: StartFlowStep,
                        state: DialogueState) -> None:
        """
        职责：运行步骤类型是start，什么都不用干，找到下一个步骤ID,更新到state中的流程上下文中
        Args:
            step:
            state:
            flow_list:

        Returns:
        """

        #  1. 推进下一步
        self._advance_next_step(step, state)

        # 2. 返回None
        return None

    def _advance_next_step(self,
                           step: FlowStep,
                           state: DialogueState):

        # 1. 找step_id
        next_step_id = self._find_next_step_id(step, state)

        # 2. 更新step_id
        state.current_task().step_id = next_step_id

    def _find_next_step_id(self,
                           step: FlowStep,
                           state: DialogueState) -> str:

        for link in step.next:
            if isinstance(link, FlowStepStaticLink):
                return link.target  # step_id
            elif isinstance(link, FlowStepConditionLink):
                # 1. 计算条件表的条件
                if self._eval_condition(link.condition, state):
                    return link.target  # step_id
            elif isinstance(link, FlowStepFallbackLink):
                return link.target  # step_id

        return ""

    def _eval_condition(self,
                        condition_expr: str,
                        state: DialogueState) -> bool:
        """
        condition_expr="context.get('reason') == 'clarification_rejected'"
        Args:
            condition:
            step:
            state:


        Returns:

        """

        data = {
            "context": asdict(state.active_system_task) if state.active_system_task is not None else {},
            "slots": state.active_task.slots if state.active_task is not None else {}
        }

        return eval(condition_expr, {}, data)

    def _run_end_step(self,
                      state: DialogueState) -> None:
        """
        职责： 清空对应的流程上下文
        特点：不需要调用_advance_next_step方法
        Args:
            step:
            state:

        Returns:

        """

        if state.active_system_task is not None:
            state.end_system_task()
        elif state.active_task is not None:
            state.end_active_task()
        else:
            pass

        return None

    def _run_action_step(self,
                         step: ActionFlowStep,
                         state: DialogueState) -> ActionCall:
        """
        职责：构建ActionCall对象返回
        特点：需要调用_advance_next_step方法
        Args:
            step:
            state:

        Returns:

        """

        # 1. 推进下一步
        self._advance_next_step(step, state)

        # 2. 构建ActionCall返回
        action_kwargs = step.args

        if isinstance(action_kwargs, str):
            # system_collect_information系统流程 args: context.response 转成字典（dict） 归一化思想
            action_kwargs = asdict(state.active_system_task)['response']

        return ActionCall(action_name=step.action, action_kwargs=action_kwargs)

    def run_collection_step(self,
                            step: CollectionFlowStep,
                            state: DialogueState) -> ActionCall | None:
        """
        职责：让用户填写业务流程缺少的槽位信息
        特点①：
        步骤类型是collect的，永远只出现在当前两个yml文件中的user_flows.yml中 【收集槽位本质属于业务侧】
        特点②：run_collection_step方法会被触发两次。
        为什么触发两次：希望对用户填写后的槽位信息做校验。主要是为了在配置文件中如何使用validated 校验开关
        1. 让用填写槽位信息，触发第一次------返回None,内层循环继续执行（current_task）但是不能推进下一步（_advance_next_step）
        2. 校验用户填写的槽位信息  触发第二次(校验成功、校验失败)
        校验成功：执行下一步：调用_advance_next_step  返回None
        校验失败：让用户在填写一次(填错的槽位移除掉，构建错误响应)
        Args:
            step:
            state:

        Returns:

        """

        self._try_fill_slots_from_object(step, state)

        if state.active_task.slots.get(step.slot_name):
            # 第二次： 校验用户填写的槽位信息
            if step.validated:
                if self._eval_condition(condition_expr=step.validated.condition, state=state):
                    self._advance_next_step(step, state)  # 推进下一步
                    return None  # 返回None
                else:
                    # a) 清空填错的槽位信息
                    state.remove_slot(step.slot_name)

                    # b) 给错误响应
                    if step.validated.failure_response:
                        return ActionCall(action_name="action_response",
                                          action_kwargs=asdict(step.validated.failure_response))
                    else:
                        return ActionCall(action_name="action_response",
                                          action_kwargs={"text": "你填写的槽位信息有误不合法，请重新填写"})

            else:
                self._advance_next_step(step, state)  # 推进下一步
                return None  # 返回None
        else:
            # 第一次 让用户填写槽位信息 激活system_collect_information系统流程
            state.start_system_task(SystemCollectInformationContext(
                flow_id="system_collect_information",
                step_id="start",
                response=asdict(step.response),
                slot_name=step.slot_name
            ))
            return None




    def _try_fill_slots_from_object(self,
                                    step:CollectionFlowStep,
                                    state:DialogueState):

        # 1. 判断当前是否存在正在执行的业务流程以及卡片信息
        if  state.active_task is None or state.focused_object is None:
            return

        # 2. 卡片类型和槽位的映射
        object_type_slots_mapping={
            "order":"order_number",
            "product":"product_id"
        }

        # 3. 获取期望的槽位
        expected_slot_name= object_type_slots_mapping.get(state.focused_object.type)

        # 4. 判读当前这一步缺少的槽位是否等于期望的槽位 且当前业务流程上下文中槽位还没有，才利用前面点击过的卡片
        if step.slot_name== expected_slot_name and not state.active_task.slots.get(step.slot_name) :
            state.set_slots({step.slot_name:state.focused_object.id})

