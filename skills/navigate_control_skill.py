#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
navigate_control_skill.py
导航控制 Skill：支持开始、暂停、停止路径跟踪
发布 /waypoints_control (std_msgs/String)
"""

import rospy
from std_msgs.msg import String
from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult


class NavigateControlSkill(BaseSkill):
    """
    导航控制 Skill
    - start: 开始/继续路径跟踪
    - pause: 暂停当前导航
    - stop:  停止并清空当前路径
    """

    def __init__(self):
        super().__init__()
        self.name = "navigate_control"
        self.pub = rospy.Publisher('/waypoints_control', String, queue_size=1, latch=True)

    def get_description(self) -> str:
        return "导航控制：开始(start)、暂停(pause)、停止(stop)当前路径跟踪"

    def get_parameters(self) -> dict:
        return {
            "action": {
                "type": "string",
                "description": "控制指令：start(开始/继续)、pause(暂停)、stop(停止)",
                "required": True,
                "enum": ["start", "pause", "stop"]
            }
        }

    def execute(self, params: dict) -> SkillResult:
        action = params.get("action", "").strip().lower()

        if action not in ("start", "pause", "stop"):
            return SkillResult(
                False,
                f"无效的控制指令: {action}，仅支持 start / pause / stop",
                error="invalid_action"
            )

        # 发布控制指令
        msg = String(data=action)
        self.pub.publish(msg)

        # 中文反馈映射
        action_map = {
            "start": "▶️ 已发送开始命令",
            "pause": "⏸️ 已发送暂停命令",
            "stop": "🛑 已发送停止命令"
        }

        rospy.loginfo(f"[NavigateControl] {action_map[action]} → /waypoints_control")
        return SkillResult(True, action_map[action], data={"action": action})