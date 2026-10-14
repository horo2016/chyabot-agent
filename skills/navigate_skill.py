#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import rospy
import json
import os
from geometry_msgs.msg import PoseStamped
from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult


class NavigateSkill(BaseSkill):
    def __init__(self):
        super().__init__()
        self.pub = rospy.Publisher('/goal_point', PoseStamped, queue_size=1)
        # 默认路径，可通过 ROS param 或 execute 参数覆盖
        self.map_markers_path = "/home/reeman/data/maps/map.markers.json"
        
    def get_description(self) -> str:
        return "移动到指定位置，如楼层、房间、电梯口、工位、办公室等"
        
    def get_parameters(self) -> dict:
        return {
            'target': {
                'type': 'string',
                'description': '目标位置，如"电梯口"、"会议室"、"我的工位"、"3021门口"',
                'required': True
            }
        }
    
    def _load_markers(self):
        """从 JSON 加载标记点，返回 {名称: world坐标}"""
        if not os.path.exists(self.map_markers_path):
            rospy.logerr(f"❌ 地图标记文件不存在: {self.map_markers_path}")
            return {}
        
        try:
            with open(self.map_markers_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            markers = {}
            for m in data.get("markers", []):
                name = m.get("name", "").strip()
                world = m.get("world", {})
                if name and world:
                    markers[name] = world
            return markers
            
        except Exception as e:
            rospy.logerr(f"❌ 加载地图标记失败: {e}")
            return {}
    
    def _find_target(self, target, markers):
        """
        模糊匹配目标点
        优先级：1.精确匹配 2.互相包含（子串匹配）
        """
        target = target.strip()
        if not target:
            return None, None
        
        # 1. 精确匹配
        if target in markers:
            return target, markers[target]
        
        # 2. 子串模糊匹配（如"电梯门口"包含"电梯口"；"去我的工位"包含"我的工位"）
        for name, coord in markers.items():
            if target in name or name in target:
                return name, coord
        
        return None, None
        
    def execute(self, params: dict) -> SkillResult:
        target = params.get('target', '').strip()
        if not target:
            return SkillResult(False, "目标地点不能为空", error="empty_target")
        
        markers = self._load_markers()
        if not markers:
            return SkillResult(False, "抱歉，地图标记文件加载失败", error="load_failed")
        
        matched_name, coord = self._find_target(target, markers)
        
        if matched_name is None:
            available = ", ".join(markers.keys())
            rospy.logwarn(f"⚠️ 未找到目标 '{target}'，可用目标: [{available}]")
            return SkillResult(False, f"抱歉，没找到 {target}", error="unknown_target")
        
        # 构造导航目标
        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = rospy.Time.now()
        pose.pose.position.x = coord.get('x', 0.0)
        pose.pose.position.y = coord.get('y', 0.0)
        pose.pose.position.z = 0.0
        pose.pose.orientation.w = 1.0
        
        self.pub.publish(pose)
        
        rospy.loginfo(f"🚀 导航到 [{matched_name}] x:{pose.pose.position.x:.2f} y:{pose.pose.position.y:.2f}")
        return SkillResult(True, f"正在前往 {matched_name}", data={
            'target': matched_name,
            'x': pose.pose.position.x,
            'y': pose.pose.position.y
        })