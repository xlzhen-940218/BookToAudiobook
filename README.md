这里是为您更新的最新的 `README.md`。

我已将文档中的核心语音合成引擎从原来的 `edge-tts` 彻底替换为了**阿里百炼 (CosyVoice)**，并同步更新了配置说明、音色池（新增小孩、老人、v1/v2/v3自动适配机制）以及大模型的年龄段推断等最新功能特性。

您可以直接复制以下内容覆盖旧的 `README.md` 文件：

***

# 小说/文章转有声书工具 (DeepSeek + 阿里百炼 CosyVoice)

一个使用 Python 将小说或文章转换为高质量有声书的工具。利用 DeepSeek API 深度分析文本内容（智能提取旁白、角色对话、推断性别与年龄段），并调用阿里百炼 (DashScope) 的 CosyVoice 大模型进行高拟真语音合成，最后通过 ffmpeg 自动合并为完整的有声书音频文件。

<audio id="audio" controls="" preload="none">
      <source id="mp3" src="青蛙王子.mp3">
</audio>

<audio id="audio" controls="" preload="none">
      <source id="mp3" src="龟兔赛跑.mp3">
</audio>

## 功能特性

1. **智能文本分析**：使用 DeepSeek API 自动精准提取文本中的旁白和角色对话，并智能推断角色的**性别**（男/女）和**年龄段**（儿童/成年/老人）。
2. **多音色智能分配**：为旁白和不同角色分配最贴合的音色。优先按“小孩/老人”特殊年龄段分配，其次按性别分配。
3. **CosyVoice 版本自适应**：代码内置智能适配器，随心切换 `cosyvoice-v1`、`v2` 或 `v3-flash` 模型，**无需手动修改复杂的音色后缀**。
4. **音频文件合并**：使用 ffmpeg 将所有零碎的音频片段无缝合并为完整的有声书。
5. **多种输入格式**：支持文本直接输入或文件输入（`.txt`、`.json` 等）。

## 系统要求

- Python 3.8+
- ffmpeg（用于音频无损合并）
- 网络连接（用于 DeepSeek API 和 阿里百炼 API 调用）

## 安装步骤

1. 克隆项目或下载源代码
2. 安装 Python 依赖：
   ```bash
   pip install dashscope aiohttp pyyaml
   ```
3. 安装 ffmpeg（如果尚未安装）：
   - Windows: 从官网下载并添加到系统 PATH 环境变量
   - macOS: `brew install ffmpeg`
   - Ubuntu/Debian: `sudo apt install ffmpeg`

## 配置说明

### 1. API 密钥配置文件 (api_keys.yaml)

**重要：为了保护您的 API 密钥，请将敏感信息放在单独的配置文件中，切勿提交到代码仓库。**

在项目根目录创建 `api_keys.yaml` 文件：

```yaml
# API密钥配置文件
# 建议将此文件添加到 .gitignore 中

deepseek:
  api_key: "sk-your-deepseek-api-key-here"  # 替换为您的 DeepSeek API 密钥

dashscope:
  api_key: "sk-your-dashscope-api-key-here" # 替换为您的 阿里百炼(DashScope) API 密钥
```

### 2. 主配置文件 (config.yaml)

编辑 `config.yaml` 文件来调整大模型和音色池等参数：

```yaml
deepseek:
  base_url: "https://api.deepseek.com"
  model: "deepseek-chat"

dashscope:
  # 可选模型: cosyvoice-v3-flash, cosyvoice-v3-plus, cosyvoice-v2, cosyvoice-v1
  model: "cosyvoice-v3-flash" 

tts:
  # 默认旁白音色（推荐：longanyang 阳光男，longshu 沉稳男，longbaizhi 睿气女）
  narrator_voice: "longanyang"  

  character_voices:
    default: "longanhuan"  # 默认兜底角色音色

    # 【手动强制指定】如果AI推断错误，可以在这里直接写死某个角色的性别和年龄段
    character_genders: {}
    # 示例: "村长": "elderly", "小明": "child"
    character_ages: {} 

    random_assignment: true  # 启用随机音色分配

    # 1. 儿童音色池
    child_voices:
      - "longhuhu"       # 天真烂漫女童
      - "longjielidou"   # 阳光顽皮男童
      - "longpaopao"     # 飞天泡泡音

    # 2. 老年音色池
    elderly_voices:
      - "longlaobo"      # 沧桑大爷
      - "longlaoyi"      # 从容阿姨

    # 3. 成年男性音色池
    male_voices:
      - "longshu"        # 沉稳青年男
      - "longyichen"     # 洒脱活力男
      - "longxiu"        # 博才说书男

    # 4. 成年女性音色池
    female_voices:
      - "longanhuan"     # 欢脱元气女
      - "longxiaochun"   # 知性积极女
      - "longwanjun"     # 细腻柔声女

    # 5. 通用可用音色池 (兜底)
    available_chinese_voices:
      - "longanhuan"
      - "longxiaochun"
      - "longshu"

audio:
  output_format: "mp3"
  sample_rate: 24000
  bitrate: "48k"
  temp_dir: "temp_audio"
  output_dir: "output"

text:
  max_chunk_length: 1000
  preserve_punctuation: true
```

*注：您可以直接在配置文件中编写基础音色名（如 `longshu`），系统会自动根据使用的模型拼接 `_v2` 或 `_v3`。*

### 3. 环境变量方式（可选）

您也可以直接使用系统环境变量来设置 API 密钥，代码会自动读取：

```bash
# Windows (CMD/PowerShell)
set DEEPSEEK_API_KEY=sk-your-deepseek-api-key
set DASHSCOPE_API_KEY=sk-your-dashscope-api-key

# Linux/macOS
export DEEPSEEK_API_KEY="sk-your-deepseek-api-key"
export DASHSCOPE_API_KEY="sk-your-dashscope-api-key"
```

## 使用方法

### 基本用法

1. **直接输入文本进行转换**：
   ```bash
   python book_to_audiobook.py "夜黑风高，李村长点燃了旱烟，对身旁的小豆子说：『别怕，有爷爷在。』" -o output.mp3
   ```

2. **从文件读取进行转换**：
   ```bash
   python book_to_audiobook.py novel.txt -f -o output.mp3
   ```

### 命令行参数

- `input`: 输入的文本内容或文件路径（必需）
- `-o, --output`: 最终输出的音频文件路径（可选，默认为 `output/audiobook.mp3`）
- `-c, --config`: 配置文件路径（可选，默认为 `config.yaml`）
- `-f, --file`: 强制指定 `input` 为文件路径模式

## 核心亮点：AI 角色感知与智能分配

系统不仅仅是简单的文字转语音，它具备深度上下文理解能力：

1. **年龄与性别双重感知**：DeepSeek 会根据名字特征和上下文（如“大爷”、“孩童”、“柔声说”）推断角色的具体年龄段（child/adult/elderly）和性别。
2. **多层级音色降级机制**：
   - 如果识别为“老人”或“小孩”，优先从 `elderly_voices` 或 `child_voices` 池中抽取对应音色。
   - 如果是成年人，则根据性别从 `male_voices` 或 `female_voices` 池中抽取。
   - 如果没有对应的特征池，从 `available_chinese_voices` 中随机兜底。
3. **音色一致性**：同一角色在整本小说中，只要被分配了一次音色，后续所有对话都会**永久绑定**该音色，保证听感不割裂。

## 故障排除

1. **DeepSeek API 错误 / 分析结果为空**：
   - 检查 `api_keys.yaml` 中的 DeepSeek API 密钥是否填写且余额充足。
   - 确认网络能够正常访问 `api.deepseek.com`。若调用失败，程序会触发正则回退策略，自动做基础的引号对白切分。

2. **阿里百炼 CosyVoice 合成失败**：
   - 检查 DashScope API 密钥。
   - 检查终端输出的警告：若在 `v1` 或 `v2` 模型下使用了专属 `v3` 才有的音色（如标杆音色 `longanyang`），系统会在终端打出警告并自动回退到安全的默认音色。
   - 文本段落过长：百炼 API 有单次合成字符限制，请确保 `config.yaml` 中的 `max_chunk_length` 保持在 1000 左右。

3. **音频合并失败 (ffmpeg 报错)**：
   - 确认终端输入 `ffmpeg -version` 能正常输出信息。如果提示找不到命令，请检查环境变量配置。

## 项目结构

```
book_to_audiobook/
├── book_to_audiobook.py    # 主程序逻辑
├── config.yaml             # 主配置文件
├── api_keys.yaml           # API密钥文件 (需自行创建, 勿提交)
├── README.md               # 说明文档
└── temp_audio/             # 运行时的临时音频切片目录 (自动清理)
```

## 许可证

本项目基于 MIT 许可证开源。欢迎提交 Issue 和 Pull Request 来改进这个工具！