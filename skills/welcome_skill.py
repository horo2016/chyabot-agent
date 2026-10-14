#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
welcome_skill.py
智能欢迎 Skill：边缘触发 + 持续冷却 + 离开重置
"""

import rospy
import random
import time
from std_msgs.msg import String, Bool
from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult


class WelcomeSkill(BaseSkill):
    def __init__(self):
        super().__init__()
        self.name = "welcome"
        
        # 配置
        self.enabled = True
        self.cooldown = 20.0           # 持续有人时的冷却间隔
        self.stop_keywords = ["不用播报", "停止欢迎", "别说话", "安静", "闭嘴", "不要播报"]
        self.start_keywords = ["开始欢迎", "恢复播报", "继续欢迎", "开启欢迎"]
        self.welcome_texts = [
            "欢迎光临弹弓科技",
            "您好，请问有什么可以帮您",
            "欢迎光临，很高兴见到您",
            "您好，欢迎来到弹弓科技"
        ]
        
        # 状态机
        self.state = "NO_PERSON"       # NO_PERSON | HAS_PERSON
        self.last_speak_time = 0.0
        self.last_person_time = 0.0    # 上次看到人的时间（用于判断离开）
        self.person_timeout = 2.0      # 超过2秒没看到人，认为人离开了
        
        # ROS
        self.person_sub = None
        self.tts_pub = None
        self.input_sub = None
        
    def get_description(self) -> str:
        return "智能欢迎系统：检测到新人时播报，持续有人20s冷却，人离开后重置，支持语音控制启停"
        
    def get_parameters(self) -> dict:
        return {
            "enabled": {
                "type": "boolean",
                "description": "是否默认启用",
                "required": False,
                "default": True
            },
            "cooldown": {
                "type": "number",
                "description": "持续有人时的播报间隔（秒）",
                "required": False,
                "default": 20.0
            },
            "welcome_text": {
                "type": "string",
                "description": "欢迎语，多个用 | 分隔",
                "required": False,
                "default": "欢迎光临弹弓科技|您好，请问有什么可以帮您|欢迎光临，很高兴见到您"
            }
        }
        
    def execute(self, params: dict) -> SkillResult:
        self.enabled = params.get("enabled", self.enabled)
        self.cooldown = params.get("cooldown", self.cooldown)
        
        texts = params.get("welcome_text", "")
        if texts:
            self.welcome_texts = [t.strip() for t in texts.split("|") if t.strip()]
        
        self.person_sub = rospy.Subscriber("/vision/person_detected", Bool, self._on_person)
        self.tts_pub = rospy.Publisher("/voice/tts_text", String, queue_size=1)
        self.input_sub = rospy.Subscriber("/agent/input", String, self._on_input)
        
        rospy.loginfo(
            f"🎉 Welcome Skill 启动: enabled={self.enabled}, "
            f"cooldown={self.cooldown}s, 状态机模式"
        )
        return SkillResult(True, "智能欢迎已启动")
        
    def cancel(self):
        if self.person_sub:
            self.person_sub.unregister()
        if self.input_sub:
            self.input_sub.unregister()
        rospy.loginfo("🛑 Welcome Skill 已停止")
        
    def _on_person(self, msg: Bool):
        """状态机处理人员检测"""
        has_person = msg.data
        now = time.time()
        
        if has_person:
            self.last_person_time = now
            
            if not self.enabled:
                return
                
            if self.state == "NO_PERSON":
                # 新人出现 → 立即播报
                self._speak_welcome()
                self.state = "HAS_PERSON"
                self.last_speak_time = now
                
            elif self.state == "HAS_PERSON":
                # 持续有人 → 检查冷却
                elapsed = now - self.last_speak_time
                if elapsed >= self.cooldown:
                    self._speak_welcome()
                    self.last_speak_time = now
                else:
                    rospy.logdebug(f"⏳ 持续有人，冷却中 {self.cooldown - elapsed:.1f}s")
        else:
            # 没人，检查是否离开
            if self.state == "HAS_PERSON":
                gone_time = now - self.last_person_time
                if gone_time >= self.person_timeout:
                    rospy.loginfo("👋 人员离开，重置状态")
                    self.state = "NO_PERSON"
                    
    def _speak_welcome(self):
        """播报欢迎语"""
        text = random.choice(self.welcome_texts)
        rospy.loginfo(f"🎉 播报: {text}")
        self.tts_pub.publish(text)
        
    def _on_input(self, msg: String):
        """语音控制启停"""
        text = msg.data.strip()
        
        if any(kw in text for kw in self.stop_keywords):
            if self.enabled:
                self.enabled = False
                self.tts_pub.publish("好的，我将停止欢迎播报")
                rospy.loginfo("🔇 Welcome Skill 已禁用")
            return
                
        if any(kw in text for kw in self.start_keywords):
            if not self.enabled:
                self.enabled = True
                self.tts_pub.publish("好的，恢复欢迎播报")
                rospy.loginfo("🔔 Welcome Skill 已启用")
            return