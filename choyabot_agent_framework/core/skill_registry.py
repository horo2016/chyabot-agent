#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skill 注册表 - 动态发现、热加载
"""

import os
import sys
import yaml
import importlib.util
import logging
from pathlib import Path
from typing import Dict, Type, Optional, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from choyabot_agent_framework.skills.base_skill import BaseSkill


class SkillRegistry(FileSystemEventHandler):
    def __init__(self, skills_dir: str = "skills", config_dir: str = "config/skills"):
        self.skills_dir = Path(skills_dir)
        self.config_dir = Path(config_dir)
        self._skills: Dict[str, BaseSkill] = {}
        self._configs: Dict[str, dict] = {}
        self.logger = logging.getLogger(__name__)
        
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # 文件监控
        self.observer = Observer()
        self.observer.schedule(self, str(self.skills_dir), recursive=True)
        self.observer.start()
        
    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            name = Path(event.src_path).stem.replace('_skill', '')
            if name and name != 'base':
                self.logger.info(f"🔄 热重载: {name}")
                self.reload_skill(name)
                
    def discover(self) -> List[str]:
        names = []
        if self.skills_dir.exists():
            for f in self.skills_dir.glob("*_skill.py"):
                n = f.stem.replace('_skill', '')
                if n and n != 'base':
                    names.append(n)
        return names
        
    def load_skill(self, name: str) -> Optional[BaseSkill]:
        """加载单个技能，全路径日志"""
        mod_path = self.skills_dir / f"{name}_skill.py"
        self.logger.debug(f"📄 {name}: 文件路径 {mod_path} (exists={mod_path.exists()})")
        
        if not mod_path.exists():
            self.logger.error(f"❌ {name}: 文件不存在 {mod_path}")
            return None
        
        try:
            # 加载模块
            spec = importlib.util.spec_from_file_location(f"skills.{name}", mod_path)
            if spec is None:
                self.logger.error(f"❌ {name}: spec_from_file_location 返回 None")
                return None
                
            mod = importlib.util.module_from_spec(spec)
            
            if str(self.skills_dir.parent) not in sys.path:
                sys.path.insert(0, str(self.skills_dir.parent))
            
            self.logger.debug(f"📄 {name}: 执行模块...")
            spec.loader.exec_module(mod)
            self.logger.debug(f"📄 {name}: 模块执行完成")
            
        except Exception as e:
            self.logger.error(f"❌ {name}: 模块加载异常: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
        
        # 查找类
        cls_name = ''.join([w.capitalize() for w in name.split('_')]) + 'Skill'
        cls = getattr(mod, cls_name, None)
        self.logger.debug(f"🔍 {name}: 尝试类名 {cls_name}, found={cls is not None}")
        
        if cls is None or not (isinstance(cls, type) and issubclass(cls, BaseSkill)):
            candidates = []
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (isinstance(attr, type) 
                    and issubclass(attr, BaseSkill) 
                    and attr is not BaseSkill
                    and attr.__module__ == mod.__name__):
                    candidates.append(attr)
            
            if not candidates:
                self.logger.error(f"❌ {name}: 未找到 BaseSkill 子类。模块成员: {[x for x in dir(mod) if not x.startswith('_')]}")
                return None
                
            cls = candidates[0]
            if len(candidates) > 1:
                self.logger.warning(f"⚠️ {name}: 多个候选 { [c.__name__ for c in candidates] }")
        
        self.logger.debug(f"🔍 {name}: 使用类 {cls.__name__}")
        
        # 实例化
        try:
            inst = cls()
            self.logger.debug(f"🔧 {name}: 实例化成功")
        except Exception as e:
            self.logger.error(f"❌ {name}: 实例化失败: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None
        
        # 加载 YAML
        cfg_path = self.config_dir / f"{name}.yaml"
        self.logger.debug(f"📋 {name}: 配置文件 {cfg_path} (exists={cfg_path.exists()})")
        
        try:
            if cfg_path.exists():
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    inst.config = yaml.safe_load(f) or {}
                    # 安全读取 timeout
                    params = inst.config.get('parameters', {}) if isinstance(inst.config, dict) else {}
                    timeout_cfg = params.get('timeout', {}) if isinstance(params, dict) else {}
                    inst.timeout = timeout_cfg.get('default', 30.0) if isinstance(timeout_cfg, dict) else 30.0
                self.logger.debug(f"📋 {name}: YAML 加载成功")
            else:
                inst.config = {}
                inst.timeout = 30.0
                self.logger.warning(f"⚠️ {name}: 无配置文件")
        except Exception as e:
            self.logger.error(f"❌ {name}: YAML 加载异常: {e}")
            inst.config = {}
            inst.timeout = 30.0
        
        # 注册
        self._skills[name] = inst
        self._configs[name] = inst.config
        self.logger.info(f"✅ 加载技能: {name} (类: {cls.__name__})")
        
    def reload_skill(self, name: str):
        mod_name = f"skills.{name}"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        return self.load_skill(name)
        
    def load_all(self):
        """加载所有技能，逐个打印详细状态"""
        names = self.discover()
        self.logger.info(f"🔍 扫描到 {len(names)} 个技能文件: {names}")
        
        for name in names:
            self.logger.info(f"⏳ 正在加载: {name}...")
            skill = self.load_skill(name)
            if skill is None:
                self.logger.error(f"❌ {name}: 加载失败，返回 None")
            else:
                self.logger.info(f"✅ {name}: 加载成功")
        
        loaded = list(self._skills.keys())
        self.logger.info(f"📦 最终加载成功: {loaded} ({len(loaded)}/{len(names)})")
            
    def get(self, name: str) -> Optional[BaseSkill]:
        return self._skills.get(name)
        
    def list(self) -> List[Dict]:
        return [{
            'name': n,
            'description': s.get_description(),
            'parameters': s.get_parameters(),
            'status': s.status.value
        } for n, s in self._skills.items()]
        
    def get_descriptions_for_llm(self) -> str:
        lines = ["可用技能："]
        for n, s in self._skills.items():
            lines.append(f"\n- {n}: {s.get_description()}")
            ps = s.get_parameters()
            if ps:
                lines.append("  参数:")
                for pn, pc in ps.items():
                    req = "必填" if pc.get('required') else "可选"
                    lines.append(f"    - {pn} ({pc.get('type','string')}, {req}): {pc.get('description','')}")
        return "\n".join(lines)
        
    def stop(self):
        self.observer.stop()
        self.observer.join()