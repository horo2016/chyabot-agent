#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import rospy
import json
from std_msgs.msg import String
from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult


class ArmElevatorSkill(BaseSkill):
    def __init__(self):
        super().__init__()
        self.pub = rospy.Publisher('/arm/elevator/command', String, queue_size=1)
        # 合法的 action 取值，用于校验：按下 / 抬起
        self.valid_actions = ['press', 'release', 'press_and_release']

    def get_description(self) -> str:
        return "控制机械臂按下/抬起电梯面板按钮，支持单步按下、单步抬起和完整的点按动作"

    def get_parameters(self) -> dict:
        return {
            'action': {
                'type': 'string',
                'description': '机械臂操作类型，可选值：press（按下并保持）、release（抬起）、press_and_release（点按：按下后自动抬起）',
                'required': True,
                'enum': ['press', 'release', 'press_and_release']
            },
            'position': {
                'type': 'string',
                'description': '目标按钮位置标识，LLM从用户指令中提取，如"1F_up"（一楼上行）、"B1"（负一楼）、"15F_down"',
                'required': True
            },
            'force': {
                'type': 'number',
                'description': '按压力度（N），仅在机械臂支持力控时生效，缺省时使用安全默认值',
                'required': False
            },
            'duration': {
                'type': 'number',
                'description': '按下保持时长（秒），仅对 press 和 press_and_release 有效，缺省为安全值',
                'required': False
            }
        }

    def execute(self, params: dict) -> SkillResult:
        action = params.get('action', '').strip()

        # 校验 action 合法性
        if not action:
            return SkillResult(False, "操作类型不能为空", error="empty_action")
        if action not in self.valid_actions:
            return SkillResult(
                False,
                f"非法的操作类型 '{action}'，仅支持: {', '.join(self.valid_actions)}",
                error="invalid_action"
            )

        # 校验 position 合法性（先校验、后执行）
        position = params.get('position', '').strip()
        if not position:
            rospy.logerr("❌ 缺少 position 参数，无法定位目标按钮")
            return SkillResult(
                False,
                "操作电梯按钮需要提供目标按钮位置",
                error="missing_position"
            )

        # 构造指令
        command = {"action": action, "position": position}

        # 可选参数：力度与保持时长（由底层控制端做限幅，保证安全）
        force = params.get('force')
        if force is not None:
            command['force'] = force
        duration = params.get('duration')
        if duration is not None:
            command['duration'] = duration

        if action == 'press':
            message = f"机械臂正在按下 {position} 按钮"
        elif action == 'release':
            message = f"机械臂已从 {position} 按钮抬起"
        elif action == 'press_and_release':
            message = f"机械臂已点按 {position} 按钮"
        else:
            # 防御性编程，理论上不会到达此处
            return SkillResult(False, "未知的操作类型", error="unknown_action")

        # 发布 JSON 指令到 /arm/elevator/command
        try:
            cmd_msg = String()
            cmd_msg.data = json.dumps(command, ensure_ascii=False)
            self.pub.publish(cmd_msg)

            rospy.loginfo(f"🦾 机械臂电梯指令已发送: {cmd_msg.data}")
            return SkillResult(True, message, data=command)

        except Exception as e:
            rospy.logerr(f"❌ 发送机械臂指令失败: {e}")
            return SkillResult(False, "机械臂指令发送失败", error="publish_failed")

    def cancel(self) -> SkillResult:
        """响应上层调度器的取消指令：立即中断机械臂运动"""
        cancel_msg = String()
        cancel_msg.data = json.dumps({"action": "cancel"}, ensure_ascii=False)
        self.pub.publish(cancel_msg)
        rospy.logwarn("🛑 机械臂电梯操作已被取消，执行急停")
        return SkillResult(True, "机械臂操作已取消", data={"action": "cancel"})
