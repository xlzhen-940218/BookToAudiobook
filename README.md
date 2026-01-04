# 小说/文章转有声书工具

一个使用Python将小说或文章转换为有声书的工具，利用DeepSeek API分析文本内容，edge-tts进行语音合成，ffmpeg合并音频文件。

## 功能特性

1. **智能文本分析**：使用DeepSeek API自动识别文本中的旁白和角色对话
2. **多音色语音合成**：为旁白和不同角色分配不同的音色
3. **音频文件合并**：使用ffmpeg将所有音频片段合并为完整的有声书
4. **配置文件管理**：支持YAML配置文件，方便调整参数
5. **多种输入格式**：支持文本直接输入或文件输入（txt、json等）

## 系统要求

- Python 3.8+
- ffmpeg（用于音频合并）
- 网络连接（用于DeepSeek API调用）

## 安装步骤

1. 克隆项目或下载源代码
2. 安装Python依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 安装ffmpeg（如果尚未安装）：
   - Windows: 从官网下载并添加到PATH
   - macOS: `brew install ffmpeg`
   - Ubuntu/Debian: `sudo apt install ffmpeg`

## 配置说明

### 1. 主配置文件 (config.yaml)

编辑 `config.yaml` 文件来配置应用程序参数：

```yaml
# DeepSeek API配置
# 注意：API密钥已移至单独的配置文件 api_keys.yaml
# 请创建 api_keys.yaml 文件并添加您的API密钥
deepseek:
  # api_key: "your-api-key-here"  # 已移至 api_keys.yaml
  base_url: "https://api.deepseek.com"
  model: "deepseek-chat"

# 语音合成配置
tts:
  # 默认音色（旁白）
  narrator_voice: "zh-CN-XiaoxiaoNeural"
  
  # 角色音色配置
  character_voices:
    # 默认音色（当角色没有特定音色或随机分配时使用）
    default: "zh-CN-YunxiNeural"
    # 可以在这里添加特定角色的音色映射（优先级最高）
    # 例如: "张三": "zh-CN-YunyangNeural"
    
    # 角色性别配置（用于音色选择和pitch调整）
    # 可以在这里添加特定角色的性别配置
    # 例如: "张三": "male", "李四": "female"
    character_genders: {}
    
    # 随机音色分配选项
    random_assignment: true  # 是否启用随机音色分配
    # 可用的中文音色列表（用于随机分配）- 使用可靠可用的音色
    available_chinese_voices:
      - "zh-CN-XiaoxiaoNeural"  # 女声，可靠（旁白默认）
      - "zh-CN-YunxiNeural"     # 男声，可靠（角色默认）
      - "zh-CN-YunyangNeural"   # 男声，可靠
      - "zh-CN-XiaoyiNeural"    # 女声，可靠
    
    # 音色性别分类（用于自动分配）
    male_voices:
      - "zh-CN-YunxiNeural"
      - "zh-CN-YunyangNeural"
    female_voices:
      - "zh-CN-XiaoxiaoNeural"
      - "zh-CN-XiaoyiNeural"
  
  # 语音参数
  rate: "+0%"
  volume: "+0%"
  pitch: "+0Hz"
  
  # 性别相关的pitch调整（当音色与性别不匹配时使用）
  gender_pitch_adjustment:
    enabled: true  # 是否启用性别pitch调整
    male_pitch: "-10Hz"  # 男角色pitch调整（更低沉）
    female_pitch: "+10Hz"  # 女角色pitch调整（更高亢）
    default_pitch: "+0Hz"  # 默认pitch调整

# 音频处理配置
audio:
  output_format: "mp3"
  sample_rate: 24000
  bitrate: "48k"
  # 临时文件目录
  temp_dir: "temp_audio"
  # 最终输出目录
  output_dir: "output"

# 文本处理配置
text:
  # 最大文本长度（字符数）
  max_chunk_length: 1000
  # 是否保留标点符号
  preserve_punctuation: true
```

### 2. API密钥配置文件 (api_keys.yaml)

**重要：为了保护您的API密钥，请将敏感信息放在单独的配置文件中**

创建 `api_keys.yaml` 文件（不要提交到Git仓库）：

```yaml
# API密钥配置文件
# 请将您的API密钥放在这里，不要将此文件提交到Git仓库
# 建议将此文件添加到.gitignore中

deepseek:
  api_key: "sk-your-deepseek-api-key-here"  # 替换为您的DeepSeek API密钥

# 可以在这里添加其他API密钥
# 例如:
# openai:
#   api_key: "your-openai-api-key"
```

### 3. 环境变量方式（可选）

您也可以使用环境变量设置API密钥：

```bash
# Windows (CMD/PowerShell)
set DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here

# Windows (PowerShell)
$env:DEEPSEEK_API_KEY="sk-your-deepseek-api-key-here"

# Linux/macOS
export DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here
```

### 4. 配置文件优先级

系统按以下顺序查找API密钥：
1. `api_keys.yaml` 或 `api_keys.yml` 文件（当前目录或config/子目录）
2. 环境变量 `DEEPSEEK_API_KEY`
3. 如果以上都未找到，会显示警告信息

### 5. Git安全建议

为了保护您的API密钥，建议将以下内容添加到 `.gitignore` 文件：

```
# API密钥文件
api_keys.yaml
api_keys.yml
.api_keys.yaml
.api_keys.yml

# 环境配置文件
.env
.env.local
```

这样，您的API密钥就不会意外提交到版本控制系统。

## 使用方法

### 基本用法

1. **直接输入文本**：
   ```bash
   python book_to_audiobook.py "你的文本内容" -o output.mp3
   ```

2. **从文件输入**：
   ```bash
   python book_to_audiobook.py input.txt -f -o output.mp3
   ```

### 命令行参数

- `input`: 输入文本或文件路径（必需）
- `-o, --output`: 输出音频文件路径（可选，默认为output/audiobook.mp3）
- `-c, --config`: 配置文件路径（可选，默认为config.yaml）
- `-f, --file`: 指定输入是文件路径（如果输入是文本则不需要）

### 示例

1. 转换测试文件：
   ```bash
   python book_to_audiobook.py test_input.txt -f -o my_audiobook.mp3
   ```

2. 使用自定义配置：
   ```bash
   python book_to_audiobook.py "小说内容" -c my_config.yaml -o result.mp3
   ```

## 工作流程

1. **文本分析**：使用DeepSeek API分析文本，识别旁白和角色对话
2. **语音合成**：为每个文本片段使用edge-tts合成语音
   - 旁白使用固定音色（默认：zh-CN-XiaoxiaoNeural）
   - 角色音色分配：
     - 如果配置了特定角色的音色，则使用该音色
     - 如果启用随机分配（默认启用），则为每个角色随机分配不同的音色
     - 同一角色在整个文本中保持音色一致
     - 尽可能避免不同角色使用相同音色
3. **音频合并**：使用ffmpeg将所有音频片段合并为完整的有声书
4. **清理**：删除临时音频文件

## 性别感知的音色分配功能

系统能够根据角色性别自动分配适当的音色，避免男角色使用女声音色或女角色使用男声音色的问题。

### 功能特点

1. **性别识别**：
   - 通过配置文件指定角色性别
   - 根据角色名字自动推断性别（中文名字特征识别）
   - 支持手动配置角色性别

2. **性别对应的音色分配**：
   - 男角色自动分配男声音色（如 `zh-CN-YunxiNeural`, `zh-CN-YunyangNeural`）
   - 女角色自动分配女声音色（如 `zh-CN-XiaoxiaoNeural`, `zh-CN-XiaoyiNeural`）
   - 同一角色在整个文本中保持音色一致

3. **智能pitch调整**：
   - 当音色与角色性别不匹配时，自动调整pitch参数
   - 男角色使用女声音色时：降低pitch（更低沉）
   - 女角色使用男声音色时：提高pitch（更高亢）
   - 可配置调整幅度

### 配置示例

```yaml
# 角色音色配置
character_voices:
  # 角色性别配置
  character_genders:
    "张三": "male"    # 手动指定张三为男性
    "李芳": "female"  # 手动指定李芳为女性
  
  # 音色性别分类
  male_voices:
    - "zh-CN-YunxiNeural"
    - "zh-CN-YunyangNeural"
  female_voices:
    - "zh-CN-XiaoxiaoNeural"
    - "zh-CN-XiaoyiNeural"

# 性别pitch调整配置
gender_pitch_adjustment:
  enabled: true  # 启用pitch调整
  male_pitch: "-10Hz"   # 男角色pitch调整
  female_pitch: "+10Hz" # 女角色pitch调整
```

### 名字性别推断规则

系统根据中文名字常见特征自动推断性别：

- **女性名字特征**：芳、玲、娜、婷、娟、丽、敏、静、燕、红、秀、英、梅等
- **男性名字特征**：强、伟、刚、勇、军、杰、涛、明、建、平、波、峰、龙等

### 使用示例

1. **自动性别识别**：系统会根据角色名字自动推断性别并分配相应音色
2. **手动性别配置**：可以在配置文件中手动指定角色性别
3. **pitch调整**：当角色使用相反性别的音色时，自动调整pitch使声音更符合角色特征

## 随机音色分配功能

当有多个角色存在时，系统可以随机为每个角色分配不同的音色，使有声书更加生动。功能特点：

- **避免重复**：尽可能为不同角色分配不同的音色
- **一致性**：同一角色在整个文本中保持相同的音色
- **可配置**：可以通过配置文件启用/禁用随机分配
- **音色列表**：可以自定义可用的音色列表
- **优先级**：特定角色的音色配置优先级最高

配置示例：
```yaml
character_voices:
  random_assignment: true  # 启用随机音色分配
  available_chinese_voices:
    - "zh-CN-XiaoxiaoNeural"  # 女声
    - "zh-CN-YunxiNeural"     # 男声
    - "zh-CN-YunyangNeural"   # 男声
    - "zh-CN-XiaoyiNeural"    # 女声
```

## 支持的音色

edge-tts支持多种语言的音色，常用中文音色包括：
- `zh-CN-XiaoxiaoNeural`（女声，推荐旁白）
- `zh-CN-YunxiNeural`（男声，推荐角色）
- `zh-CN-YunyangNeural`（男声）
- `zh-CN-XiaoyiNeural`（女声）

可以通过以下命令查看所有可用音色：
```python
python -c "import asyncio; from edge_tts import VoicesManager; import asyncio; async def main(): voices = await VoicesManager.create(); print([v['ShortName'] for v in voices.voices if 'zh-' in v['ShortName']]); asyncio.run(main())"
```

## 故障排除

1. **DeepSeek API错误**：
   - 检查API密钥是否正确
   - 确认网络连接正常
   - 如果API调用失败，程序会自动使用简单的规则分析

2. **语音合成失败**：
   - 检查edge-tts是否安装正确
   - 确认音色名称正确
   - 文本可能包含不支持的字符

3. **音频合并失败**：
   - 确认ffmpeg已安装并添加到PATH
   - 检查临时音频文件是否存在

4. **Python版本问题**：
   - 确保使用Python 3.8+
   - 如果遇到模块导入错误，尝试重新安装依赖

## 项目结构

```
book_to_audiobook/
├── book_to_audiobook.py    # 主程序
├── config.yaml             # 配置文件
├── requirements.txt        # Python依赖
├── README.md              # 说明文档
├── test_input.txt         # 测试文本
└── edge-tts/              # edge-tts库（已包含）
```

## 注意事项

1. DeepSeek API有使用限制，请合理使用
2. 长文本处理可能需要较长时间
3. 生成的音频文件质量取决于edge-tts服务
4. 建议在处理长文本时适当分段

## 许可证

本项目基于MIT许可证开源。

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。
