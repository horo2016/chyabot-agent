#!/usr/bin/env python3
import rospy
from std_msgs.msg import String
import json
import time
import threading
from typing import Dict, List

from choyabot_agent_framework.core.skill_registry import SkillRegistry
from choyabot_agent_framework.core.memory import MemoryStore, MemoryEntry
from choyabot_agent_framework.core.planner import LLMPlanner
from choyabot_agent_framework.core.config_manager import ConfigManager


class RobotAgent:
    def __init__(self):
        rospy.init_node('choyabot_agent', anonymous=True)
        
        self.session_id = rospy.get_param('~session_id', f"session_{int(time.time())}")
        self.llm_url = rospy.get_param('~llm_url', 'http://localhost:11434/v1/chat/completions')
        self.llm_model = rospy.get_param('~llm_model', 'qwen2.5:7b')
        
        # 加载配置
        self.cfg = ConfigManager()
        self.session_id = rospy.get_param('~session_id', f"session_{int(time.time())}")
        
        # 从配置文件读取 LLM 配置
        self.llm_url = rospy.get_param('~llm_url', self.cfg.get('llm.url'))
        self.llm_model = rospy.get_param('~llm_model', self.cfg.get('llm.model'))
        self.llm_key = rospy.get_param('~llm_key', self.cfg.get('llm.key'))
        
        rospy.loginfo(f"🧠 LLM: {self.cfg.get_llm_display()}")
        
        self.skills = SkillRegistry()
        discovered = self.skills.discover()
        rospy.loginfo(f"🔍 扫描到的技能文件: {discovered}")
 
        self.skills.load_all()
        
        self.memory = MemoryStore()
        self.planner = LLMPlanner(self.llm_url, self.llm_model,self.llm_key)
        
        self.input_sub = rospy.Subscriber('/agent/input', String, self.on_input)
        self.status_pub = rospy.Publisher('/agent/status', String, queue_size=10)
        self.tts_pub = rospy.Publisher('/voice/tts_text', String, queue_size=10)
        
        self.running = True
        rospy.loginfo(f"🤖 ChoyaBot Agent 启动 | Session: {self.session_id}")
        rospy.loginfo(f"   技能: {list(self.skills._skills.keys())}")
        # 启动常驻型 Skill（如语音）
        self._start_persistent_skills()
        
    def _start_persistent_skills(self):
        """启动标记为 persistent 的 Skill"""
        for name, skill in self.skills._skills.items():
            cfg = skill.config or {}
            if cfg.get('persistent', False) or cfg.get('timeout', 30) == 0:
                rospy.loginfo(f"🚀 启动常驻 Skill: {name}")
                
                # 把 YAML 参数 schema 转成扁平运行时参数
                runtime_params = {}
                for key, val in cfg.get('parameters', {}).items():
                    if isinstance(val, dict):
                        runtime_params[key] = val.get('default')
                    else:
                        runtime_params[key] = val
                
                result = skill.execute(runtime_params)
                if not result.success:
                    rospy.logerr(f"❌ {name} 启动失败: {result.message}")
    def on_input(self, msg):
        text = msg.data
        rospy.loginfo(f"📥 输入: {text}")
        self.memory.add(MemoryEntry(None, self.session_id, 'user', text, {'type': 'voice'}, time.time()))
        self.process(text)
        
    def process(self, text: str):
        self._publish_status('planning')
        
        skills_desc = self.skills.get_descriptions_for_llm()
         # 🔍 打印 LLM 看到的技能描述
        rospy.loginfo(f"📋 skills_desc:\n{skills_desc}")
        recent = self.memory.get_recent(self.session_id, limit=10)
        memory_ctx = self._format_memory(recent)
        
        plan_data = self.planner.plan(text, skills_desc, memory_ctx)
        
        if plan_data is None:
            self._speak("抱歉，我暂时无法处理")
            self._publish_status('idle')
            return
            
        reply = plan_data.get('reply', '收到')
        self._speak(reply)
        
        self.memory.add(MemoryEntry(None, self.session_id, 'assistant', reply, {'plan': plan_data.get('plan', [])}, time.time()))
        
        plan = plan_data.get('plan', [])
        if plan:
            self.execute_plan(plan)
        else:
            self._publish_status('idle')
            
    def execute_plan(self, plan: List[Dict]):
        self._publish_status('executing')
        
        for step in plan:
            if not self.running:
                break
                
            skill_name = step.get('skill')
            params = step.get('params', {})
            
            skill = self.skills.get(skill_name)
            if skill is None:
                rospy.logerr(f"❌ 未知技能: {skill_name}")
                continue
                
            valid, err = skill.validate_params(params)
            if not valid:
                rospy.logerr(f"❌ 参数错误: {err}")
                self._speak(f"参数错误: {err}")
                continue
                
            rospy.loginfo(f"🔧 执行: {skill_name}({params})")
            self._publish_status(f'executing:{skill_name}')
            
            skill.pre_execute(params)
            result = skill.execute(params)
            skill.post_execute(result)
            
            self.memory.add(MemoryEntry(None, self.session_id, 'system', f"{skill_name}: {result.message}",
                                        {'skill': skill_name, 'success': result.success}, time.time()))
            
            if not result.success:
                rospy.logerr(f"❌ 失败: {result.error}")
                self._speak(f"执行失败: {result.message}")
                break
                
        self._publish_status('idle')
        
    def _format_memory(self, entries: List[MemoryEntry]) -> str:
        if not entries:
            return ""
        lines = ["历史对话："]
        for e in entries:
            lines.append(f"- {e.role}: {e.content}")
        return "\n".join(lines)
        
    def _speak(self, text: str):
        if text:
            self.tts_pub.publish(text)
            
    def _publish_status(self, status: str):
        self.status_pub.publish(status)
        
    def run(self):
        rospy.spin()
        
    def stop(self):
        self.running = False
        self.skills.stop()