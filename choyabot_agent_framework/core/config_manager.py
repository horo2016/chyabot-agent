#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理：YAML 配置文件读写
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigManager:
    """管理 ~/.choya/config.yaml"""
    
    def __init__(self):
        self.config_dir = Path.home() / ".choya"
        self.config_file = self.config_dir / "config.yaml"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self._defaults = self._build_defaults()
        self._data = self._load()
        
    def _build_defaults(self) -> Dict[str, Any]:
        """构建默认配置模板"""
        return {
            "llm": {
                "url": "http://localhost:11434/v1/chat/completions",
                "model": "qwen2.5:7b",
                "key": ""
            },
            "lvm": {                          # 多模态视觉模型
                "url": "",
                "model": "",
                "key": ""
            },
            "voice": {
                "wake_word": "jarvis",
                "model_path": "~/whisper-models/base",
                "audio_device": None
            }
        }
        
    def _merge_defaults(self, data: Dict, defaults: Dict) -> Dict:
        """递归合并默认值：已有文件保留用户值，缺失字段自动补全"""
        result = data.copy()
        for key, value in defaults.items():
            if key not in result:
                result[key] = value
            elif isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge_defaults(result[key], value)
        return result
        
    def _load(self) -> Dict[str, Any]:
        """加载配置，自动合并缺失的默认字段"""
        data = {}
        if self.config_file.exists():
            with open(self.config_file) as f:
                data = yaml.safe_load(f) or {}
        
        # 合并默认值，确保新增字段（如 lvm）自动补全
        data = self._merge_defaults(data, self._defaults)
        return data
        
    def save(self):
        """保存配置"""
        with open(self.config_file, 'w') as f:
            yaml.dump(self._data, f, allow_unicode=True, sort_keys=False)
            
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置，支持点号路径，如 llm.url"""
        keys = key.split('.')
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value
        
    def set(self, key: str, value: Any):
        """设置配置，支持点号路径"""
        keys = key.split('.')
        data = self._data
        
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
            
        data[keys[-1]] = value
        self.save()
        
    def delete(self, key: str):
        """删除配置"""
        keys = key.split('.')
        data = self._data
        
        for k in keys[:-1]:
            if k not in data:
                return
            data = data[k]
            
        if keys[-1] in data:
            del data[keys[-1]]
            self.save()
            
    def list_all(self) -> Dict[str, Any]:
        """列出所有配置"""
        return self._data.copy()
        
    def get_llm_config(self) -> Dict[str, str]:
        """获取 LLM 配置"""
        return self._data.get("llm", {})
    
    def get_lvm_config(self) -> Dict[str, str]:
        """获取 LVM（多模态视觉模型）配置"""
        return self._data.get("lvm", {})
        
    def get_lvm_display(self) -> str:
        """获取 LVM 显示信息"""
        cfg = self.get_lvm_config()
        url = cfg.get("url", "")
        model = cfg.get("model", "")
        key = cfg.get("key", "")
        
        key_display = "已设置" if key else "未设置"
        
        if not url:
            mode = "⚠️ 未配置"
        elif "localhost" in url or "127.0.0.1" in url:
            mode = "🖥️ 本地"
        else:
            mode = "🌐 远程 API"
            
        return f"{mode} | URL: {url or '无'} | 模型: {model or '无'} | Key: {key_display}"
        
    def get_llm_display(self) -> str:
        """获取 LLM 显示信息"""
        cfg = self.get_llm_config()
        url = cfg.get("url", "")
        model = cfg.get("model", "")
        key = cfg.get("key", "")
        
        key_display = "已设置" if key else "未设置"
        
        if "localhost" in url or "127.0.0.1" in url:
            mode = "🖥️ 本地 (Ollama)"
        else:
            mode = "🌐 远程 API"
            
        return f"{mode} | URL: {url} | 模型: {model} | Key: {key_display}"