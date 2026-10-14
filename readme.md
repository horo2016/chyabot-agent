# ChoyaBot Agent Framework 使用文档

> **面向机器人智能体的 Python Agent 框架**
> 
> 版本: v1.0.0 | 作者: 李德 | 适用: ROS1 + Python 3.8+

---

## 一、项目概述

### 1.1 什么是 ChoyaBot Agent Framework？

ChoyaBot Agent 是一个**面向机器人驱动的智能体框架**，灵感来源于 OpenClaw，但专为 ROS1 机器人场景设计。

**核心能力：**
- 🎤 **语音交互**：唤醒词检测 + 语音识别 + 语音合成
- 🧠 **LLM 规划**：将自然语言指令分解为可执行的机器人动作
- 🔧 **动态 Skill**：像插件一样热插拔机器人技能（导航、电梯、机械臂等）
- 📝 **记忆系统**：SQLite 持久化对话历史
- 🔄 **连续对话**：一次唤醒后，3 秒内无需重复唤醒

### 1.2 适用场景

- 服务机器人语音控制
- 多楼层配送机器人
- 电梯联动机器人
- 人机语音交互教学演示

### 1.3 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户语音输入                          │
│              "去三楼会议室，把文件拿到一楼"               │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Voice Skill (语音技能)                                  │
│  ├─ Porcupine 唤醒词检测 (jarvis/computer)               │
│  ├─ Faster-Whisper 语音识别 (本地模型)                    │
│  ├─ VAD 自动断句 (能量阈值 + 静音检测)                    │
│  └─ pyttsx3 语音合成 (离线播报)                          │
│  输出: /agent/input → "去三楼会议室，把文件拿到一楼"       │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Agent Core (智能体核心)                                 │
│  ├─ Memory (记忆系统): SQLite 存储对话历史               │
│  ├─ Planner (规划器): LLM 分解任务为执行步骤             │
│  └─ Skill Registry (技能注册表): 动态加载/热重载 Skill   │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│  Skill 执行队列                                          │
│  ├─ Step 1: navigate(target="三楼会议室")                │
│  ├─ Step 2: arm_pick(object="文件")                      │
│  ├─ Step 3: navigate(target="一楼")                      │
│  └─ Step 4: arm_place(location="桌面")                   │
└─────────────────────────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌────────────┐  ┌────────────┐  ┌────────────┐
    │  Navigate  │  │    Arm     │  │  Elevator  │
    │   Skill    │  │   Skill    │  │   Skill    │
    │  (底盘移动) │  │ (按压/抓取) │  │ (电梯操作) │
    └────────────┘  └────────────┘  └────────────┘
```

---

## 二、目录结构

```
choyabot-agent-framework/
├── README.md                          # 项目说明
├── setup.py                           # pip 安装配置
├── requirements.txt                   # Python 依赖
├── bin/
│   └── choya                          # CLI 入口脚本
│
├── choyabot_agent_framework/          # 框架核心包
│   ├── __init__.py
│   ├── __main__.py                    # python -m / choya CLI
│   │
│   ├── core/                          # 核心模块
│   │   ├── __init__.py
│   │   ├── agent.py                   # Agent 主调度器
│   │   ├── skill_registry.py          # Skill 注册表 + 热加载
│   │   ├── planner.py                 # LLM 任务规划器
│   │   ├── memory.py                  # SQLite 记忆系统
│   │   ├── context.py                 # 上下文管理
│   │   └── config_manager.py          # YAML 配置管理
│   │
│   ├── skills/                        # 框架内置基类
│   │   ├── __init__.py
│   │   └── base_skill.py              # Skill 基类 (必须继承)
│   │
│   └── utils/                         # 工具函数
│       ├── __init__.py
│       └── logger.py
│
├── skills/                            # 用户 Skill 目录 (运行时加载)
│   ├── __init__.py
│   ├── navigate_skill.py              # 导航技能示例
│   ├── elevator_skill.py              # 电梯技能示例
│   ├── arm_skill.py                   # 机械臂技能示例
│   └── voice_skill.py                 # 语音交互技能
│
├── config/                            # 配置文件
│   └── skills/                        # Skill YAML 配置
│       ├── navigate.yaml
│       ├── elevator.yaml
│       ├── arm.yaml
│       └── voice.yaml
│
└── memory/                            # SQLite 数据库
    └── conversation.db
```

---

## 三、安装步骤

### 3.1 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Ubuntu 20.04 / 22.04 |
| Python | 3.8+ |
| ROS | ROS1 Noetic |
| 内存 | 4GB+ (本地 LLM) / 2GB (远程 API) |
| 麦克风 | USB 麦克风或板载音频 |

### 3.2 安装依赖

```bash
# 1. 系统依赖
sudo apt update
sudo apt install -y     python3-pip     python3-dev     portaudio19-dev     espeak     espeak-data     libespeak1     ffmpeg     git

# 2. 克隆项目
cd ~
git clone https://github.com/horo2016/choyabot-agent-framework.git
cd choyabot-agent-framework

# 3. 安装 Python 依赖
pip install -r requirements.txt

# 4. 安装框架 (开发模式)
pip install -e .

# 5. 验证安装
choya --help
```

### 3.3 下载 Whisper 模型

```bash
# 安装 huggingface-hub
pip install huggingface-hub

# 使用国内镜像下载模型
export HF_ENDPOINT=https://hf-mirror.com

# 下载 base 模型 (约 150MB，推荐)
huggingface-cli download Systran/faster-whisper-base     --local-dir ~/whisper-models/base     --local-dir-use-symlinks False

# 或下载 tiny 模型 (约 40MB，更快但精度稍低)
huggingface-cli download Systran/faster-whisper-tiny     --local-dir ~/whisper-models/tiny     --local-dir-use-symlinks False

# 验证
ls -lh ~/whisper-models/base/model.bin
```

### 3.4 配置 LLM (二选一)

#### 方案 A：本地 Ollama (推荐，零费用)

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取中文模型
ollama pull qwen2.5:7b

# 启动服务
ollama serve &

# 配置框架
choya config set llm.url http://localhost:11434/v1/chat/completions
choya config set llm.model qwen2.5:7b
choya config set llm.key ""
```

#### 方案 B：远程 API (DeepSeek/SiliconFlow)

```bash
# 注册获取 API Key: https://platform.deepseek.com
choya config set llm.url https://api.deepseek.com/v1/chat/completions
choya config set llm.model deepseek-chat
choya config set llm.key "sk-your-api-key"

# 验证配置
choya config get llm
```

### 3.5 音频权限

```bash
# 添加用户到 audio 组
sudo usermod -a -G audio $USER
newgrp audio

# 测试麦克风
arecord -D plughw:1,0 -d 3 -f S16_LE -r 16000 -c 1 test.wav
aplay test.wav
```

---

## 四、使用说明

### 4.1 初始化项目

```bash
choya init
```

输出：
```
🚀 初始化 ChoyaBot Agent 项目...
  ✅ 创建示例技能: navigate

🧠 LLM 配置:
   🖥️ 本地 (Ollama) | URL: http://localhost:11434/v1/chat/completions | 模型: qwen2.5:7b | Key: 未设置

✅ 初始化完成
   技能目录: /home/horo2016/choyabot-agent-framework/skills
   配置目录: /home/horo2016/choyabot-agent-framework/config/skills
```

### 4.2 查看和管理技能

```bash
# 列出已安装技能
choya skill list

# 添加本地技能
choya skill add --file ./my_elevator_skill.py --config ./my_elevator.yaml

# 从 Git 仓库添加技能
choya skill add --git https://github.com/xxx/choya-skill-vision.git

# 查看技能详情
choya skill info navigate

# 移除技能
choya skill remove navigate
```

### 4.3 启动 Agent

```bash
# 启动 (需要先运行 roscore)
roscore &
choya run
```

交互示例：
```
🚀 启动 ChoyaBot Agent...

🧠 LLM: 🖥️ 本地 (Ollama) | URL: http://localhost:11434/v1/chat/completions | 模型: qwen2.5:7b

[INFO] 🤖 ChoyaBot Agent 启动
[INFO]    技能: ['navigate', 'voice']
[INFO] 🚀 启动常驻 Skill: voice
[INFO] ✅ Porcupine: terminator
[INFO] ⏳ 加载 Whisper...
[INFO] ✅ Whisper 就绪 (0.3s)
[INFO] ✅ TTS 就绪
[INFO] 👂 监听唤醒词...

用户: "terminator"
🔔 检测到唤醒词！
用户: "去一楼按电梯"
🎯 识别结果: 去一楼按电梯
🧠 LLM 思考中...
🧠 执行计划: 2 步
🔧 执行: navigate({'target': '一楼电梯口'})
🔊 播报: 好的，正在前往一楼电梯口
🔧 执行: elevator({'direction': 'up'})
🔊 播报: 正在按上行按钮
⏳ 连续对话 3s...
```

### 4.4 配置管理

```bash
# 查看所有配置
choya config list

# 查看单项
choya config get llm.url

# 设置配置
choya config set llm.model qwen2.5:7b
choya config set voice.wake_word jarvis

# 删除配置
choya config delete llm.key
```

---

## 五、核心模块详解

### 5.1 Skill 基类 (skills/base_skill.py)

所有机器人技能必须继承 `BaseSkill`：

```python
from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult

class MySkill(BaseSkill):
    def __init__(self):
        super().__init__()
        # 初始化 ROS 发布器等

    def get_description(self) -> str:
        """返回技能描述，LLM 靠这个理解技能用途"""
        return "描述这个技能能做什么"

    def get_parameters(self) -> dict:
        """返回参数 schema，LLM 靠这个生成正确参数"""
        return {
            'param_name': {
                'type': 'string',      # string/number/boolean/enum
                'description': '参数说明',
                'required': True       # 是否必填
            }
        }

    def execute(self, params: dict) -> SkillResult:
        """执行技能

        Args:
            params: LLM 生成的参数字典

        Returns:
            SkillResult(success, message, data, error)
        """
        try:
            # 执行业务逻辑
            return SkillResult(True, "执行成功", data={"key": "value"})
        except Exception as e:
            return SkillResult(False, f"失败: {e}", error=str(e))
```

### 5.2 Skill 注册表 (core/skill_registry.py)

**核心功能：**
- **自动发现**：扫描 `skills/` 目录，自动加载 `*_skill.py` 文件
- **热重载**：文件修改后自动重新加载，无需重启
- **参数校验**：根据 `get_parameters()` 自动校验 LLM 生成的参数

**工作原理：**
```python
registry = SkillRegistry()
registry.load_all()  # 加载所有技能

skill = registry.get("navigate")  # 获取技能实例
result = skill.execute({"target": "一楼"})  # 执行
```

### 5.3 LLM 规划器 (core/planner.py)

**核心功能：**
- 将用户自然语言指令发送给 LLM
- LLM 根据可用技能描述，返回结构化 JSON 执行计划

**System Prompt 设计：**
```
你是一个机器人任务规划助手。

可用技能：
- navigate: 移动到指定位置（参数：target）
- elevator: 操作电梯（参数：direction）
- arm: 机械臂操作（参数：action, target）

规则：
1. 每个步骤必须对应一个可用技能
2. 参数必须严格符合技能的参数 schema
3. 复杂任务拆分为多个串行步骤

返回严格 JSON：
{
    "thought": "思考过程",
    "plan": [
        {"step": 1, "skill": "navigate", "params": {"target": "一楼"}, "reason": "原因"}
    ],
    "reply": "给用户的自然语言回复",
    "need_confirm": false
}
```

### 5.4 记忆系统 (core/memory.py)

**SQLite 存储结构：**
```sql
CREATE TABLE conversations (
    id INTEGER PRIMARY KEY,
    session_id TEXT,      -- 会话ID
    role TEXT,            -- user/assistant/system
    content TEXT,         -- 内容
    metadata TEXT,        -- JSON 元数据
    timestamp REAL        -- 时间戳
);
```

**用途：**
- 多轮对话上下文
- 任务执行历史回溯
- 用户偏好记忆

### 5.5 配置管理 (core/config_manager.py)

**配置文件位置：** `~/.choya/config.yaml`

**默认配置：**
```yaml
llm:
  url: http://localhost:11434/v1/chat/completions
  model: qwen2.5:7b
  key: ""

voice:
  wake_word: jarvis
  model_path: ~/whisper-models/base
  audio_device: null
```

---

## 六、Skill 开发教程

### 6.1 开发一个新 Skill (以电梯控制为例)

**Step 1: 创建 Skill 文件 `skills/elevator_skill.py`**

```python
#!/usr/bin/env python3
import rospy
from std_msgs.msg import String
import json
from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult


class ElevatorSkill(BaseSkill):
    def __init__(self):
        super().__init__()
        # 创建 ROS 发布器
        self.pub = rospy.Publisher('/elevator/command', String, queue_size=1)

    def get_description(self) -> str:
        """LLM 靠这个理解技能用途"""
        return "操作电梯系统，包括按上行/下行按钮、前往指定楼层"

    def get_parameters(self) -> dict:
        """LLM 靠这个生成正确参数"""
        return {
            'action': {
                'type': 'enum',
                'enum': ['press_up', 'press_down', 'go_floor'],
                'description': '操作类型：按上行、按下行、去某层',
                'required': True
            },
            'floor': {
                'type': 'string',
                'description': '目标楼层，如"1"、"2"、"3"',
                'required': False
            }
        }

    def execute(self, params: dict) -> SkillResult:
        """执行业务逻辑"""
        action = params['action']

        try:
            if action == 'press_up':
                self.pub.publish(json.dumps({'action': 'press', 'direction': 'up'}))
                return SkillResult(True, "已按上行按钮")
            elif action == 'press_down':
                self.pub.publish(json.dumps({'action': 'press', 'direction': 'down'}))
                return SkillResult(True, "已按下行按钮")
            elif action == 'go_floor':
                floor = params.get('floor', '')
                if not floor:
                    return SkillResult(False, "缺少楼层参数", error="missing_floor")
                self.pub.publish(json.dumps({'action': 'go', 'floor': floor}))
                return SkillResult(True, f"正在前往 {floor} 层")
            else:
                return SkillResult(False, f"未知操作: {action}", error="invalid_action")
        except Exception as e:
            return SkillResult(False, f"执行失败: {e}", error=str(e))
```

**Step 2: 创建 YAML 配置 `config/skills/elevator.yaml`**

```yaml
name: elevator
version: 1.0.0
description: 操作电梯系统，包括按按钮、选择楼层
author: your_name
tags: [elevator, building]

parameters:
  action:
    type: enum
    enum: [press_up, press_down, go_floor]
    description: 电梯操作类型
    required: true
  floor:
    type: string
    description: 目标楼层
    required: false

ros:
  topics:
    - name: /elevator/command
      type: std_msgs/String
      direction: publish

timeout: 15.0
```

**Step 3: 安装并测试**

```bash
# 复制文件到项目目录
cp elevator_skill.py choyabot-agent-framework/skills/
cp elevator.yaml choyabot-agent-framework/config/skills/

# 或使用 CLI
choya skill add --file ./elevator_skill.py --config ./elevator.yaml

# 查看是否加载
choya skill list

# 启动测试
choya run
# 说: "Jarvis, 按上行按钮"
```

### 6.2 Skill 开发规范

| 规范 | 说明 |
|------|------|
| 文件名 | `xxx_skill.py`，类名 `XxxSkill` |
| 继承 | 必须继承 `BaseSkill` |
| 描述 | `get_description()` 要清晰，LLM 靠它理解 |
| 参数 | `get_parameters()` 要完整，包含 type/description/required |
| 执行 | `execute()` 返回 `SkillResult`，成功/失败都要处理 |
| 配置 | 必须配套 YAML 文件，放在 `config/skills/` |

### 6.3 参数类型对照表

| type | Python 类型 | 示例值 |
|------|------------|--------|
| string | str | "一楼" |
| number | int/float | 3.5 |
| boolean | bool | true |
| enum | str (限定范围) | "up" / "down" |

---

## 七、二次开发指南

### 7.1 修改 LLM System Prompt

编辑 `core/planner.py`，修改 `system_prompt`：

```python
system_prompt = f"""你是一个机器人任务规划助手。

可用技能：
{skills_desc}

【在这里添加你的自定义规则】
- 规则1: xxx
- 规则2: xxx

返回严格 JSON：
{{
    "thought": "思考过程",
    "plan": [...],
    "reply": "回复"
}}
"""
```

### 7.2 添加新的 ROS 话题桥接

在 Skill 的 `execute()` 里发布到任意 ROS 话题：

```python
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

class VisionSkill(BaseSkill):
    def __init__(self):
        self.pub = rospy.Publisher('/camera/command', String, queue_size=1)
        self.img_pub = rospy.Publisher('/camera/snapshot', Image, queue_size=1)
```

### 7.3 自定义语音唤醒词

1. 访问 [Picovoice Console](https://console.picovoice.ai/)
2. 训练自定义唤醒词（中文支持）
3. 下载 `.ppn` 文件
4. 修改 `voice_skill.py`：

```python
self.porcupine = pvporcupine.create(
    access_key="你的API_KEY",
    keyword_paths=["/path/to/你的唤醒词.ppn"]
)
```

### 7.4 更换语音识别模型

```bash
# 下载更大的模型（更准但更慢）
huggingface-cli download Systran/faster-whisper-small     --local-dir ~/whisper-models/small

# 修改配置
choya config set voice.model_path ~/whisper-models/small
```

### 7.5 调试技巧

```bash
# 1. 查看 ROS 话题
rostopic list | grep agent
rostopic echo /agent/input
rostopic echo /voice/tts_text

# 2. 手动发布测试
rostopic pub /agent/input std_msgs/String "data: '去一楼'"

# 3. 查看日志
choya run 2>&1 | tee agent.log

# 4. 测试 LLM 连通性
curl http://localhost:11434/v1/chat/completions   -H "Content-Type: application/json"   -d '{"model":"qwen2.5:7b","messages":[{"role":"user","content":"hi"}]}'
```

---

## 八、常见问题 FAQ

### Q1: 麦克风没有声音？

```bash
# 检查设备
arecord -l

# 检查权限
groups | grep audio

# 测试录音
arecord -D plughw:1,0 -d 3 test.wav
```

### Q2: Whisper 模型加载失败？

```bash
# 检查文件大小
ls -lh ~/whisper-models/base/model.bin  # 应约 150MB

# 重新下载
huggingface-cli download Systran/faster-whisper-base     --local-dir ~/whisper-models/base --local-dir-use-symlinks False
```

### Q3: LLM 返回 None？

```bash
# 检查 Ollama 是否运行
curl http://localhost:11434/api/tags

# 或检查远程 API Key
choya config get llm.key
```

### Q4: Skill 热加载不生效？

确保 `skill_registry.py` 中的 `Observer` 正在运行，且文件修改后保存。

### Q5: Python 3.8 类型注解报错？

使用 `typing` 模块：
```python
from typing import Tuple, Optional, Dict, List
# 用 Tuple[bool, str] 而不是 tuple[bool, str]
```

---

## 九、扩展阅读

| 组件 | 文档 |
|------|------|
| Porcupine | https://picovoice.ai/docs/quick-start/porcupine-python/ |
| Faster-Whisper | https://github.com/SYSTRAN/faster-whisper |
| Ollama | https://github.com/ollama/ollama |
| ROS1 | http://wiki.ros.org/ROS/Tutorials |

---

## 十、课程作业建议

1. **基础作业**：安装框架，成功运行 `choya run`，完成一次语音交互
2. **Skill 开发**：编写一个控制 LED 灯的 Skill，通过语音开关灯
3. **LLM 调优**：修改 System Prompt，让机器人能处理更复杂的任务链
4. **项目实战**：为实验室机器人添加语音控制功能（导航+抓取+放置）

---

> **文档版本**: v1.0.0
> **最后更新**: 2026-05-13
> **项目地址**: https://github.com/horo2016/choyabot-agent-framework



录制课程建议
第1课（45min）：概述 + 安装 + 启动演示
第2课（45min）：核心原理 + Skill开发实战
第3课（45min）：二次开发 + 项目实战
学生看完这份文档后，应该能够：
✅ 独立安装并运行框架
✅ 理解 Agent → Planner → Skill → ROS 的数据流
✅ 编写自己的 Skill 并热加载
✅ 修改 LLM Prompt 适配新场景
✅ 完成课程作业（语音控制机器人）
