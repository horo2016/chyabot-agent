#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill 基类 - 所有技能必须继承
兼容 Python 3.8
"""

import abc
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class SkillStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SkillResult:
    success: bool
    message: str
    data: Dict[str, Any] = None
    error: Optional[str] = None


class BaseSkill(abc.ABC):
    """技能基类"""

    def __init__(self):
        self.name = self.__class__.__name__.replace('Skill', '').lower()
        self.status = SkillStatus.IDLE
        self.config = {}
        self.timeout = 30.0

    @abc.abstractmethod
    def get_description(self) -> str:
        """给 LLM 看的技能描述"""
        pass

    @abc.abstractmethod
    def get_parameters(self) -> Dict[str, Dict]:
        """参数 schema"""
        return {}

    @abc.abstractmethod
    def execute(self, params: Dict[str, Any]) -> SkillResult:
        """执行技能"""
        pass

    def validate_params(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """参数校验 - Python 3.8 兼容 Tuple[...]"""
        schema = self.get_parameters()
        for key, cfg in schema.items():
            if cfg.get('required', False) and key not in params:
                return False, f"缺少必填参数: {key}"
            if key in params:
                val = params[key]
                t = cfg.get('type')
                if t == 'string' and not isinstance(val, str):
                    return False, f"{key} 应为字符串"
                elif t == 'number' and not isinstance(val, (int, float)):
                    return False, f"{key} 应为数字"
                elif t == 'boolean' and not isinstance(val, bool):
                    return False, f"{key} 应为布尔值"
                elif t == 'enum' and val not in cfg.get('enum', []):
                    return False, f"{key} 必须是 {cfg['enum']} 之一"
        return True, None

    def cancel(self):
        """取消执行"""
        self.status = SkillStatus.CANCELLED

    def pre_execute(self, params: Dict[str, Any]):
        """执行前钩子"""
        self.status = SkillStatus.RUNNING

    def post_execute(self, result: SkillResult):
        """执行后钩子"""
        self.status = SkillStatus.SUCCESS if result.success else SkillStatus.FAILED