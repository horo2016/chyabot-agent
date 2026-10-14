#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
choya CLI - ChoyaBot Agent 命令行工具
"""

import sys
import os
import argparse
import shutil
import subprocess
import yaml
from pathlib import Path

from choyabot_agent_framework.core.config_manager import ConfigManager

# 框架路径
SKILLS_DIR = Path("skills")
CONFIG_DIR = Path("config/skills")


def ensure_dirs():
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (Path("memory")).mkdir(exist_ok=True)


def _create_example_navigate():
    """内嵌创建示例导航 skill"""
    code = """#!/usr/bin/env python3
import rospy
from geometry_msgs.msg import PoseStamped
from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult


class NavigateSkill(BaseSkill):
    def __init__(self):
        super().__init__()
        self.pub = rospy.Publisher('/move_base_simple/goal', PoseStamped, queue_size=1)
        
    def get_description(self) -> str:
        return "移动到指定位置，如楼层、房间、电梯口等"
        
    def get_parameters(self) -> dict:
        return {
            'target': {
                'type': 'string',
                'description': '目标位置，如\\"一楼\\"、\\"会议室\\"',
                'required': True
            }
        }
        
    def execute(self, params: dict) -> SkillResult:
        target = params['target']
        locations = {
            '一楼': {'x': 0, 'y': 0},
            '二楼': {'x': 10, 'y': 0},
            '三楼': {'x': 20, 'y': 0},
            '会议室': {'x': 22, 'y': 5},
            '电梯口': {'x': 5, 'y': 2},
        }
        for loc, coord in locations.items():
            if loc in target:
                pose = PoseStamped()
                pose.header.frame_id = 'map'
                pose.header.stamp = rospy.Time.now()
                pose.pose.position.x = coord['x']
                pose.pose.position.y = coord['y']
                pose.pose.orientation.w = 1.0
                self.pub.publish(pose)
                return SkillResult(True, f"正在前往 {target}", data={'target': target})
        return SkillResult(False, f"未知目标: {target}", error="unknown_target")
"""
    with open(SKILLS_DIR / "navigate_skill.py", 'w') as f:
        f.write(code)


def _create_example_navigate_yaml():
    """内嵌创建示例配置"""
    cfg = {
        'name': 'navigate',
        'version': '1.0.0',
        'description': '移动到指定位置，如楼层、房间、电梯口等',
        'author': 'choyabot',
        'tags': ['navigation', 'move'],
        'parameters': {
            'target': {
                'type': 'string',
                'description': '目标位置名称',
                'required': True
            }
        },
        'ros': {
            'topics': [{
                'name': '/move_base_simple/goal',
                'type': 'geometry_msgs/PoseStamped',
                'direction': 'publish'
            }]
        },
        'timeout': 30.0
    }
    with open(CONFIG_DIR / "navigate.yaml", 'w') as f:
        yaml.dump(cfg, f, allow_unicode=True, sort_keys=False)


def cmd_init(args):
    """初始化项目"""
    print("🚀 初始化 ChoyaBot Agent 项目...")
    ensure_dirs()
    
    # 创建示例 skill
    if not (SKILLS_DIR / "navigate_skill.py").exists():
        _create_example_navigate()
        _create_example_navigate_yaml()
        print("  ✅ 创建示例技能: navigate")
    
    # 显示 LLM 配置
    cfg = ConfigManager()
    print(f"\n🧠 LLM 配置:")
    print(f"   {cfg.get_llm_display()}")
    print(f"\n   配置文件: {cfg.config_file}")
    print(f"\n   大语言模型修改命令:")
    print(f"     choya config set llm.url http://localhost:11434/v1/chat/completions")
    print(f"     choya config set llm.model qwen2.5:7b")
    print(f"     choya config set llm.key your-api-key")
    print(f"\n   多模态模型修改命令:")
    print(f"     choya config set lvm.url  https://api.moonshot.cn/v1/chat/completions")
    print(f"     choya config set lvm.model moonshot-v1-8k-vision-preview")
    print(f"     choya config set lvm.key  sk-your-key")
        
    print("\n✅ 初始化完成")
    print(f"   技能目录: {SKILLS_DIR.absolute()}")
    print(f"   配置目录: {CONFIG_DIR.absolute()}")
    print("\n下一步:")
    print("  choya skill list          # 查看技能")
    print("  choya config get llm      # 查看 LLM 配置")
    print("  choya config get lvm      # 查看 LVM 配置")
    print("  choya run                 # 启动 Agent")
    return 0


def cmd_config_get(args):
    """获取配置"""
    cfg = ConfigManager()
    key = args.key
    
    if key:
        value = cfg.get(key)
        if value is None:
            print(f"❌ 配置项不存在: {key}")
            return 1
        print(value)
    else:
        # 显示所有配置
        data = cfg.list_all()
        print("=== ⚙️ 当前配置 ===\n")
        print(yaml.dump(data, allow_unicode=True, sort_keys=False))
        
    return 0


def cmd_config_set(args):
    """设置配置"""
    cfg = ConfigManager()
    cfg.set(args.key, args.value)
    print(f"✅ 设置: {args.key} = {args.value}")
    
    # 如果是 LLM 配置，显示完整信息
    if args.key.startswith("llm."):
        print(f"\n🧠 当前 LLM: {cfg.get_llm_display()}")
        
    return 0


def cmd_config_delete(args):
    """删除配置"""
    cfg = ConfigManager()
    cfg.delete(args.key)
    print(f"✅ 删除: {args.key}")
    return 0


def cmd_skill_add(args):
    """添加技能"""
    ensure_dirs()
    
    if args.file:
        skill_file = Path(args.file)
        if not skill_file.exists():
            print(f"❌ 技能文件不存在: {skill_file}")
            return 1
            
        target = SKILLS_DIR / skill_file.name
        shutil.copy(skill_file, target)
        print(f"✅ 安装技能文件: {target}")
        
        if args.config:
            cfg = Path(args.config)
            if cfg.exists():
                shutil.copy(cfg, CONFIG_DIR / cfg.name)
                print(f"✅ 安装配置文件: {CONFIG_DIR / cfg.name}")
                
        print("🔄 框架将自动热加载")
        return 0
        
    elif args.git:
        repo_name = args.git.split('/')[-1].replace('.git', '')
        clone_dir = Path(f"/tmp/choya-skill-{repo_name}")
        
        print(f"⬇️ 克隆仓库: {args.git}")
        try:
            subprocess.run(
                ['git', 'clone', '--depth', '1', args.git, str(clone_dir)],
                check=True, capture_output=True
            )
        except subprocess.CalledProcessError as e:
            print(f"❌ 克隆失败: {e}")
            return 1
            
        # 查找 skill 文件
        skill_files = list(clone_dir.glob("*_skill.py"))
        config_files = list(clone_dir.glob("*.yaml")) + list(clone_dir.glob("skill.yaml"))
        
        for f in skill_files:
            shutil.copy(f, SKILLS_DIR / f.name)
            print(f"✅ 安装技能: {f.name}")
            
        for f in config_files:
            name = f.stem if f.stem != 'skill' else repo_name.replace('choya-skill-', '')
            shutil.copy(f, CONFIG_DIR / f"{name}.yaml")
            print(f"✅ 安装配置: {name}.yaml")
            
        shutil.rmtree(clone_dir)
        return 0
        
    else:
        print("❌ 请指定 --file 或 --git")
        return 1


def cmd_skill_list(args):
    """列出技能"""
    ensure_dirs()
    print("=== 🔧 已安装技能 ===\n")
    
    if not SKILLS_DIR.exists():
        print("  (空)")
        return 0
        
    found = False
    for f in sorted(SKILLS_DIR.glob("*_skill.py")):
        found = True
        name = f.stem.replace('_skill', '')
        cfg = CONFIG_DIR / f"{name}.yaml"
        
        status = "🟢" if cfg.exists() else "🟡 缺少配置"
        desc = ""
        if cfg.exists():
            try:
                with open(cfg) as cf:
                    data = yaml.safe_load(cf)
                    desc = data.get('description', '')
                    ver = data.get('version', '?')
                    status += f"  v{ver}"
            except:
                pass
                
        print(f"  {status:<12} {name:<15} {desc}")
        print(f"               文件: {f}")
        
    if not found:
        print("  (空) 使用 'choya skill add --file xxx.py' 添加技能")
        
    print()
    return 0


def cmd_skill_remove(args):
    """移除技能"""
    name = args.name
    skill_file = SKILLS_DIR / f"{name}_skill.py"
    config_file = CONFIG_DIR / f"{name}.yaml"
    
    removed = False
    if skill_file.exists():
        skill_file.unlink()
        print(f"✅ 移除技能: {skill_file}")
        removed = True
        
    if config_file.exists():
        config_file.unlink()
        print(f"✅ 移除配置: {config_file}")
        removed = True
        
    if not removed:
        print(f"❌ 技能不存在: {name}")
        return 1
        
    print("🔄 框架将自动卸载")
    return 0


def cmd_skill_info(args):
    """查看技能详情"""
    name = args.name
    cfg = CONFIG_DIR / f"{name}.yaml"
    
    if not cfg.exists():
        print(f"❌ 配置不存在: {name}")
        return 1
        
    with open(cfg) as f:
        data = yaml.safe_load(f)
        
    print(f"=== 📋 {name} ===")
    print(yaml.dump(data, allow_unicode=True, sort_keys=False))
    return 0


def cmd_run(args):
    """启动 Agent"""
    ensure_dirs()
    
    # 显示 LLM 配置
    cfg = ConfigManager()
    print("🚀 启动 ChoyaBot Agent...\n")
    print(f"🧠 LLM: {cfg.get_llm_display()}\n")
    
    from choyabot_agent_framework.core.agent import RobotAgent
    
    agent = RobotAgent()
    try:
        agent.run()
    except KeyboardInterrupt:
        print("\n👋 收到退出信号")
    finally:
        agent.stop()


def main():
    parser = argparse.ArgumentParser(
        prog="choya",
        description="ChoyaBot Agent Framework - 机器人智能体框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  choya init                              # 初始化项目
  choya config get llm                    # 查看 LLM 配置
  choya config set llm.model qwen2.5:7b   # 设置模型
  choya config set llm.url http://localhost:11434/v1/chat/completions
  choya config set llm.key sk-xxx         # 设置 API Key
  choya skill list                        # 列出技能
  choya skill add --file ./nav.py         # 添加本地技能
  choya skill add --git https://github.com/xxx/choya-skill-elevator.git
  choya skill remove navigate             # 移除技能
  choya skill info elevator               # 查看技能详情
  choya run                               # 启动 Agent
        """
    )
    
    sub = parser.add_subparsers(dest='cmd', help='子命令')
    
    # init
    sub.add_parser('init', help='初始化项目')
    
    # config
    config_p = sub.add_parser('config', help='配置管理')
    config_sub = config_p.add_subparsers(dest='config_cmd', help='配置操作')
    
    config_get_p = config_sub.add_parser('get', help='获取配置')
    config_get_p.add_argument('key', nargs='?', help='配置项，如 llm.url')
    
    config_set_p = config_sub.add_parser('set', help='设置配置')
    config_set_p.add_argument('key', help='配置项，如 llm.model')
    config_set_p.add_argument('value', help='配置值')
    
    config_del_p = config_sub.add_parser('delete', help='删除配置')
    config_del_p.add_argument('key', help='配置项')
    
    config_sub.add_parser('list', help='列出所有配置')
    
    # skill
    skill_p = sub.add_parser('skill', help='技能管理')
    skill_sub = skill_p.add_subparsers(dest='skill_cmd', help='技能操作')
    
    add_p = skill_sub.add_parser('add', help='添加技能')
    add_p.add_argument('--file', help='本地 .py 文件路径')
    add_p.add_argument('--config', help='本地 .yaml 配置文件')
    add_p.add_argument('--git', help='Git 仓库地址')
    
    skill_sub.add_parser('list', help='列出技能')
    
    rm_p = skill_sub.add_parser('remove', help='移除技能')
    rm_p.add_argument('name', help='技能名称')
    
    info_p = skill_sub.add_parser('info', help='查看技能详情')
    info_p.add_argument('name', help='技能名称')
    
    # run
    sub.add_parser('run', help='启动 Agent')
    
    args = parser.parse_args()
    
    if args.cmd == 'init':
        return cmd_init(args)
    elif args.cmd == 'config':
        if args.config_cmd == 'get':
            return cmd_config_get(args)
        elif args.config_cmd == 'set':
            return cmd_config_set(args)
        elif args.config_cmd == 'delete':
            return cmd_config_delete(args)
        elif args.config_cmd == 'list':
            return cmd_config_get(args)  # key=None 时列出所有
        else:
            config_p.print_help()
            return 1
    elif args.cmd == 'skill':
        if args.skill_cmd == 'add':
            return cmd_skill_add(args)
        elif args.skill_cmd == 'list':
            return cmd_skill_list(args)
        elif args.skill_cmd == 'remove':
            return cmd_skill_remove(args)
        elif args.skill_cmd == 'info':
            return cmd_skill_info(args)
        else:
            skill_p.print_help()
            return 1
    elif args.cmd == 'run':
        return cmd_run(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
