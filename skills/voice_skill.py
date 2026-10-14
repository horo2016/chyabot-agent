#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
voice_skill.py
语音交互 Skill：Porcupine 唤醒 + Faster-Whisper 识别 + pyttsx3/edge-tts TTS
作为 ChoyaBot Agent 的可插拔 Skill 运行
"""
import os
os.environ['PA_ALSA_PLUGHW'] = '1'   # ← 必须在所有 import 的最前面
import rospy
from std_msgs.msg import String, Bool
import sounddevice as sd
import numpy as np
import pvporcupine
from faster_whisper import WhisperModel
import pyttsx3
import threading
import queue
import time
import os
import sys
from pathlib import Path
import asyncio
import tempfile
import shutil
import subprocess

from choyabot_agent_framework.skills.base_skill import BaseSkill, SkillResult
'''
Python 3.8.10 (default, Mar 18 2025, 20:04:55)
[GCC 9.4.0] on linux
Type "help", "copyright", "credits" or "license" for more information.
>>> import sounddevice as sd
>>> for i, d in enumerate(sd.query_devices()):
...     if d['max_input_channels'] > 0:
...         print(f"[{i}] {d['name']}")
...
[0] USB PnP Sound Device: Audio (hw:0,0)
[1] icspring camera: USB Audio (hw:1,0)
[2] HDA Intel PCH: ALC897 Analog (hw:2,0)
[3] HDA Intel PCH: ALC897 Alt Analog (hw:2,2)
[9] sysdefault
[10] spdif
[11] samplerate
[12] speexrate
[13] pulse
[14] upmix
[15] vdownmix
[16] default

'''

class VoiceSkill(BaseSkill):
    """
    语音交互 Skill
    - 后台线程持续监听音频
    - 唤醒后录音 → 识别 → 发布 /agent/input
    - 接收 /voice/tts_text 执行播报
    """
    
    def __init__(self):
        super().__init__()
        self.name = "voice"
        
        # 参数（从 YAML 读取，也可 ROS param）
        self.wake_word = "computer"
        self.model_path = os.path.expanduser("~/whisper-models/base")
        self.device = None
        self.sample_rate = 16000
        self.blocksize = 512
        
        # VAD
        self.energy_threshold = 150
        self.silence_frames = 30
        self.min_speech_frames = 10
        self.max_frames = 300
        self.follow_up_timeout = 1.0
        self.follow_up_energy = 100
        
        # 组件
        self.porcupine = None
        self.whisper = None
        self.tts = None
        self.audio_queue = queue.Queue(maxsize=200)
        
        # 状态机
        self.state = "IDLE"  # IDLE | LISTENING | RECORDING | RECOGNIZING
        self.state_lock = threading.Lock()
        self.record_buffer = []
        self.follow_up_timer = None
        self.is_playing = False
        
        # 线程
        self.threads = []
        self.running = False
        
        # ROS（Skill 内部自建发布/订阅）
        self.input_pub = None   # 发布识别结果给 Agent
        self.tts_sub = None     # 接收外部 TTS 指令

        # ===== 新增：TTS 引擎配置 =====
        self.tts_engine = "edge-tts"      # "pyttsx3" | "edge-tts"
        self.edge_voice = "zh-CN-XiaoxiaoNeural"
        
    def get_description(self) -> str:
        return "语音交互系统：唤醒词识别、语音转文字、语音合成播报"
        
    def get_parameters(self) -> dict:
        return {
            "wake_word": {
                "type": "string",
                "description": "唤醒词名称，如 computer",
                "required": False,
                "default": "computer"
            },
            "model_path": {
                "type": "string",
                "description": "Whisper 本地模型路径",
                "required": False,
                "default": "~/whisper-models/base"
            },
            "audio_device": {
                "type": "number",
                "description": "音频设备索引，None 表示默认",
                "required": False,
                "default": None
            },
            # ===== 新增参数 =====
            "tts_engine": {
                "type": "string",
                "description": "TTS引擎: pyttsx3(离线) 或 edge-tts(在线)",
                "required": False,
                "default": "pyttsx3"
            },
            "edge_voice": {
                "type": "string",
                "description": "Edge-TTS 音色，如 zh-CN-XiaoxiaoNeural",
                "required": False,
                "default": "zh-CN-XiaoxiaoNeural"
            }
        }
        
    def execute(self, params: dict) -> SkillResult:
        """
        启动语音交互后台线程
        返回启动状态，实际运行在后台
        """
        self.wake_word = params.get("wake_word", self.wake_word)
        self.model_path = os.path.expanduser(params.get("model_path", self.model_path))
        self.device = params.get("audio_device", self.device)
        # ===== 新增：读取 TTS 配置 =====
        self.tts_engine = params.get("tts_engine", self.tts_engine)
        self.edge_voice = params.get("edge_voice", self.edge_voice)
        
        try:
            self._init_ros()
            self._init_porcupine()
            self._init_whisper()
            self._init_tts()
            
            self.running = True
            
            # 启动音频采集线程
            t1 = threading.Thread(target=self._audio_producer, daemon=True)
            t1.start()
            self.threads.append(t1)
            
            # 启动处理循环线程
            t2 = threading.Thread(target=self._process_loop, daemon=True)
            t2.start()
            self.threads.append(t2)
            
            rospy.loginfo("🎤 Voice Skill 后台启动完成")
            return SkillResult(
                True,
                f"语音系统已启动，唤醒词: {self.wake_word}",
                data={"wake_word": self.wake_word, "model": self.model_path}
            )
            
        except Exception as e:
            return SkillResult(False, f"语音启动失败: {e}", error=str(e))
            
    def cancel(self):
        """停止语音 Skill"""
        self.running = False
        if self.follow_up_timer and self.follow_up_timer.is_alive():
            self.follow_up_timer.cancel()
        if self.porcupine:
            self.porcupine.delete()
        rospy.loginfo("🛑 Voice Skill 已停止")
        
    # ==================== 初始化 ====================
    
    def _init_ros(self):
        """初始化 ROS 发布/订阅"""
        self.input_pub = rospy.Publisher("/agent/input", String, queue_size=10)
        self.status_pub = rospy.Publisher("/voice/status", String, queue_size=10)
        self.tts_sub = rospy.Subscriber("/voice/tts_text", String, self._tts_callback)
        
    def _init_porcupine(self):
        self.porcupine = pvporcupine.create(keywords=[self.wake_word])
        self.frame_length = self.porcupine.frame_length
        rospy.loginfo(f"✅ Porcupine: {self.wake_word}")
        
    def _init_whisper(self):
        rospy.loginfo(f"⏳ 加载 Whisper...")
        t0 = time.time()
        self.whisper = WhisperModel(
            self.model_path,
            device="cpu",
            compute_type="int8",
            cpu_threads=2,
            num_workers=1,
            local_files_only=True
        )
        rospy.loginfo(f"✅ Whisper 就绪 ({time.time()-t0:.1f}s)")
        
    def _init_tts(self):
        """初始化 TTS（支持 pyttsx3 / edge-tts 切换）"""
        if self.tts_engine == "pyttsx3":
            try:
                self.tts = pyttsx3.init()
                self.tts.setProperty("rate", 150)
                self.tts.setProperty("volume", 0.9)
                voices = self.tts.getProperty("voices")
                for v in voices:
                    if "chinese" in v.name.lower() or "zh" in v.id.lower():
                        self.tts.setProperty("voice", v.id)
                        break
                rospy.loginfo("✅ TTS 就绪 (pyttsx3)")
            except Exception as e:
                rospy.logerr(f"❌ pyttsx3 初始化失败: {e}")
                self.tts = None
                
        elif self.tts_engine == "edge-tts":
            try:
                import edge_tts  # 仅做导入验证
                self.tts = None  # edge-tts 无需持久化句柄
                rospy.loginfo(f"✅ TTS 就绪 (edge-tts, 音色: {self.edge_voice})")
            except ImportError:
                rospy.logerr("❌ edge-tts 未安装，请执行: pip install edge-tts")
                self.tts = None
        else:
            rospy.logerr(f"❌ 未知 TTS 引擎: {self.tts_engine}")
            
    # ==================== 音频回调 ====================
    
    def _audio_producer(self):
        """音频采集线程"""
        rospy.loginfo("🎙️ 启动音频采集...")
        rospy.loginfo(f"🎙️ 使用音频设备 [{self.device}]")
        stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype=np.float32,
            blocksize=self.blocksize,
            device=self.device,
            callback=self._audio_callback
        )
        
        with stream:
            rospy.loginfo("✅ 音频流已启动")
            while self.running and not rospy.is_shutdown():
                time.sleep(0.1)
                
    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice 回调"""
        if status:
            rospy.logwarn(f"Audio: {status}")
        if self.is_playing:
            return
            
        pcm_int16 = (indata[:, 0] * 32767).astype(np.int16)
        
        try:
            self.audio_queue.put_nowait(pcm_int16)
        except queue.Full:
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.put_nowait(pcm_int16)
            except queue.Empty:
                pass
                
    # ==================== 处理循环 ====================
    
    def _process_loop(self):
        """主处理循环"""
        rospy.loginfo("👂 开始监听唤醒词...")
        
        while self.running and not rospy.is_shutdown():
            try:
                pcm = self.audio_queue.get(timeout=1.0)
            except queue.Empty:
                continue
                
            state = self._get_state()
            
            if state == "IDLE":
                self._handle_idle(pcm)
            elif state == "LISTENING":
                self._handle_listening(pcm)
            elif state == "RECORDING":
                self._handle_recording(pcm)
                
    def _handle_idle(self, pcm):
        """IDLE：监听唤醒词"""
        if len(pcm) >= self.frame_length:
            if self.porcupine.process(pcm[:self.frame_length]) >= 0:
                rospy.loginfo("🔔 检测到唤醒词！")
                # ===== 新增：唤醒回应 =====
                self._speak("在的")
                
                self._set_state("RECORDING")
                self.record_buffer = [np.zeros(self.blocksize, dtype=np.int16)]
                self.silence_count = 0
                self.speech_count = 0
                self.total_frames = 0
                
    def _handle_listening(self, pcm):
        """LISTENING：连续对话等待"""
        energy = np.abs(pcm).mean()
        if energy > self.follow_up_energy:
            rospy.loginfo("🗣️ 检测到后续指令")
            self._set_state("RECORDING")
            self.record_buffer = []
            self.silence_count = 0
            self.speech_count = 0
            self.total_frames = 0
            
    def _handle_recording(self, pcm):
        """RECORDING：VAD 录音"""
        self.record_buffer.append(pcm.copy())
        self.total_frames += 1
        
        energy = np.abs(pcm).mean()
        if energy > self.energy_threshold:
            self.speech_count += 1
            self.silence_count = 0
        else:
            self.silence_count += 1
            
        # 实时音量条
        bar_len = int(min(energy / 2000, 1.0) * 40)
        bar = "█" * bar_len + "░" * (40 - bar_len)
        sys.stdout.write(f"\r🔴 REC [{self.total_frames:3d}] {bar} {energy:4.0f}")
        sys.stdout.flush()
        
        should_stop = False
        if self.speech_count > 0 and self.silence_count >= self.silence_frames:
            should_stop = True
        elif self.total_frames >= self.max_frames:
            should_stop = True
            
        if should_stop:
            sys.stdout.write("\n")
            sys.stdout.flush()
            print(f'speech_count: {self.speech_count}')
            if self.speech_count >= self.min_speech_frames:
                self._start_recognize()
            else:
                self._goto_idle()
                
    def _start_recognize(self):
        """启动识别"""
        audio_np = np.concatenate(self.record_buffer)
        self.record_buffer = []
        self._set_state("RECOGNIZING")
        threading.Thread(target=self._recognize_thread, args=(audio_np,), daemon=True).start()
        
    def _recognize_thread(self, audio_np):
        """识别线程"""
        try:
            audio_float = audio_np.astype(np.float32) / 32768.0
            segments, _ = self.whisper.transcribe(
                audio_float,
                language="zh",
                beam_size=2,
                best_of=2,
                vad_filter=True,
                task="transcribe",
                temperature=0.1,          # 降低随机性
                condition_on_previous_text=True
            )
            text = " ".join([s.text for s in segments]).strip()
            
            if text:
                rospy.loginfo(f"🎯 识别结果: {text}")
                self.input_pub.publish(text)  # ← 发布给 Agent
                
                # 连续对话等待
                self._start_follow_up()
            else:
                self._goto_idle()
                
        except Exception as e:
            rospy.logerr(f"❌ 识别错误: {e}")
            self._goto_idle()
            
    def _start_follow_up(self):
        """连续对话"""
        self._set_state("LISTENING")
        if self.follow_up_timer and self.follow_up_timer.is_alive():
            self.follow_up_timer.cancel()
        self.follow_up_timer = threading.Timer(self.follow_up_timeout, self._follow_up_timeout)
        self.follow_up_timer.start()
        
    def _follow_up_timeout(self):
        if self._get_state() == "LISTENING":
            self._goto_idle()
            
    def _goto_idle(self):
        if self.follow_up_timer and self.follow_up_timer.is_alive():
            self.follow_up_timer.cancel()
        self._set_state("IDLE")
        rospy.loginfo("👂 监听唤醒词...")
        
    # ==================== TTS ====================
    
    def _tts_callback(self, msg):
        """接收 TTS 指令"""
        text = msg.data
        threading.Thread(target=self._speak, args=(text,), daemon=True).start()
        
    def _speak(self, text):
        """TTS 分发入口（支持引擎切换）"""
        if not text:
            return
        rospy.loginfo(f"🔊 播报({self.tts_engine}): {text}")
        self.is_playing = True
        try:
            if self.tts_engine == "pyttsx3":
                self._speak_pyttsx3(text)
            elif self.tts_engine == "edge-tts":
                self._speak_edge(text)
            else:
                rospy.logerr(f"❌ 未知 TTS 引擎: {self.tts_engine}")
        except Exception as e:
            rospy.logerr(f"❌ TTS 错误: {e}")
        finally:
            self.is_playing = False
            
    def _speak_pyttsx3(self, text):
        """离线 TTS（原逻辑）"""
        if not self.tts:
            rospy.logerr("❌ pyttsx3 未初始化")
            return
        self.tts.say(text)
        self.tts.runAndWait()
        
    def _speak_edge(self, text):
        """在线 Edge-TTS：生成 mp3 → 调用系统播放器"""
        import edge_tts
        
        async def _do_speak():
            communicate = edge_tts.Communicate(text=text, voice=self.edge_voice)
            
            # 生成临时 mp3
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                mp3_path = f.name
                await communicate.save(mp3_path)
            
            # 查找可用播放器（优先 mpg123，其次 ffplay）
            player = None
            for cmd in [["mpg123", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]]:
                if shutil.which(cmd[0]):
                    player = cmd
                    break
            
            if player:
                subprocess.run(['mpg123', '-o', 'pulse', '-q', mp3_path],capture_output=True)
                #subprocess.run(player + [mp3_path], check=False)
            else:
                rospy.logerr("❌ 未找到 mp3 播放器，请安装 mpg123 或 ffplay")
            
            # 清理临时文件
            try:
                os.unlink(mp3_path)
            except Exception:
                pass
        
        # 在新事件循环中运行异步 TTS
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_do_speak())
            loop.close()
        except Exception as e:
            rospy.logerr(f"❌ Edge-TTS 错误: {e}")
            
    # ==================== 状态管理 ====================
    
    def _set_state(self, state):
        with self.state_lock:
            self.state = state
            
    def _get_state(self):
        with self.state_lock:
            return self.state