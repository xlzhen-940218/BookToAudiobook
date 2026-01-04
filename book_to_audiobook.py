#!/usr/bin/env python3
"""
小说/文章转有声书工具
使用DeepSeek API分析文本，edge-tts进行语音合成，ffmpeg合并音频
"""

import os
import sys
import asyncio
import json
import yaml
import re
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import aiohttp
import edge_tts
from edge_tts import VoicesManager
import subprocess


class Config:
    """配置管理类"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 尝试从api_keys.yaml加载API密钥
            api_keys_config = self._load_api_keys()
            
            # 如果api_keys.yaml中存在deepseek配置，合并到主配置中
            if api_keys_config and 'deepseek' in api_keys_config:
                if 'deepseek' not in config:
                    config['deepseek'] = {}
                
                # 合并API密钥配置，api_keys.yaml中的配置优先级更高
                for key, value in api_keys_config['deepseek'].items():
                    config['deepseek'][key] = value
            
            return config
        except FileNotFoundError:
            print(f"配置文件 {self.config_path} 不存在，使用默认配置")
            return self.get_default_config()
        except yaml.YAMLError as e:
            print(f"配置文件解析错误: {e}")
            sys.exit(1)
    
    def _load_api_keys(self) -> Optional[Dict[str, Any]]:
        """加载API密钥配置文件"""
        api_keys_paths = [
            "api_keys.yaml",
            "api_keys.yml",
            ".api_keys.yaml",
            ".api_keys.yml",
            "config/api_keys.yaml",
            "config/api_keys.yml"
        ]
        
        for path in api_keys_paths:
            try:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        return yaml.safe_load(f)
            except (yaml.YAMLError, IOError) as e:
                print(f"警告: 无法加载API密钥文件 {path}: {e}")
        
        # 如果找不到API密钥文件，尝试从环境变量读取
        api_key_from_env = os.environ.get('DEEPSEEK_API_KEY')
        if api_key_from_env:
            print("从环境变量 DEEPSEEK_API_KEY 读取API密钥")
            return {
                'deepseek': {
                    'api_key': api_key_from_env
                }
            }
        
        print("警告: 未找到API密钥配置文件，请创建 api_keys.yaml 文件或设置 DEEPSEEK_API_KEY 环境变量")
        return None
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        # 尝试从API密钥文件或环境变量获取API密钥
        api_keys_config = self._load_api_keys()
        api_key = 'your-api-key-here'  # 默认值
        
        if api_keys_config and 'deepseek' in api_keys_config:
            api_key = api_keys_config['deepseek'].get('api_key', 'your-api-key-here')
        
        return {
            'deepseek': {
                'api_key': api_key,
                'base_url': 'https://api.deepseek.com',
                'model': 'deepseek-chat'
            },
            'tts': {
                'narrator_voice': 'zh-CN-XiaoxiaoNeural',
                'character_voices': {
                    'default': 'zh-CN-YunxiNeural',
                    'character_genders': {},
                    'random_assignment': True,
                    'available_chinese_voices': [
                        'zh-CN-XiaoxiaoNeural',
                        'zh-CN-YunxiNeural',
                        'zh-CN-YunyangNeural',
                        'zh-CN-XiaoyiNeural'
                    ],
                    'male_voices': [
                        'zh-CN-YunxiNeural',
                        'zh-CN-YunyangNeural'
                    ],
                    'female_voices': [
                        'zh-CN-XiaoxiaoNeural',
                        'zh-CN-XiaoyiNeural'
                    ]
                },
                'rate': '+0%',
                'volume': '+0%',
                'pitch': '+0Hz',
                'gender_pitch_adjustment': {
                    'enabled': True,
                    'male_pitch': '-10Hz',
                    'female_pitch': '+10Hz',
                    'default_pitch': '+0Hz'
                }
            },
            'audio': {
                'output_format': 'mp3',
                'sample_rate': 24000,
                'bitrate': '48k',
                'temp_dir': 'temp_audio',
                'output_dir': 'output'
            },
            'text': {
                'max_chunk_length': 1000,
                'preserve_punctuation': True
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value


class DeepSeekAnalyzer:
    """DeepSeek API文本分析器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.api_key = config.get('deepseek.api_key')
        self.base_url = config.get('deepseek.base_url')
        self.model = config.get('deepseek.model')
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def analyze_text(self, text: str) -> List[Dict[str, Any]]:
        """
        分析文本，识别旁白和角色对话
        
        返回格式:
        [
            {
                "type": "narrator" | "character",
                "character": "角色名" (如果是角色对话),
                "text": "文本内容",
                "voice": "音色名称"
            },
            ...
        ]
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        # 构建提示词
        prompt = self._build_prompt(text)
        
        # 调用DeepSeek API
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个专业的文本分析助手，专门分析小说和文章中的旁白和角色对话。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 4000
        }
        
        try:
            async with self.session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    analysis_result = result['choices'][0]['message']['content']
                    return self._parse_analysis_result(analysis_result)
                else:
                    print(f"DeepSeek API错误: {response.status}")
                    # 如果API调用失败，使用简单的规则分析
                    return self._simple_analysis(text)
        except Exception as e:
            print(f"DeepSeek API调用异常: {e}")
            return self._simple_analysis(text)
    
    def _build_prompt(self, text: str) -> str:
        """构建分析提示词"""
        return f"""
请分析以下文本，识别出旁白和各个角色的对话，并推断每个角色的性别。文本内容：

{text[:2000]}...

请按照以下JSON格式返回分析结果：
[
  {{
    "type": "narrator",
    "text": "旁白文本内容",
    "voice": "narrator"
  }},
  {{
    "type": "character",
    "character": "角色名",
    "gender": "male/female/unknown",
    "text": "角色对话内容",
    "voice": "character_角色名"
  }},
  ...
]

规则：
1. 旁白：描述性文字、环境描写、心理活动等非对话内容
2. 角色对话：引号内的内容，如"你好"、「你好」、『你好』等
3. 如果无法确定角色名，使用"unknown"作为角色名
4. 推断角色性别：根据角色名字、上下文、称呼等推断性别
   - male: 男性角色
   - female: 女性角色  
   - unknown: 无法确定性别
5. 保持文本的原始顺序
6. 不要修改原始文本内容
"""
    
    def _parse_analysis_result(self, result: str) -> List[Dict[str, Any]]:
        """解析DeepSeek返回的分析结果"""
        try:
            # 尝试从结果中提取JSON
            json_match = re.search(r'\[.*\]', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                print("无法从API响应中提取JSON，使用简单分析")
                return self._simple_analysis(result)
        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
            return self._simple_analysis(result)
    
    def _simple_analysis(self, text: str) -> List[Dict[str, Any]]:
        """简单的文本分析（备用方案）"""
        segments = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 简单的规则：引号内的内容视为角色对话
            dialogue_pattern = r'["「」『』](.+?)["「」『』]'
            matches = list(re.finditer(dialogue_pattern, line))
            
            if matches:
                last_end = 0
                for match in matches:
                    # 添加引号前的文本作为旁白
                    if match.start() > last_end:
                        narrator_text = line[last_end:match.start()].strip()
                        if narrator_text:
                            segments.append({
                                "type": "narrator",
                                "text": narrator_text,
                                "voice": "narrator"
                            })
                    
                    # 添加对话作为角色
                    dialogue_text = match.group(1).strip()
                    if dialogue_text:
                        segments.append({
                            "type": "character",
                            "character": "unknown",
                            "text": dialogue_text,
                            "voice": "character_unknown"
                        })
                    
                    last_end = match.end()
                
                # 添加最后一段旁白
                if last_end < len(line):
                    narrator_text = line[last_end:].strip()
                    if narrator_text:
                        segments.append({
                            "type": "narrator",
                            "text": narrator_text,
                            "voice": "narrator"
                        })
            else:
                # 整行作为旁白
                segments.append({
                    "type": "narrator",
                    "text": line,
                    "voice": "narrator"
                })
        
        return segments


class TTSEngine:
    """语音合成引擎"""
    
    def __init__(self, config: Config):
        self.config = config
        self.voices_manager: Optional[VoicesManager] = None
        self.voice_cache: Dict[str, str] = {}  # 角色到音色的映射缓存
        self.character_voice_assignments: Dict[str, str] = {}  # 角色分配的音色
        self.character_gender_cache: Dict[str, str] = {}  # 角色性别缓存
    
    async def initialize(self):
        """初始化语音管理器"""
        self.voices_manager = await VoicesManager.create()
    
    def get_character_gender(self, character_name: str, segment: Dict[str, Any] = None) -> str:
        """获取角色性别"""
        # 1. 首先检查segment中是否有API返回的gender字段（优先级最高）
        if segment and 'gender' in segment:
            gender = segment['gender']
            if gender in ['male', 'female']:
                self.character_gender_cache[character_name] = gender
                return gender
        
        # 2. 检查是否已经在缓存中
        if character_name in self.character_gender_cache:
            return self.character_gender_cache[character_name]
        
        # 3. 检查配置文件中的性别配置
        character_genders = self.config.get('tts.character_voices.character_genders', {})
        if character_name in character_genders:
            gender = character_genders[character_name]
            self.character_gender_cache[character_name] = gender
            return gender
        
        # 4. 根据角色名字推断性别（简单的中文名字推断）
        # 常见女性名字特征：芳、玲、娜、婷、娟、丽、敏、静、燕、红、秀、英、梅等
        # 常见男性名字特征：强、伟、刚、勇、军、杰、涛、明、建、平、波、峰、龙等
        female_patterns = ['芳', '玲', '娜', '婷', '娟', '丽', '敏', '静', '燕', '红', '秀', '英', '梅', '花', '兰', '玉', '珍', '芬', '萍']
        male_patterns = ['强', '伟', '刚', '勇', '军', '杰', '涛', '明', '建', '平', '波', '峰', '龙', '虎', '雄', '斌', '浩', '宇', '飞']
        
        for pattern in female_patterns:
            if pattern in character_name:
                self.character_gender_cache[character_name] = 'female'
                return 'female'
        
        for pattern in male_patterns:
            if pattern in character_name:
                self.character_gender_cache[character_name] = 'male'
                return 'male'
        
        # 5. 默认性别（根据配置或默认值）
        default_gender = 'male'  # 默认设为男性
        self.character_gender_cache[character_name] = default_gender
        return default_gender
    
    def get_voice_for_segment(self, segment: Dict[str, Any]) -> str:
        """根据片段类型获取音色"""
        voice_config = self.config.get('tts', {})
        
        if segment['type'] == 'narrator':
            return voice_config.get('narrator_voice', 'zh-CN-XiaoxiaoNeural')
        else:  # character
            character = segment.get('character', 'default')
            character_voices_config = voice_config.get('character_voices', {})
            
            # 1. 首先检查是否有特定角色的音色配置（优先级最高）
            if character in character_voices_config and character_voices_config[character] != 'default':
                return character_voices_config[character]
            
            # 2. 检查是否已经为该角色分配了音色（确保同一角色音色一致）
            if character in self.character_voice_assignments:
                return self.character_voice_assignments[character]
            
            # 3. 获取角色性别（使用API返回的gender信息）
            character_gender = self.get_character_gender(character, segment)
            
            # 4. 根据性别选择音色
            male_voices = character_voices_config.get('male_voices', [])
            female_voices = character_voices_config.get('female_voices', [])
            
            if character_gender == 'male' and male_voices:
                # 为男角色选择男声音色
                import random
                selected_voice = random.choice(male_voices)
                self.character_voice_assignments[character] = selected_voice
                print(f"为男角色 '{character}' 分配音色: {selected_voice}")
                return selected_voice
            elif character_gender == 'female' and female_voices:
                # 为女角色选择女声音色
                import random
                selected_voice = random.choice(female_voices)
                self.character_voice_assignments[character] = selected_voice
                print(f"为女角色 '{character}' 分配音色: {selected_voice}")
                return selected_voice
            
            # 5. 如果性别音色不可用，使用随机分配
            random_assignment = character_voices_config.get('random_assignment', True)
            available_voices = character_voices_config.get('available_chinese_voices', [])
            
            if random_assignment and available_voices:
                import random
                # 排除旁白音色，避免角色使用旁白音色
                narrator_voice = voice_config.get('narrator_voice', 'zh-CN-XiaoxiaoNeural')
                candidate_voices = [v for v in available_voices if v != narrator_voice]
                
                # 排除已经分配给其他角色的音色，确保每个角色音色不同
                assigned_voices = set(self.character_voice_assignments.values())
                available_candidate_voices = [v for v in candidate_voices if v not in assigned_voices]
                
                # 如果没有可用的不同音色，则使用所有候选音色（允许重复）
                if not available_candidate_voices:
                    available_candidate_voices = candidate_voices
                
                if available_candidate_voices:
                    selected_voice = random.choice(available_candidate_voices)
                    self.character_voice_assignments[character] = selected_voice
                    print(f"为角色 '{character}' 分配音色: {selected_voice}")
                    return selected_voice
            
            # 6. 使用默认音色
            default_voice = character_voices_config.get('default', 'zh-CN-YunxiNeural')
            self.character_voice_assignments[character] = default_voice
            return default_voice
    
    def get_pitch_for_segment(self, segment: Dict[str, Any], voice: str) -> str:
        """根据片段类型和音色获取pitch调整"""
        voice_config = self.config.get('tts', {})
        pitch_adjustment_config = voice_config.get('gender_pitch_adjustment', {})
        
        # 如果不启用pitch调整，返回默认pitch
        if not pitch_adjustment_config.get('enabled', True):
            return voice_config.get('pitch', '+0Hz')
        
        if segment['type'] == 'narrator':
            return voice_config.get('pitch', '+0Hz')
        else:  # character
            character = segment.get('character', 'default')
            character_gender = self.get_character_gender(character, segment)
            
            # 判断音色性别
            male_voices = self.config.get('tts.character_voices.male_voices', [])
            female_voices = self.config.get('tts.character_voices.female_voices', [])
            
            voice_gender = 'unknown'
            if voice in male_voices:
                voice_gender = 'male'
            elif voice in female_voices:
                voice_gender = 'female'
            
            # 如果音色性别与角色性别匹配，使用默认pitch
            if voice_gender == character_gender:
                return voice_config.get('pitch', '+0Hz')
            
            # 如果音色性别与角色性别不匹配，进行pitch调整
            if character_gender == 'male':
                # 男角色使用女声音色，降低pitch使其更低沉
                return pitch_adjustment_config.get('male_pitch', '-10Hz')
            elif character_gender == 'female':
                # 女角色使用男声音色，提高pitch使其更高亢
                return pitch_adjustment_config.get('female_pitch', '+10Hz')
            else:
                return pitch_adjustment_config.get('default_pitch', '+0Hz')
    
    async def synthesize_segment(self, segment: Dict[str, Any], output_path: str) -> bool:
        """合成单个文本片段为音频"""
        try:
            voice = self.get_voice_for_segment(segment)
            text = segment['text']
            
            # 获取语音参数
            rate = self.config.get('tts.rate', '+0%')
            volume = self.config.get('tts.volume', '+0%')
            base_pitch = self.config.get('tts.pitch', '+0Hz')
            
            # 获取性别相关的pitch调整
            gender_pitch = self.get_pitch_for_segment(segment, voice)
            
            # 如果启用了性别pitch调整，使用调整后的pitch
            pitch_adjustment_config = self.config.get('tts.gender_pitch_adjustment', {})
            if pitch_adjustment_config.get('enabled', True):
                pitch = gender_pitch
                # 显示pitch调整信息
                character = segment.get('character', 'unknown')
                if segment['type'] == 'character' and gender_pitch != base_pitch:
                    character_gender = self.get_character_gender(character)
                    print(f"角色 '{character}' ({character_gender}) 使用pitch调整: {gender_pitch}")
            else:
                pitch = base_pitch
            
            # 使用edge-tts合成语音
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice,
                rate=rate,
                volume=volume,
                pitch=pitch
            )
            
            await communicate.save(output_path)
            return True
            
        except Exception as e:
            print(f"语音合成失败: {e}")
            return False
    
    async def synthesize_all(self, segments: List[Dict[str, Any]], output_dir: str) -> List[str]:
        """合成所有文本片段"""
        if not self.voices_manager:
            await self.initialize()
        
        audio_files = []
        os.makedirs(output_dir, exist_ok=True)
        
        for i, segment in enumerate(segments):
            output_file = os.path.join(output_dir, f"segment_{i:04d}.mp3")
            print(f"正在合成第 {i+1}/{len(segments)} 段: {segment['text'][:50]}...")
            
            success = await self.synthesize_segment(segment, output_file)
            if success:
                audio_files.append(output_file)
            else:
                print(f"第 {i+1} 段合成失败，跳过")
        
        return audio_files


class AudioMerger:
    """音频合并器"""
    
    def __init__(self, config: Config):
        self.config = config
    
    def merge_audio_files(self, audio_files: List[str], output_file: str) -> bool:
        """使用ffmpeg合并音频文件"""
        if not audio_files:
            print("没有音频文件可合并")
            return False
        
        # 创建文件列表
        list_file = tempfile.mktemp(suffix='.txt')
        try:
            with open(list_file, 'w', encoding='utf-8') as f:
                for audio_file in audio_files:
                    f.write(f"file '{os.path.abspath(audio_file)}'\n")
            
            # 检查ffmpeg是否可用
            try:
                subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("ffmpeg未安装或不可用，请先安装ffmpeg")
                return False
            
            # 使用ffmpeg合并
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c', 'copy',
                output_file,
                '-y'  # 覆盖输出文件
            ]
            
            print(f"正在合并音频文件...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"音频合并完成: {output_file}")
                return True
            else:
                print(f"音频合并失败: {result.stderr}")
                return False
                
        finally:
            if os.path.exists(list_file):
                os.remove(list_file)
    
    def cleanup_temp_files(self, temp_dir: str):
        """清理临时文件"""
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
            print(f"已清理临时目录: {temp_dir}")


class BookToAudiobook:
    """主控制器"""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config = Config(config_path)
        self.analyzer: Optional[DeepSeekAnalyzer] = None
        self.tts_engine: Optional[TTSEngine] = None
        self.audio_merger: Optional[AudioMerger] = None
    
    async def convert(self, input_text: str, output_file: str = None) -> bool:
        """转换文本为有声书"""
        print("开始转换文本为有声书...")
        
        # 初始化组件
        self.analyzer = DeepSeekAnalyzer(self.config)
        self.tts_engine = TTSEngine(self.config)
        self.audio_merger = AudioMerger(self.config)
        
        # 获取输出路径
        if not output_file:
            output_dir = self.config.get('audio.output_dir', 'output')
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, 'audiobook.mp3')
        
        temp_dir = self.config.get('audio.temp_dir', 'temp_audio')
        
        try:
            # 步骤1: 分析文本
            print("步骤1: 分析文本内容...")
            async with self.analyzer as analyzer:
                segments = await analyzer.analyze_text(input_text)
            
            print(f"分析完成，共识别出 {len(segments)} 个片段")
            
            # 保存分析结果（可选）
            analysis_file = output_file.replace('.mp3', '_analysis.json')
            with open(analysis_file, 'w', encoding='utf-8') as f:
                json.dump(segments, f, ensure_ascii=False, indent=2)
            print(f"分析结果已保存到: {analysis_file}")
            
            # 步骤2: 语音合成
            print("步骤2: 开始语音合成...")
            await self.tts_engine.initialize()
            audio_files = await self.tts_engine.synthesize_all(segments, temp_dir)
            
            if not audio_files:
                print("语音合成失败，没有生成音频文件")
                return False
            
            print(f"语音合成完成，共生成 {len(audio_files)} 个音频文件")
            
            # 步骤3: 合并音频
            print("步骤3: 合并音频文件...")
            success = self.audio_merger.merge_audio_files(audio_files, output_file)
            
            if success:
                print(f"有声书生成成功: {output_file}")
                
                # 清理临时文件
                self.audio_merger.cleanup_temp_files(temp_dir)
                
                # 显示统计信息
                total_duration = self._estimate_duration(len(audio_files))
                print(f"估计总时长: {total_duration}")
                
                return True
            else:
                print("音频合并失败")
                return False
                
        except Exception as e:
            print(f"转换过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _estimate_duration(self, num_segments: int) -> str:
        """估计总时长（简单估算）"""
        # 假设每个片段平均5秒
        total_seconds = num_segments * 5
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}小时{minutes}分钟{seconds}秒"
        elif minutes > 0:
            return f"{minutes}分钟{seconds}秒"
        else:
            return f"{seconds}秒"
    
    def convert_file(self, input_file: str, output_file: str = None) -> bool:
        """转换文件中的文本为有声书"""
        try:
            # 支持多种文本格式
            if input_file.endswith('.txt'):
                with open(input_file, 'r', encoding='utf-8') as f:
                    text = f.read()
            elif input_file.endswith('.json'):
                with open(input_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    text = data.get('text', '') if isinstance(data, dict) else str(data)
            else:
                # 尝试按文本文件读取
                try:
                    with open(input_file, 'r', encoding='utf-8') as f:
                        text = f.read()
                except:
                    print(f"不支持的文件格式: {input_file}")
                    return False
            
            # 运行异步转换
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self.convert(text, output_file))
            finally:
                loop.close()
            
        except Exception as e:
            print(f"文件读取失败: {e}")
            return False


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='小说/文章转有声书工具')
    parser.add_argument('input', help='输入文本或文件路径')
    parser.add_argument('-o', '--output', help='输出音频文件路径')
    parser.add_argument('-c', '--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('-f', '--file', action='store_true', help='输入是文件路径')
    
    args = parser.parse_args()
    
    # 创建转换器实例
    converter = BookToAudiobook(args.config)
    
    if args.file:
        # 输入是文件
        success = converter.convert_file(args.input, args.output)
    else:
        # 输入是文本，直接运行异步转换
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(converter.convert(args.input, args.output))
        finally:
            loop.close()
    
    if success:
        print("转换成功！")
        sys.exit(0)
    else:
        print("转换失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()
