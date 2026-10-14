#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import rospy
import json
from std_msgs.msg import String
from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult


class ElevatorSkill(BaseSkill):
    def __init__(self):
        super().__init__()
        self.pub = rospy.Publisher('/elevator/command', String, queue_size=1)
        # 合法的 action 取值，用于校验
        self.valid_actions = ['press_up', 'press_down', 'go_floor']
        
    def get_description(self) -> str:
        return "控制电梯系统完成楼层切换操作，支持按上下行按钮和前往指定楼层"
        
    def get_parameters(self) -> dict:
        return {
            'action': {
                'type': 'string',
                'description': '电梯操作类型，可选值：press_up（按上行按钮）、press_down（按下行按钮）、go_floor（前往指定楼层）',
                'required': True,
                'enum': ['press_up', 'press_down', 'go_floor']
            },
            'floor': {
                'type': 'string',
                'description': '目标楼层编号，仅在 action 为 go_floor 时必填，如"3"、"B1"、"15F"',
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
        
        # 构造指令
        command = {"action": action}
        
        if action == 'go_floor':
            floor = params.get('floor', '').strip()
            # 先校验、后执行：floor 参数缺失或为空时返回明确错误
            if not floor:
                rospy.logerr("❌ go_floor 操作缺少 floor 参数")
                return SkillResult(
                    False, 
                    "前往指定楼层需要提供楼层编号", 
                    error="missing_floor"
                )
            command['floor'] = floor
            message = f"正在前往 {floor} 层"
        elif action == 'press_up':
            message = "已按下上行按钮"
        elif action == 'press_down':
            message = "已按下下行按钮"
        else:
            # 防御性编程，理论上不会到达此处
            return SkillResult(False, "未知的操作类型", error="unknown_action")
        
        # 发布 JSON 指令到 /elevator/command
        try:
            cmd_msg = String()
            cmd_msg.data = json.dumps(command, ensure_ascii=False)
            self.pub.publish(cmd_msg)
            
            rospy.loginfo(f"🛗 电梯指令已发送: {cmd_msg.data}")
            return SkillResult(True, message, data=command)
            
        except Exception as e:
            rospy.logerr(f"❌ 发送电梯指令失败: {e}")
            return SkillResult(False, "电梯指令发送失败", error="publish_failed")