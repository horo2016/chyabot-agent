#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
goal_recorder_skill.py
目标点采集 Skill：监听定位 Odometry，通过语音指令记录并保存目标点
作为 ChoyaBot Agent 的可插拔 Skill 运行

参数从 config/skills/goal_recorder.yaml 读取
"""

import rospy
from std_msgs.msg import String, Bool
from nav_msgs.msg import Odometry
import json
import os
import time
import threading
import math
import re
from pathlib import Path

import yaml

from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult

 
class GoalRecorderSkill(BaseSkill):
    """
    目标点采集 Skill
    - 持续监听 localization_odom 获取当前位姿
    - 接收语音指令（通过 /agent/input 或内部调用）
    - 解析指令中的位置名称，保存当前位姿
    - 支持保存到 JSON 文件
    - 支持查询、删除、列出所有目标点

    参数从 config/skills/goal_recorder.yaml 读取
    """

    def __init__(self):
        super().__init__()
        self.name = "goal_recorder"

        # 默认参数（会被 YAML 覆盖）
        self.save_path = os.path.expanduser("~/goals.json")
        self.odom_topic = "/localization_odom"
        self.input_topic = "/agent/input"
        self.min_record_interval = 2.0
        self.position_tolerance = 0.05
        self.yaw_tolerance = 0.087
        self.auto_save = True
        self.keywords = ["记录", "保存", "标记", "采集"]
        self.delete_keywords = ["删除", "移除"]
        self.list_keywords = ["列出", "查看", "列表"]

        # 状态
        self.current_pose = None
        self.current_yaw = 0.0
        self.last_record_time = 0.0
        self.goals = {}
        self.goals_lock = threading.Lock()

        # ROS
        self.odom_sub = None
        self.input_sub = None
        self.status_pub = None
        self.result_pub = None

        self.running = False

    def _load_yaml_config(self):
        """从 config/skills/goal_recorder.yaml 加载配置"""
        # 查找 YAML 文件路径
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "..", "..", "config", "skills", "goal_recorder.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "config", "skills", "goal_recorder.yaml"),
            os.path.join(os.getcwd(), "config", "skills", "goal_recorder.yaml"),
            os.path.expanduser("~/catkin_ws/src/choyabot_agent_framework/config/skills/goal_recorder.yaml"),
            os.path.expanduser("~/workspace/config/skills/goal_recorder.yaml"),
        ]

        yaml_path = None
        for path in possible_paths:
            if os.path.exists(path):
                yaml_path = path
                break

        if yaml_path is None:
            rospy.logwarn("⚠️ 未找到 config/skills/goal_recorder.yaml，使用默认参数")
            return

        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            params = config.get("parameters", {})

            # 读取各参数
            if "save_path" in params:
                self.save_path = os.path.expanduser(params["save_path"].get("default", self.save_path))

            if "odom_topic" in params:
                self.odom_topic = params["odom_topic"].get("default", self.odom_topic)

            if "input_topic" in params:
                self.input_topic = params["input_topic"].get("default", self.input_topic)

            if "min_record_interval" in params:
                self.min_record_interval = params["min_record_interval"].get("default", self.min_record_interval)

            if "position_tolerance" in params:
                self.position_tolerance = params["position_tolerance"].get("default", self.position_tolerance)

            if "yaw_tolerance" in params:
                self.yaw_tolerance = params["yaw_tolerance"].get("default", self.yaw_tolerance)

            if "auto_save" in params:
                self.auto_save = params["auto_save"].get("default", self.auto_save)

            if "keywords" in params:
                self.keywords = params["keywords"].get("default", self.keywords)

            if "delete_keywords" in params:
                self.delete_keywords = params["delete_keywords"].get("default", self.delete_keywords)

            if "list_keywords" in params:
                self.list_keywords = params["list_keywords"].get("default", self.list_keywords)

            rospy.loginfo(f"📄 已加载 YAML 配置: {yaml_path}")

        except Exception as e:
            rospy.logwarn(f"⚠️ 加载 YAML 配置失败: {e}，使用默认参数")

    def get_description(self) -> str:
        return "目标点采集系统：监听定位位姿，语音指令记录并保存目标点位置"

    def get_parameters(self) -> dict:
        return {
            "save_path": {
                "type": "string",
                "description": "目标点保存文件路径（JSON格式）",
                "required": False,
                "default": "~/goals.json"
            },
            "odom_topic": {
                "type": "string",
                "description": "定位 Odometry 话题名",
                "required": False,
                "default": "/localization_odom"
            },
            "input_topic": {
                "type": "string",
                "description": "语音输入话题名",
                "required": False,
                "default": "/agent/input"
            },
            "min_record_interval": {
                "type": "number",
                "description": "两次记录最小间隔（秒）",
                "required": False,
                "default": 2.0
            },
            "position_tolerance": {
                "type": "number",
                "description": "位置去重容差（米）",
                "required": False,
                "default": 0.05
            },
            "yaw_tolerance": {
                "type": "number",
                "description": "角度去重容差（弧度）",
                "required": False,
                "default": 0.087
            },
            "auto_save": {
                "type": "boolean",
                "description": "是否自动保存到文件",
                "required": False,
                "default": True
            },
            "keywords": {
                "type": "list",
                "description": "记录指令关键词列表",
                "required": False,
                "default": ["记录", "保存", "标记", "采集"]
            },
            "delete_keywords": {
                "type": "list",
                "description": "删除指令关键词列表",
                "required": False,
                "default": ["删除", "移除"]
            },
            "list_keywords": {
                "type": "list",
                "description": "列表指令关键词列表",
                "required": False,
                "default": ["列出", "查看", "列表"]
            }
        }

    def execute(self, params: dict) -> SkillResult:
        """启动目标点采集后台监听"""
        # 先加载 YAML 配置（基础默认值）
        self._load_yaml_config()

        # 再用传入的 params 覆盖（优先级最高）
        self.save_path = os.path.expanduser(params.get("save_path", self.save_path))
        self.odom_topic = params.get("odom_topic", self.odom_topic)
        self.input_topic = params.get("input_topic", self.input_topic)
        self.min_record_interval = params.get("min_record_interval", self.min_record_interval)
        self.position_tolerance = params.get("position_tolerance", self.position_tolerance)
        self.yaw_tolerance = params.get("yaw_tolerance", self.yaw_tolerance)
        self.auto_save = params.get("auto_save", self.auto_save)
        self.keywords = params.get("keywords", self.keywords)
        self.delete_keywords = params.get("delete_keywords", self.delete_keywords)
        self.list_keywords = params.get("list_keywords", self.list_keywords)

        try:
            self._load_goals()

            self.odom_sub = rospy.Subscriber(self.odom_topic, Odometry, self._odom_callback)
            self.input_sub = rospy.Subscriber(self.input_topic, String, self._input_callback)
            self.status_pub = rospy.Publisher("/goal_recorder/status", String, queue_size=10)
            self.result_pub = rospy.Publisher("/goal_recorder/result", String, queue_size=10)

            self.running = True

            rospy.loginfo(f"📍 Goal Recorder 启动完成")
            rospy.loginfo(f"   保存路径: {self.save_path}")
            rospy.loginfo(f"   监听话题: {self.odom_topic}")
            rospy.loginfo(f"   语音输入: {self.input_topic}")
            rospy.loginfo(f"   已加载目标点: {len(self.goals)} 个")

            return SkillResult(
                True,
                f"目标点采集已启动，已加载 {len(self.goals)} 个目标点",
                data={"save_path": self.save_path, "loaded_goals": len(self.goals)}
            )

        except Exception as e:
            return SkillResult(False, f"目标点采集启动失败: {e}", error=str(e))

    def cancel(self):
        """停止 Skill，自动保存"""
        self.running = False
        if self.auto_save:
            self._save_goals()
        rospy.loginfo("🛑 Goal Recorder 已停止")

    # ==================== ROS 回调 ====================

    def _odom_callback(self, msg: Odometry):
        """定位 Odometry 回调，更新当前位姿"""
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        self.current_pose = [p.x, p.y, p.z, q.x, q.y, q.z, q.w]

        siny = 2.0 * (q.w * q.z + q.x * q.y)
        cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        self.current_yaw = math.atan2(siny, cosy)

    def _input_callback(self, msg: String):
        """接收语音/文本输入，解析指令"""
        text = msg.data.strip()
        rospy.loginfo(f"📥 Goal Recorder 收到输入: {text}")

        if any(kw in text for kw in self.keywords):
            self._handle_record_command(text)
        elif any(kw in text for kw in self.delete_keywords):
            self._handle_delete_command(text)
        elif any(kw in text for kw in self.list_keywords):
            self._handle_list_command()

    # ==================== 指令处理 ====================

    def _handle_record_command(self, text: str):
        """处理记录指令，提取名称并保存"""
        name = self._extract_name(text, self.keywords)

        if not name:
            self._publish_status("error", "未检测到目标点名称，请说：记录电梯门口")
            return

        if self.current_pose is None:
            self._publish_status("error", "尚未收到定位数据，无法记录")
            return

        now = time.time()
        if now - self.last_record_time < self.min_record_interval:
            self._publish_status("warning", f"记录太频繁，请间隔 {self.min_record_interval} 秒")
            return

        if self._is_duplicate(self.current_pose, self.current_yaw):
            self._publish_status("warning", "该位置已存在相似目标点，跳过记录")
            return

        goal_data = {
            "x": self.current_pose[0],
            "y": self.current_pose[1],
            "z": self.current_pose[2],
            "qx": self.current_pose[3],
            "qy": self.current_pose[4],
            "qz": self.current_pose[5],
            "qw": self.current_pose[6],
            "yaw": self.current_yaw,
            "timestamp": now,
            "source": "voice_command"
        }

        with self.goals_lock:
            self.goals[name] = goal_data

        self.last_record_time = now

        if self.auto_save:
            self._save_goals()

        self._publish_status("success", f"✅ 已记录目标点: {name}")
        self._publish_result("recorded", name, goal_data)

        rospy.loginfo(f"📍 记录目标点: {name} -> ({goal_data['x']:.3f}, {goal_data['y']:.3f}, yaw={goal_data['yaw']:.3f})")

    def _handle_delete_command(self, text: str):
        """处理删除指令"""
        name = self._extract_name(text, self.delete_keywords)

        if not name:
            self._publish_status("error", "未检测到要删除的目标点名称")
            return

        with self.goals_lock:
            if name in self.goals:
                del self.goals[name]
                if self.auto_save:
                    self._save_goals()
                self._publish_status("success", f"🗑️ 已删除目标点: {name}")
                self._publish_result("deleted", name, {})
            else:
                self._publish_status("error", f"目标点 '{name}' 不存在")

    def _handle_list_command(self):
        """处理列表指令"""
        with self.goals_lock:
            if not self.goals:
                self._publish_status("info", "当前没有记录任何目标点")
                return

            goal_list = []
            for name, data in self.goals.items():
                goal_list.append(f"  • {name}: ({data['x']:.2f}, {data['y']:.2f})")

            msg = f"📋 已记录 {len(self.goals)} 个目标点:\n" + "\n".join(goal_list)
            self._publish_status("info", msg)
            self._publish_result("listed", "all", {"count": len(self.goals), "goals": list(self.goals.keys())})

    # ==================== 工具方法 ====================

    def _extract_name(self, text: str, keywords: list) -> str:
        """从文本中提取名称（去掉关键词）"""
        for kw in keywords:
            if kw in text:
                idx = text.find(kw) + len(kw)
                name = text[idx:].strip()
                name = name.lstrip("为是到在的 \t")
                if name:
                    return name

        match = re.search(r"['\"](.+?)['\"]", text)
        if match:
            return match.group(1)

        return ""

    def _is_duplicate(self, pose, yaw) -> bool:
        """检查是否与已有目标点重复"""
        with self.goals_lock:
            for name, data in self.goals.items():
                dx = pose[0] - data["x"]
                dy = pose[1] - data["y"]
                dist = (dx * dx + dy * dy) ** 0.5
                dyaw = abs(yaw - data["yaw"])
                while dyaw > 3.14159:
                    dyaw -= 6.28318
                if dist < self.position_tolerance and abs(dyaw) < self.yaw_tolerance:
                    return True
        return False

    def _publish_status(self, status_type: str, message: str):
        """发布状态消息"""
        msg = String()
        msg.data = json.dumps({"type": status_type, "message": message, "timestamp": time.time()})
        self.status_pub.publish(msg)

    def _publish_result(self, action: str, name: str, data: dict):
        """发布操作结果"""
        msg = String()
        msg.data = json.dumps({"action": action, "name": name, "data": data, "timestamp": time.time()})
        self.result_pub.publish(msg)

    # ==================== 文件操作 ====================

    def _load_goals(self):
        """从文件加载目标点"""
        if not os.path.exists(self.save_path):
            rospy.loginfo(f"📂 目标点文件不存在，将创建新文件: {self.save_path}")
            return

        try:
            with open(self.save_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                with self.goals_lock:
                    self.goals = loaded
            rospy.loginfo(f"📂 已加载 {len(self.goals)} 个目标点")
        except Exception as e:
            rospy.logwarn(f"⚠️ 加载目标点文件失败: {e}")

    def _save_goals(self):
        """保存目标点到文件"""
        try:
            os.makedirs(os.path.dirname(self.save_path) or ".", exist_ok=True)

            with self.goals_lock:
                with open(self.save_path, 'w', encoding='utf-8') as f:
                    json.dump(self.goals, f, ensure_ascii=False, indent=2)

            rospy.loginfo(f"💾 已保存 {len(self.goals)} 个目标点到 {self.save_path}")
        except Exception as e:
            rospy.logerr(f"❌ 保存目标点失败: {e}")

    # ==================== 外部调用接口 ====================

    def record_goal(self, name: str) -> dict:
        """外部直接调用记录目标点"""
        if self.current_pose is None:
            return {"success": False, "error": "无定位数据"}

        now = time.time()
        goal_data = {
            "x": self.current_pose[0],
            "y": self.current_pose[1],
            "z": self.current_pose[2],
            "qx": self.current_pose[3],
            "qy": self.current_pose[4],
            "qz": self.current_pose[5],
            "qw": self.current_pose[6],
            "yaw": self.current_yaw,
            "timestamp": now,
            "source": "api_call"
        }

        with self.goals_lock:
            self.goals[name] = goal_data

        if self.auto_save:
            self._save_goals()

        return {"success": True, "name": name, "data": goal_data}

    def get_goal(self, name: str) -> dict:
        """获取指定目标点"""
        with self.goals_lock:
            return self.goals.get(name, {})

    def get_all_goals(self) -> dict:
        """获取所有目标点"""
        with self.goals_lock:
            return dict(self.goals)

    def delete_goal(self, name: str) -> bool:
        """删除指定目标点"""
        with self.goals_lock:
            if name in self.goals:
                del self.goals[name]
                if self.auto_save:
                    self._save_goals()
                return True
            return False
