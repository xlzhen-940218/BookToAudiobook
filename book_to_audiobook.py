#!/usr/bin/env python3
"""
小说/文章转有声书工具
使用DeepSeek API分析文本，阿里百炼(DashScope)进行语音合成，ffmpeg合并音频
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
import subprocess

# 阿里百炼 SDK
import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer


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

            if api_keys_config:
                if 'deepseek' in api_keys_config:
                    if 'deepseek' not in config:
                        config['deepseek'] = {}
                    for key, value in api_keys_config['deepseek'].items():
                        config['deepseek'][key] = value

                if 'dashscope' in api_keys_config:
                    if 'dashscope' not in config:
                        config['dashscope'] = {}
                    for key, value in api_keys_config['dashscope'].items():
                        config['dashscope'][key] = value

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
        ds_api_key_env = os.environ.get('DEEPSEEK_API_KEY')
        dashscope_api_key_env = os.environ.get('DASHSCOPE_API_KEY')

        keys = {}
        if ds_api_key_env:
            keys['deepseek'] = {'api_key': ds_api_key_env}
        if dashscope_api_key_env:
            keys['dashscope'] = {'api_key': dashscope_api_key_env}

        if keys:
            print("从环境变量读取了部分 API 密钥")
            return keys

        print("警告: 未找到API密钥配置文件或环境变量。")
        return None

    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        api_keys_config = self._load_api_keys() or {}

        ds_api_key = api_keys_config.get('deepseek', {}).get('api_key', 'your-deepseek-api-key')
        dashscope_api_key = api_keys_config.get('dashscope', {}).get('api_key', 'your-dashscope-api-key')

        return {
            'deepseek': {
                'api_key': ds_api_key,
                'base_url': 'https://api.deepseek.com',
                'model': 'deepseek-chat'
            },
            'dashscope': {
                'api_key': dashscope_api_key,
                'model': 'cosyvoice-v3-flash'  # 默认使用阿里最新音色模型
            },
            'tts': {
                'narrator_voice': 'longanyang',  # 阳光大男孩，适合旁白
                'character_voices': {
                    'default': 'longanhuan',
                    'character_genders': {},
                    'random_assignment': True,
                    'available_chinese_voices': [
                        'longanyang',
                        'longanhuan',
                        'longxiaochun_v3',
                        'longshu_v3',
                        'longyichen_v3',
                        'longwanjun_v3',
                        'longxiaoxia_v3'
                    ],
                    'male_voices': [
                        'longshu_v3',  # 沉稳青年男
                        'longyichen_v3',  # 洒脱活力男
                        'longjielidou_v3'  # 阳光顽皮男
                    ],
                    'female_voices': [
                        'longanhuan',  # 欢脱元气女
                        'longxiaochun_v3',  # 知性积极女
                        'longwanjun_v3',  # 细腻柔声女
                        'longxiaoxia_v3'  # 沉稳权威女
                    ]
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
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        prompt = self._build_prompt(text)
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
                    return self._simple_analysis(text)
        except Exception as e:
            print(f"DeepSeek API调用异常: {e}")
            return self._simple_analysis(text)

    def _build_prompt(self, text: str) -> str:
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
        try:
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
        segments = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            dialogue_pattern = r'["「」『』](.+?)["「」『』]'
            matches = list(re.finditer(dialogue_pattern, line))

            if matches:
                last_end = 0
                for match in matches:
                    if match.start() > last_end:
                        narrator_text = line[last_end:match.start()].strip()
                        if narrator_text:
                            segments.append({
                                "type": "narrator",
                                "text": narrator_text,
                                "voice": "narrator"
                            })

                    dialogue_text = match.group(1).strip()
                    if dialogue_text:
                        segments.append({
                            "type": "character",
                            "character": "unknown",
                            "text": dialogue_text,
                            "voice": "character_unknown"
                        })

                    last_end = match.end()

                if last_end < len(line):
                    narrator_text = line[last_end:].strip()
                    if narrator_text:
                        segments.append({
                            "type": "narrator",
                            "text": narrator_text,
                            "voice": "narrator"
                        })
            else:
                segments.append({
                    "type": "narrator",
                    "text": line,
                    "voice": "narrator"
                })

        return segments


class TTSEngine:
    """阿里百炼语音合成引擎"""

    def __init__(self, config: Config):
        self.config = config
        self.character_voice_assignments: Dict[str, str] = {}
        self.character_gender_cache: Dict[str, str] = {}

        # 配置 DashScope API Key
        api_key = self.config.get('dashscope.api_key')
        if api_key:
            dashscope.api_key = api_key
        else:
            dashscope.api_key = os.environ.get('DASHSCOPE_API_KEY')

        if not dashscope.api_key or dashscope.api_key == 'your-dashscope-api-key':
            print("警告: 阿里百炼(DashScope) API Key 未配置！合成可能会失败。")

    async def initialize(self):
        """初始化操作 (由于百炼通过类直接调用，这里可保留为空或做连接测试)"""
        pass

    def get_character_gender(self, character_name: str, segment: Dict[str, Any] = None) -> str:
        """获取角色性别"""
        if segment and 'gender' in segment:
            gender = segment['gender']
            if gender in ['male', 'female']:
                self.character_gender_cache[character_name] = gender
                return gender

        if character_name in self.character_gender_cache:
            return self.character_gender_cache[character_name]

        character_genders = self.config.get('tts.character_voices.character_genders', {})
        if character_name in character_genders:
            gender = character_genders[character_name]
            self.character_gender_cache[character_name] = gender
            return gender

        female_patterns = ['芳', '玲', '娜', '婷', '娟', '丽', '敏', '静', '燕', '红', '秀', '英', '梅', '花', '兰',
                           '玉', '珍', '芬', '萍']
        male_patterns = ['强', '伟', '刚', '勇', '军', '杰', '涛', '明', '建', '平', '波', '峰', '龙', '虎', '雄', '斌',
                         '浩', '宇', '飞']

        for pattern in female_patterns:
            if pattern in character_name:
                self.character_gender_cache[character_name] = 'female'
                return 'female'

        for pattern in male_patterns:
            if pattern in character_name:
                self.character_gender_cache[character_name] = 'male'
                return 'male'

        default_gender = 'male'
        self.character_gender_cache[character_name] = default_gender
        return default_gender

    def get_voice_for_segment(self, segment: Dict[str, Any]) -> str:
        """根据片段类型获取音色"""
        voice_config = self.config.get('tts', {})

        if segment['type'] == 'narrator':
            return voice_config.get('narrator_voice', 'longanyang')
        else:
            character = segment.get('character', 'default')
            character_voices_config = voice_config.get('character_voices', {})

            if character in character_voices_config and character_voices_config[character] != 'default':
                return character_voices_config[character]

            if character in self.character_voice_assignments:
                return self.character_voice_assignments[character]

            character_gender = self.get_character_gender(character, segment)

            male_voices = character_voices_config.get('male_voices', [])
            female_voices = character_voices_config.get('female_voices', [])

            if character_gender == 'male' and male_voices:
                import random
                selected_voice = random.choice(male_voices)
                self.character_voice_assignments[character] = selected_voice
                print(f"为男角色 '{character}' 分配音色: {selected_voice}")
                return selected_voice
            elif character_gender == 'female' and female_voices:
                import random
                selected_voice = random.choice(female_voices)
                self.character_voice_assignments[character] = selected_voice
                print(f"为女角色 '{character}' 分配音色: {selected_voice}")
                return selected_voice

            random_assignment = character_voices_config.get('random_assignment', True)
            available_voices = character_voices_config.get('available_chinese_voices', [])

            if random_assignment and available_voices:
                import random
                narrator_voice = voice_config.get('narrator_voice', 'longanyang')
                candidate_voices = [v for v in available_voices if v != narrator_voice]

                assigned_voices = set(self.character_voice_assignments.values())
                available_candidate_voices = [v for v in candidate_voices if v not in assigned_voices]

                if not available_candidate_voices:
                    available_candidate_voices = candidate_voices

                if available_candidate_voices:
                    selected_voice = random.choice(available_candidate_voices)
                    self.character_voice_assignments[character] = selected_voice
                    print(f"为角色 '{character}' 分配音色: {selected_voice}")
                    return selected_voice

            default_voice = character_voices_config.get('default', 'longanhuan')
            self.character_voice_assignments[character] = default_voice
            return default_voice

    async def synthesize_segment(self, segment: Dict[str, Any], output_path: str) -> bool:
        """合成单个文本片段为音频"""
        try:
            voice = self.get_voice_for_segment(segment)
            text = segment['text']
            model = self.config.get('dashscope.model', 'cosyvoice-v3-flash')

            # 使用 DashScope 的同步调用，但在异步线程池中运行以防阻塞主循环
            loop = asyncio.get_event_loop()

            def _call_dashscope():
                # 实例化合成器
                synthesizer = SpeechSynthesizer(model=model, voice=voice)
                # 调用获取二进制音频流
                audio_data = synthesizer.call(text)

                if audio_data is None:
                    raise Exception("百炼返回的音频数据为空")

                # 写入文件
                with open(output_path, 'wb') as f:
                    f.write(audio_data)

            await loop.run_in_executor(None, _call_dashscope)
            return True

        except Exception as e:
            print(f"语音合成失败 (片段: '{segment['text'][:15]}...'): {e}")
            return False

    async def synthesize_all(self, segments: List[Dict[str, Any]], output_dir: str) -> List[str]:
        """合成所有文本片段"""
        await self.initialize()

        audio_files = []
        os.makedirs(output_dir, exist_ok=True)

        for i, segment in enumerate(segments):
            output_file = os.path.join(output_dir, f"segment_{i:04d}.mp3")
            print(f"正在合成第 {i + 1}/{len(segments)} 段: {segment['text'][:50]}...")

            success = await self.synthesize_segment(segment, output_file)
            if success:
                audio_files.append(output_file)
            else:
                print(f"第 {i + 1} 段合成失败，跳过")

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

        list_file = tempfile.mktemp(suffix='.txt')
        try:
            with open(list_file, 'w', encoding='utf-8') as f:
                for audio_file in audio_files:
                    f.write(f"file '{os.path.abspath(audio_file)}'\n")

            try:
                subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("ffmpeg未安装或不可用，请先安装ffmpeg")
                return False

            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c', 'copy',
                output_file,
                '-y'
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

        self.analyzer = DeepSeekAnalyzer(self.config)
        self.tts_engine = TTSEngine(self.config)
        self.audio_merger = AudioMerger(self.config)

        if not output_file:
            output_dir = self.config.get('audio.output_dir', 'output')
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, 'audiobook.mp3')

        temp_dir = self.config.get('audio.temp_dir', 'temp_audio')

        try:
            print("步骤1: 分析文本内容...")
            async with self.analyzer as analyzer:
                segments = await analyzer.analyze_text(input_text)

            print(f"分析完成，共识别出 {len(segments)} 个片段")

            analysis_file = output_file.replace('.mp3', '_analysis.json')
            with open(analysis_file, 'w', encoding='utf-8') as f:
                json.dump(segments, f, ensure_ascii=False, indent=2)
            print(f"分析结果已保存到: {analysis_file}")

            print("步骤2: 开始语音合成 (阿里百炼 CosyVoice)...")
            audio_files = await self.tts_engine.synthesize_all(segments, temp_dir)

            if not audio_files:
                print("语音合成失败，没有生成音频文件")
                return False

            print(f"语音合成完成，共生成 {len(audio_files)} 个音频文件")

            print("步骤3: 合并音频文件...")
            success = self.audio_merger.merge_audio_files(audio_files, output_file)

            if success:
                print(f"有声书生成成功: {output_file}")
                self.audio_merger.cleanup_temp_files(temp_dir)
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
        try:
            if input_file.endswith('.txt'):
                with open(input_file, 'r', encoding='utf-8') as f:
                    text = f.read()
            elif input_file.endswith('.json'):
                with open(input_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    text = data.get('text', '') if isinstance(data, dict) else str(data)
            else:
                try:
                    with open(input_file, 'r', encoding='utf-8') as f:
                        text = f.read()
                except:
                    print(f"不支持的文件格式: {input_file}")
                    return False

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
    import os  # 确保引入了os

    parser = argparse.ArgumentParser(description='小说/文章转有声书工具 (基于阿里百炼 CosyVoice)')
    parser.add_argument('input', help='输入文本或文件路径')
    parser.add_argument('-o', '--output', help='输出音频文件路径')
    parser.add_argument('-c', '--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('-f', '--file', action='store_true', help='强制指定输入为文件路径')

    args = parser.parse_args()

    # 创建转换器实例
    converter = BookToAudiobook(args.config)

    # 【修改核心逻辑】：如果用户加了 -f，或者输入的内容恰好是一个真实存在的文件路径，就走文件模式
    is_file_mode = args.file or os.path.isfile(args.input)

    if is_file_mode:
        if not os.path.exists(args.input):
            print(f"错误: 指定的文件不存在 -> {args.input}")
            sys.exit(1)

        print(f"正在读取文件: {args.input}")
        # 输入是文件
        success = converter.convert_file(args.input, args.output)
    else:
        print("正在处理直接输入的文本内容...")
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