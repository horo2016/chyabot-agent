#!/usr/bin/env python3
import json
import requests
import logging
from pathlib import Path
from typing import Optional, Dict
import yaml
import rospy

class LLMPlanner:
    def __init__(self, api_url: str, model: str, api_key: str = ""):
        self.api_url = api_url
        self.model = model
        self.api_key = api_key
        self.headers = {"Content-Type": "application/json"}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self.logger = logging.getLogger(__name__)
        rospy.loginfo(f"🔧 LLMPlanner 初始化: url={api_url}, model={model}, key={'有' if api_key else '无'}")
        # 加载 prompt 配置
        self.prompt_cfg = self._load_prompt_config()
        
    def _load_prompt_config(self) -> Dict:
        """从 ~/.choya/prompts.yaml 加载 prompt 模板"""
        prompt_file = Path.home() / ".choya" / "prompts.yaml"
        rospy.loginfo(f" 加载 {prompt_file}，配置")
        if prompt_file.exists():
            
            try:
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                    return data.get("planner", {})
            except Exception as e:
                rospy.loginfo(f"⚠️ 加载 prompts.yaml 失败: {e}，使用默认配置")
        
        # 默认配置（兜底）
        return {
            "system_template": (
                "你是一个机器人任务规划助手。\n\n"
                "{skills_desc}\n\n"
                "规则：\n"
                "1. 每个步骤必须对应一个可用技能\n"
                "2. 参数必须严格符合 schema\n"
                "3. 复杂任务拆分为多个串行步骤\n\n"
                "返回严格 JSON：\n"
                '{{"thought": "...", "plan": [{{"skill": "...", "params": {{...}}}}], "reply": "..."}}\n\n'
                "{memory_context}"
            ),
            "temperature": 0.3,
            "max_tokens": 1024
        }
        
    def plan(self, user_input: str, skills_desc: str, memory_context: str = "") -> Optional[dict]:
        # 从配置读取模板并填充变量
        template = self.prompt_cfg.get("system_template", "")
        system = template.format(
            skills_desc=skills_desc,
            memory_context=memory_context if memory_context else ""
        )
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_input}
            ],
            "temperature": self.prompt_cfg.get("temperature", 0.3),
            "max_tokens": self.prompt_cfg.get("max_tokens", 1024),
            "response_format": {"type": "json_object"}
        }
        try:
            resp = requests.post(self.api_url, headers=self.headers, json=payload, timeout=30)
            #rospy.logwarn(f"📡 响应状态码: {resp.status_code}")
            
            resp.raise_for_status()
            resp_json = resp.json()
            #rospy.logwarn(f"📡 响应结构: {list(resp_json.keys())}")
            
            raw_content = resp_json["choices"][0]["message"]["content"]
            rospy.logwarn(f"📥 原始返回前200字: {raw_content[:500]}")
            
            return json.loads(raw_content)
            
        except requests.exceptions.RequestException as e:
            rospy.logerr(f"❌ HTTP 请求失败: {e}")
            return None
        except (json.JSONDecodeError, KeyError) as e:
            rospy.logerr(f"❌ 解析失败: {e}")
            return None
        except Exception as e:
            rospy.logerr(f"❌ ❌ LLM 规划失败: {e}")
            return None
        