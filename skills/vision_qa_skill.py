#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vision_qa_skill.py
视觉问答 Skill：订阅 /usb_camera/image_raw，调用多模态 LVM 回答视觉问题
独立配置 choya config get lvm，与 llm 互不冲突
"""

import rospy
import base64
import io
import threading
import requests
import os
import subprocess
import ast
from sensor_msgs.msg import Image
from std_msgs.msg import String

try:
    from cv_bridge import CvBridge
    CV_BRIDGE_AVAILABLE = True
except ImportError:
    CV_BRIDGE_AVAILABLE = False

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

import numpy as np

from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult


class VisionQASkill(BaseSkill):
    """
    视觉问答 Skill
    - 后台订阅 /usb_camera/image_raw 缓存最新帧
    - 独立读取 choya config get lvm（多模态视觉模型配置）
    - execute 接收 question，结合当前图像调用 LVM
    """

    def __init__(self):
        super().__init__()
        self.name = "vision_qa"
        
        # 图像缓存
        self.latest_image = None
        self.image_lock = threading.Lock()
        self.image_sub = None
        self.cv_bridge = None
        
        # LVM 配置（会被 _load_lvm_config 覆盖）
        self.api_base = ""
        self.api_key = ""
        self.model = ""
        self.max_tokens = 1024
        self.temperature = 0.3
        
        # ROS
        self.answer_pub = None
        
    def get_description(self) -> str:
        return "视觉问答：获取USB摄像头画面，调用多模态大模型回答你看到了什么、物体颜色、人物穿着等视觉问题"
        
    def get_parameters(self) -> dict:
        return {
            "question": {
                "type": "string",
                "description": "视觉问题，如'你看到了什么'、'这个人穿的什么颜色的上衣'、'前方有什么障碍物'",
                "required": True
            },
            "api_key": {
                "type": "string",
                "description": "临时覆盖 LVM API Key（默认自动读取 choya config get lvm）",
                "required": False,
                "default": ""
            },
            "model": {
                "type": "string",
                "description": "临时覆盖视觉模型名称（默认自动读取 choya config get lvm）",
                "required": False,
                "default": ""
            }
        }
    
    def _load_lvm_config(self) -> dict:
        """
        加载 LVM 配置，优先级：
        1. choya config get lvm（独立视觉模型配置）
        2. ROS param /choya/lvm/*
        3. 环境变量 CHOYA_LVM_*
        4. 环境变量 VISION_API_KEY（兜底）
        """
        cfg = {"url": "", "model": "", "key": ""}
        
        # 1. 尝试 choya config get lvm
        try:
            result = subprocess.run(
                ["choya", "config", "get", "lvm"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    parsed = ast.literal_eval(output)
                    if isinstance(parsed, dict):
                        cfg["url"] = parsed.get("url", "")
                        cfg["model"] = parsed.get("model", "")
                        cfg["key"] = parsed.get("key", "")
                        rospy.loginfo("✅ VisionQA: 已从 choya config 读取 LVM 配置")
                        return cfg
        except Exception as e:
            rospy.logdebug(f"choya config get lvm 读取失败: {e}")
        
        # 2. ROS param
        try:
            cfg = {
                "url": rospy.get_param("/choya/lvm/url", ""),
                "model": rospy.get_param("/choya/lvm/model", ""),
                "key": rospy.get_param("/choya/lvm/key", "")
            }
            if cfg["key"]:
                rospy.loginfo("✅ VisionQA: 已从 ROS param 读取 LVM 配置")
                return cfg
        except Exception:
            pass
        
        # 3. 环境变量
        cfg = {
            "url": os.getenv("CHOYA_LVM_URL", ""),
            "model": os.getenv("CHOYA_LVM_MODEL", ""),
            "key": os.getenv("CHOYA_LVM_KEY", os.getenv("VISION_API_KEY", ""))
        }
        if cfg["key"]:
            rospy.loginfo("✅ VisionQA: 已从环境变量读取 LVM 配置")
        return cfg
        
    def execute(self, params: dict) -> SkillResult:
        # 初始化 ROS（首次执行时）
        if self.image_sub is None:
            self._init_ros()
            
        # 检查依赖
        if not PIL_AVAILABLE:
            return SkillResult(False, "缺少依赖: pip install Pillow", error="missing_pillow")
        
        # 参数
        question = params.get("question", "").strip()
        if not question:
            return SkillResult(False, "问题不能为空", error="empty_question")
        
        # 加载 LVM 配置
        lvm_cfg = self._load_lvm_config()
        
        # 参数可临时覆盖框架配置
        self.api_key = params.get("api_key", lvm_cfg.get("key", "")).strip()
        self.model = params.get("model", lvm_cfg.get("model", "")).strip()
        self.api_base = lvm_cfg.get("url", "").strip()
        
        if not self.api_key:
            return SkillResult(
                False, 
                "缺少 LVM API Key。请执行 'choya config set lvm key <your-key>' 或在参数中传入 api_key", 
                error="missing_api_key"
            )
        if not self.api_base:
            return SkillResult(
                False, 
                "缺少 LVM URL。请执行 'choya config set lvm url <url>'", 
                error="missing_api_url"
            )
        if not self.model:
            self.model = "moonshot-v1-8k-vision-preview"  # 兜底视觉模型
        
        # 获取最新图像
        with self.image_lock:
            if self.latest_image is None:
                return SkillResult(False, "暂未获取到摄像头图像，请检查 /usb_camera/image_raw 是否有数据", error="no_image")
            pil_image = self.latest_image.copy()
        
        # 编码为 base64 JPEG（压缩减少 token 消耗）
        try:
            buffered = io.BytesIO()
            pil_image.save(buffered, format="JPEG", quality=85)
            img_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
        except Exception as e:
            return SkillResult(False, f"图像编码失败: {e}", error="encode_failed")
        
        # 调用多模态 LVM
        try:
            answer = self._call_vision_llm(question, img_base64)
            if self.answer_pub:
                self.answer_pub.publish(answer)
            rospy.loginfo(f"👁️ VisionQA: Q:{question} | A:{answer[:60]}...")
            return SkillResult(True, answer, data={"question": question, "answer": answer})
        except requests.exceptions.Timeout:
            return SkillResult(False, "LVM 请求超时，请检查网络", error="timeout")
        except Exception as e:
            rospy.logerr(f"❌ VisionQA LVM 错误: {e}")
            return SkillResult(False, f"视觉分析失败: {e}", error="lvm_error")
    
    def _call_vision_llm(self, question: str, img_base64: str) -> str:
        """调用 OpenAI 兼容的多模态 API，直接使用完整 URL"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_base64}",
                                "detail": "auto"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        resp = requests.post(self.api_base, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if "choices" not in data or len(data["choices"]) == 0:
            raise ValueError(f"LVM 返回异常: {data}")
            
        return data["choices"][0]["message"]["content"].strip()
    
    def _image_callback(self, msg: Image):
        """后台缓存最新摄像头帧"""
        try:
            if CV_BRIDGE_AVAILABLE and self.cv_bridge:
                cv_img = self.cv_bridge.imgmsg_to_cv2(msg, desired_encoding="rgb8")
                pil_img = PILImage.fromarray(cv_img)
            else:
                if msg.encoding in ("rgb8", "bgr8"):
                    arr = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, 3)
                    if msg.encoding == "bgr8":
                        arr = arr[:, :, ::-1]
                    pil_img = PILImage.fromarray(arr)
                elif msg.encoding == "mono8":
                    arr = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width)
                    pil_img = PILImage.fromarray(arr).convert("RGB")
                else:
                    rospy.logwarn_throttle(10, f"⚠️ VisionQA 不支持的图像编码: {msg.encoding}")
                    return
            
            with self.image_lock:
                self.latest_image = pil_img
                
        except Exception as e:
            rospy.logerr_throttle(10, f"❌ VisionQA 图像解码失败: {e}")
    
    def _init_ros(self):
        """初始化 ROS 订阅与发布"""
        if CV_BRIDGE_AVAILABLE:
            self.cv_bridge = CvBridge()
        self.image_sub = rospy.Subscriber("/usb_camera/image_raw", Image, self._image_callback, queue_size=1)
        self.answer_pub = rospy.Publisher("/vision/answer", String, queue_size=1)
        rospy.loginfo("📷 VisionQA Skill: 已订阅 /usb_camera/image_raw")