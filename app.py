"""
Astrose — Write your romance in the stars.

AI-powered love letter & portrait cards: poem + image workflows (Coze), Streamlit, Pillow.
Rate limiting: browser fingerprint, IP, and global daily cap.
"""

import streamlit as st
import requests
import json
import os
import sys
import hashlib
import time
from datetime import datetime, date
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# 应用根目录（与 app.py 同目录），用于可靠定位 assets
APP_DIR = Path(__file__).resolve().parent

# ============================================================
# 页面基础配置
# ============================================================
st.set_page_config(
    page_title="Astrose — Write your romance in the stars.",
    page_icon="✨",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ============================================================
# 自定义CSS样式 - 温馨浪漫配色
# ============================================================
st.markdown("""
<style>
    /* 整体背景渐变 */
    .stApp {
        background: linear-gradient(180deg, #FFF0F5 0%, #FFFFFF 30%, #FFF5F5 100%);
    }

    /* 标题样式 */
    h1 {
        text-align: center;
        color: #E91E63;
    }

    /* 副标题 */
    .subtitle {
        text-align: center;
        color: #F48FB1;
        font-size: 1.2rem;
        margin-bottom: 1rem;
    }

    /* 提示文字 */
    .hint-text {
        text-align: center;
        color: #999;
        font-size: 0.9rem;
        margin-bottom: 1.5rem;
    }

    /* 剩余次数 */
    .usage-counter {
        text-align: center;
        color: #E91E63;
        font-size: 0.85rem;
        padding: 0.5rem;
        background: #FFF0F5;
        border-radius: 10px;
        margin: 0.5rem 0;
    }

    /* 主按钮增强 */
    .stButton > button[kind="primary"] {
        width: 100%;
        padding: 0.75rem 2rem;
        font-size: 1.1rem;
        border-radius: 25px;
        background: linear-gradient(135deg, #E91E63, #FF5252);
        border: none;
        color: white;
    }

    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #C2185B, #E53935);
    }

    /* 普通按钮 */
    .stButton > button[kind="secondary"] {
        width: 100%;
        border-radius: 25px;
    }

    /* 分隔装饰 */
    .divider-heart {
        text-align: center;
        color: #F48FB1;
        font-size: 1.5rem;
        margin: 1rem 0;
    }

    /* 引流区域 */
    .promo-section {
        background: #FFF5F5;
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
        text-align: center;
    }

    /* 底部签名 */
    .footer-text {
        text-align: center;
        color: #BDBDBD;
        font-size: 0.8rem;
        margin-top: 2rem;
    }

    /* 超限提示框 */
    .limit-box {
        background: #FFF5F5;
        border: 1px solid #FFCDD2;
        border-radius: 15px;
        padding: 2rem;
        text-align: center;
        margin: 1rem 0;
    }

    /* 隐藏Streamlit默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ============================================================
# 配置常量
# ============================================================
MAX_PER_USER = st.secrets.get("MAX_PER_SESSION", 3)     # 每用户（指纹）每日上限
MAX_PER_IP = st.secrets.get("MAX_PER_IP", 10)           # 每IP每日上限（比指纹宽松，防误伤）
TOTAL_LIMIT = st.secrets.get("TOTAL_LIMIT", 200)        # 全局每日总量
RATE_LIMIT_FILE = "rate_limits.json"                     # 持久化限流数据
LAST_RESULTS_FILE = "last_results.json"                  # 按指纹持久化当日上次生成结果（同用户再进保留结果页）
ASSETS_DIR = "assets"

# 贺卡画布参数
CARD_WIDTH = 800
CARD_HEIGHT = 1280   # 底部留出公众号二维码 + 提示文案
IMAGE_AREA_HEIGHT = 600
TEXT_AREA_TOP = 600
TEXT_AREA_BOTTOM = 1150
SIGNATURE_TOP = 1070   # 署名区：to TA / 落款 用户
FOOTER_AREA_TOP = 1150
FOOTER_QR_SIZE = 88
CARD_FOOTER_LINE1 = "【Astrose-把你们的故事写在星辰里】"
CARD_FOOTER_QR = "wechat_public_qr.png"   # 公众号二维码，放 assets 目录
CARD_FOOTER_PROMPT = "【回复：情人节，给你的TA写信/回信】"


# ============================================================
# 初始化 Session State
# ============================================================
if "page" not in st.session_state:
    st.session_state.page = "input"  # input / result

if "card_image" not in st.session_state:
    st.session_state.card_image = None

if "generated_poem" not in st.session_state:
    st.session_state.generated_poem = None

if "generated_image_url" not in st.session_state:
    st.session_state.generated_image_url = None

if "browser_fp" not in st.session_state:
    st.session_state.browser_fp = None

if "image_request_failed" not in st.session_state:
    st.session_state.image_request_failed = False

if "generation_inputs" not in st.session_state:
    st.session_state.generation_inputs = None  # 用于结果页请求画像工作流


# ============================================================
# 浏览器指纹：通过 JS 注入获取 localStorage UUID
# ============================================================
# 原理：在浏览器 localStorage 中种一个随机UUID作为设备指纹。
# 每次页面加载时读取并通过 URL query param 传给 Streamlit 后端。
# 这样即使刷新页面，只要不清 localStorage，指纹不变。

FINGERPRINT_JS = """
<script>
(function() {
    const STORAGE_KEY = 'love_portrait_fp';
    let fp = localStorage.getItem(STORAGE_KEY);
    if (!fp) {
        fp = 'fp_' + crypto.randomUUID();
        localStorage.setItem(STORAGE_KEY, fp);
    }
    // 通过 URL query param 把指纹传给 Streamlit 后端
    const currentUrl = new URL(window.location.href);
    const existingFp = currentUrl.searchParams.get('_fp');
    if (existingFp !== fp) {
        currentUrl.searchParams.set('_fp', fp);
        window.history.replaceState({}, '', currentUrl.toString());
        // 触发 Streamlit 重新读取 query params
        window.parent.postMessage({type: 'streamlit:setQueryParam', '_fp': fp}, '*');
    }
})();
</script>
"""


def get_browser_fingerprint() -> str | None:
    """
    获取浏览器指纹（localStorage UUID）

    返回指纹字符串，如果尚未获取到则返回 None
    """
    # 注入JS脚本（每次渲染都注入，确保指纹已种入localStorage）
    st.components.v1.html(FINGERPRINT_JS, height=0, width=0)

    # 从 URL query params 读取指纹
    params = st.query_params
    fp = params.get("_fp", None)

    if fp:
        st.session_state.browser_fp = fp

    return st.session_state.browser_fp


def get_client_ip() -> str:
    """
    获取客户端真实IP

    Streamlit Cloud 通过 st.context.headers 暴露请求头，
    其中 X-Forwarded-For 包含真实客户端IP。
    本地开发时 fallback 到 127.0.0.1。
    """
    try:
        headers = st.context.headers
        # X-Forwarded-For 格式: "client_ip, proxy1, proxy2"
        forwarded_for = headers.get("X-Forwarded-For", "")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        real_ip = headers.get("X-Real-Ip", "")
        if real_ip:
            return real_ip.strip()
    except Exception:
        pass

    return "127.0.0.1"


# ============================================================
# 持久化限流存储（JSON文件，每日自动重置）
# ============================================================
# 数据结构：
# {
#     "date": "2026-02-14",
#     "total_count": 42,
#     "fingerprints": { "fp_abc123": 3, "fp_def456": 1 },
#     "ips": { "1.2.3.4": 5, "5.6.7.8": 2 }
# }

def _load_rate_data() -> dict:
    """加载限流数据，如果日期不是今天则自动重置"""
    today = date.today().isoformat()
    default_data = {
        "date": today,
        "total_count": 0,
        "fingerprints": {},
        "ips": {},
    }

    try:
        if not os.path.exists(RATE_LIMIT_FILE):
            return default_data

        with open(RATE_LIMIT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # 跨日自动重置
        if data.get("date") != today:
            return default_data

        return data

    except (json.JSONDecodeError, IOError, KeyError):
        return default_data


def _save_rate_data(data: dict):
    """保存限流数据到文件"""
    try:
        with open(RATE_LIMIT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except IOError:
        pass


def check_rate_limit(fingerprint: str | None, ip: str) -> tuple[bool, str, int]:
    """
    三层限流检查

    返回：(allowed, reason, remaining)
        - allowed:   是否允许生成
        - reason:    拒绝原因（"total" / "fingerprint" / "ip" / ""）
        - remaining: 该用户剩余次数
    """
    data = _load_rate_data()

    # --- 第1层：全局总量 ---
    if data["total_count"] >= TOTAL_LIMIT:
        return False, "total", 0

    # --- 第2层：浏览器指纹（主力） ---
    if fingerprint:
        fp_count = data["fingerprints"].get(fingerprint, 0)
        if fp_count >= MAX_PER_USER:
            return False, "fingerprint", 0
        remaining = MAX_PER_USER - fp_count
        return True, "", remaining

    # --- 第3层：IP兜底（没有指纹时才依赖IP） ---
    ip_count = data["ips"].get(ip, 0)
    if ip_count >= MAX_PER_IP:
        return False, "ip", 0

    remaining = min(MAX_PER_USER, MAX_PER_IP - ip_count)
    return True, "", remaining


def record_usage(fingerprint: str | None, ip: str):
    """记录一次使用，同时更新指纹、IP、全局三个维度"""
    data = _load_rate_data()

    data["total_count"] = data.get("total_count", 0) + 1

    if fingerprint:
        data["fingerprints"][fingerprint] = data["fingerprints"].get(fingerprint, 0) + 1

    # IP 始终记录（作为兜底维度）
    data["ips"][ip] = data["ips"].get(ip, 0) + 1

    _save_rate_data(data)


def get_remaining_count(fingerprint: str | None, ip: str) -> int:
    """获取当前用户剩余次数"""
    data = _load_rate_data()

    if fingerprint:
        used = data["fingerprints"].get(fingerprint, 0)
        return max(0, MAX_PER_USER - used)

    ip_used = data["ips"].get(ip, 0)
    return max(0, min(MAX_PER_USER, MAX_PER_IP - ip_used))


# ============================================================
# 持久化「上次结果」：按指纹存储当日结果，同用户再进可恢复结果页
# ============================================================
def _load_last_results() -> dict:
    """加载上次结果数据，若不存在或日期不是今天则返回空结构"""
    today = date.today().isoformat()
    default_data = {"date": today, "results": {}}
    try:
        if not os.path.exists(LAST_RESULTS_FILE):
            return default_data
        with open(LAST_RESULTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != today:
            return default_data
        return data
    except (json.JSONDecodeError, IOError, KeyError):
        return default_data


def _save_last_result(
    fingerprint: str,
    image_url: str,
    poem: str,
    partner_name: str = "",
    my_name: str = "",
):
    """保存该指纹当日最近一次生成结果（含署名用 TA 名与用户名）"""
    if not fingerprint:
        return
    data = _load_last_results()
    data["results"][fingerprint] = {
        "image_url": image_url,
        "poem": poem,
        "partner_name": partner_name,
        "my_name": my_name,
    }
    try:
        with open(LAST_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except IOError:
        pass


# ============================================================
# 扣子API调用（双工作流：小诗 / 画像）
# ============================================================
WORKFLOW_ID_POEM = "7606224160260554804"   # 小诗生成工作流
WORKFLOW_ID_IMAGE = "7606174573470351400"  # 画像生成工作流


def _coze_parameters(
    user_input: str,
    partner_name: str,
    my_name: str,
    partner_gender: str,
    ta_in_my_eyes: str = "",
    message_to_ta: str = "",
) -> dict:
    """
    扣子 workflow 入参，与「开始」节点变量名一致：
    input: 你和他的故事, image: 你眼中的他, telling: 你对他说的一句话, gender: 他的性别
    """
    return {
        "input": user_input,
        "image": ta_in_my_eyes,
        "telling": message_to_ta,
        "gender": partner_gender,
    }


def call_coze_workflow_poem(
    user_input: str,
    partner_name: str,
    my_name: str,
    partner_gender: str,
    ta_in_my_eyes: str = "",
    message_to_ta: str = "",
) -> str:
    """
    调用小诗工作流，仅返回诗歌文本。
    ⚠️ 返回结构需与扣子小诗 workflow 实际输出一致（如 data.poem）。
    """
    api_url = "https://api.coze.cn/v1/workflow/run"
    api_key = st.secrets["COZE_API_KEY"]
    workflow_id = st.secrets.get("COZE_WORKFLOW_ID_POEM", WORKFLOW_ID_POEM)

    response = requests.post(
        api_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "workflow_id": workflow_id,
            "parameters": _coze_parameters(
                user_input, partner_name, my_name, partner_gender, ta_in_my_eyes, message_to_ta
            ),
        },
        timeout=120,
    )
    response.raise_for_status()
    result = response.json()
    data = result.get("data", {})
    if isinstance(data, str):
        data = json.loads(data)
    poem = data.get("poem", "") or data.get("text", "") or data.get("content", "")
    if isinstance(poem, bytes):
        poem = poem.decode("utf-8", errors="replace")
    if not isinstance(poem, str):
        poem = str(poem)
    poem = poem.strip()
    if not poem:
        raise ValueError("API未返回有效的诗歌文本")
    return poem


def call_coze_workflow_image(
    user_input: str,
    partner_name: str,
    my_name: str,
    partner_gender: str,
    ta_in_my_eyes: str = "",
    message_to_ta: str = "",
) -> str:
    """
    调用画像工作流，仅返回画像 URL。
    ⚠️ 返回结构需与扣子画像 workflow 实际输出一致（如 data.image_url）。
    """
    api_url = "https://api.coze.cn/v1/workflow/run"
    api_key = st.secrets["COZE_API_KEY"]
    workflow_id = st.secrets.get("COZE_WORKFLOW_ID_IMAGE", WORKFLOW_ID_IMAGE)

    response = requests.post(
        api_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "workflow_id": workflow_id,
            "parameters": _coze_parameters(
                user_input, partner_name, my_name, partner_gender, ta_in_my_eyes, message_to_ta
            ),
        },
        timeout=180,
    )
    response.raise_for_status()
    result = response.json()
    data = result.get("data", {})
    image_url = ""
    if isinstance(data, str):
        # 扣子有时直接返回 data 为图片 URL 字符串
        if data.strip().startswith(("http://", "https://")):
            image_url = data.strip()
        else:
            try:
                data = json.loads(data)
                image_url = data.get("image_url", "")
            except (json.JSONDecodeError, TypeError):
                pass
    else:
        image_url = data.get("image_url", "")
    if not image_url:
        raise ValueError("API未返回有效的图片URL")
    return image_url


# ============================================================
# 图片合成：情人节贺卡
# ============================================================
# 运行时下载的中文字体缓存路径（未找到系统/项目字体时使用）
_chinese_font_path_cache: str | None = None

# 可选：未找到字体时从此 URL 下载并缓存（Noto Sans SC，SIL 开源）
_FALLBACK_FONT_URL = (
    "https://cdn.jsdelivr.net/npm/@fontsource/noto-sans-sc@5.0.0/files/"
    "noto-sans-sc-chinese-simplified-400-normal.ttf"
)


def _find_chinese_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """查找可用的中文字体，按平台优先尝试；若无则尝试下载缓存，避免贺卡中文乱码"""
    global _chinese_font_path_cache

    # 优先使用已下载的缓存字体
    if _chinese_font_path_cache and os.path.exists(_chinese_font_path_cache):
        try:
            return ImageFont.truetype(_chinese_font_path_cache, size)
        except (IOError, OSError):
            _chinese_font_path_cache = None

    # 项目内字体（使用与 app.py 同目录的 assets）；优先使用用户放在 assets 的字体
    assets_dir = APP_DIR / ASSETS_DIR
    assets = [
        str(assets_dir / "演示春风楷.ttf"),
        str(assets_dir / "font.ttf"),
        str(assets_dir / "font.otf"),
        str(assets_dir / "NotoSansSC-Regular.otf"),
        str(assets_dir / "NotoSansSC-Regular.ttf"),
    ]
    mac_fonts = [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    linux_fonts = [
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/google-noto-serif-cjk/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    win_fonts = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]
    if sys.platform == "darwin":
        font_candidates = assets + mac_fonts + linux_fonts + win_fonts
    elif sys.platform == "win32":
        font_candidates = assets + win_fonts + mac_fonts + linux_fonts
    else:
        font_candidates = assets + linux_fonts + mac_fonts + win_fonts

    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, size)
        except (IOError, OSError):
            continue

    # 未找到任何本地字体：尝试下载并缓存
    try:
        resp = requests.get(_FALLBACK_FONT_URL, timeout=15)
        resp.raise_for_status()
        font_data = resp.content
        if len(font_data) < 1000:
            raise ValueError("下载的字体文件过小")
        # 优先写入项目 assets，便于持久使用；若不可写则写临时目录
        for base in [assets_dir, Path(os.environ.get("TMPDIR", "/tmp"))]:
            base = Path(base)
            if not base.exists() and base != assets_dir:
                continue
            try:
                if base == assets_dir and not base.exists():
                    base.mkdir(parents=True, exist_ok=True)
                target = base / "astrose_cjk_font.ttf"
                with open(target, "wb") as f:
                    f.write(font_data)
                _chinese_font_path_cache = str(target)
                return ImageFont.truetype(_chinese_font_path_cache, size)
            except (IOError, OSError):
                continue
    except Exception:
        pass

    print("⚠️ 未找到中文字体，使用默认字体（中文可能显示异常）")
    return ImageFont.load_default()


def _download_image(url: str) -> Image.Image:
    """从URL下载图片并返回PIL Image对象"""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content)).convert("RGB")


def _crop_center(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """将图片调整到目标尺寸，居中裁剪"""
    scale = max(target_w / img.width, target_h / img.height)
    new_w = int(img.width * scale)
    new_h = int(img.height * scale)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def create_valentine_card(
    image_url: str,
    poem_text: str,
    partner_name: str = "",
    my_name: str = "",
) -> BytesIO:
    """
    合成情人节贺卡

    画布 800×1200：上半画像，下半诗歌，署名（to TA / 落款 用户），底部署名
    """
    canvas = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # 下半部分浅粉渐变
    for y in range(TEXT_AREA_TOP, CARD_HEIGHT):
        progress = (y - TEXT_AREA_TOP) / (CARD_HEIGHT - TEXT_AREA_TOP)
        r = 255
        g = int(255 - progress * 10)
        b = int(255 - progress * 10)
        draw.line([(0, y), (CARD_WIDTH, y)], fill=(r, g, b))

    # 放置画像
    try:
        portrait = _download_image(image_url)
        portrait = _crop_center(portrait, CARD_WIDTH, IMAGE_AREA_HEIGHT)
        canvas.paste(portrait, (0, 0))
    except Exception:
        placeholder_draw = ImageDraw.Draw(canvas)
        placeholder_draw.rectangle(
            [(0, 0), (CARD_WIDTH, IMAGE_AREA_HEIGHT)],
            fill=(255, 240, 245)
        )
        fallback_font = _find_chinese_font(24)
        placeholder_draw.text(
            (CARD_WIDTH // 2, IMAGE_AREA_HEIGHT // 2),
            "画像加载中...",
            fill=(200, 200, 200),
            font=fallback_font,
            anchor="mm",
        )

    # 诗歌区：留出署名区高度
    poem_font = _find_chinese_font(30)
    poem_lines = [line.strip() for line in poem_text.split("\n") if line.strip()]

    try:
        sample_bbox = poem_font.getbbox("测试Ag")
        single_line_height = sample_bbox[3] - sample_bbox[1]
    except AttributeError:
        single_line_height = 30

    line_spacing = int(single_line_height * 1.5)
    total_poem_height = len(poem_lines) * line_spacing
    poem_area_bottom = SIGNATURE_TOP - 20
    available_height = poem_area_bottom - TEXT_AREA_TOP
    start_y = TEXT_AREA_TOP + (available_height - total_poem_height) // 2
    start_y = max(start_y, TEXT_AREA_TOP + 30)

    for i, line in enumerate(poem_lines):
        y = start_y + i * line_spacing
        if y > poem_area_bottom - line_spacing:
            break
        draw.text(
            (CARD_WIDTH // 2, y),
            line,
            fill=(51, 51, 51),
            font=poem_font,
            anchor="mt",
        )

    # 署名：to 【TA的名字】 / 落款 【用户的名字】
    signature_font = _find_chinese_font(22)
    sig_y1 = SIGNATURE_TOP
    sig_y2 = SIGNATURE_TOP + 28
    if partner_name or my_name:
        if partner_name:
            draw.text(
                (CARD_WIDTH - 60, sig_y1),
                f"to 【{partner_name}】",
                fill=(80, 80, 80),
                font=signature_font,
                anchor="rm",
            )
        if my_name:
            draw.text(
                (CARD_WIDTH - 60, sig_y2),
                f"落款 【{my_name}】",
                fill=(80, 80, 80),
                font=signature_font,
                anchor="rm",
            )

    # 底部署名：Astrose 文案 + 公众号二维码 + 提示
    footer_font = _find_chinese_font(13)
    draw.text(
        (CARD_WIDTH // 2, FOOTER_AREA_TOP + 10),
        CARD_FOOTER_LINE1,
        fill=(153, 153, 153),
        font=footer_font,
        anchor="mm",
    )
    qr_path = Path(ASSETS_DIR) / CARD_FOOTER_QR
    if qr_path.exists():
        try:
            qr_img = Image.open(qr_path).convert("RGB")
            qr_img = qr_img.resize((FOOTER_QR_SIZE, FOOTER_QR_SIZE), Image.Resampling.LANCZOS)
            qr_x = (CARD_WIDTH - FOOTER_QR_SIZE) // 2
            canvas.paste(qr_img, (qr_x, FOOTER_AREA_TOP + 28))
        except Exception:
            pass
    draw.text(
        (CARD_WIDTH // 2, FOOTER_AREA_TOP + 28 + FOOTER_QR_SIZE + 14),
        CARD_FOOTER_PROMPT,
        fill=(153, 153, 153),
        font=footer_font,
        anchor="mm",
    )

    buffer = BytesIO()
    canvas.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    return buffer


def create_text_only_card(
    poem_text: str,
    partner_name: str = "",
    my_name: str = "",
) -> BytesIO:
    """
    合成纯文字版情书贺卡（无画像，上半为占位提示）。
    画布 800×1200：上半占位区，下半诗歌，署名（to TA / 落款 用户），底部署名。
    """
    canvas = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # 下半部分浅粉渐变
    for y in range(TEXT_AREA_TOP, CARD_HEIGHT):
        progress = (y - TEXT_AREA_TOP) / (CARD_HEIGHT - TEXT_AREA_TOP)
        r = 255
        g = int(255 - progress * 10)
        b = int(255 - progress * 10)
        draw.line([(0, y), (CARD_WIDTH, y)], fill=(r, g, b))

    # 上半部分：浅粉底 + 占位文案
    draw.rectangle(
        [(0, 0), (CARD_WIDTH, IMAGE_AREA_HEIGHT)],
        fill=(255, 240, 245),
    )
    placeholder_font = _find_chinese_font(28)
    draw.text(
        (CARD_WIDTH // 2, IMAGE_AREA_HEIGHT // 2),
        "专属画像生成中…",
        fill=(200, 200, 200),
        font=placeholder_font,
        anchor="mm",
    )

    # 诗歌区：留出署名区高度
    poem_font = _find_chinese_font(30)
    poem_lines = [line.strip() for line in poem_text.split("\n") if line.strip()]

    try:
        sample_bbox = poem_font.getbbox("测试Ag")
        single_line_height = sample_bbox[3] - sample_bbox[1]
    except AttributeError:
        single_line_height = 30

    line_spacing = int(single_line_height * 1.5)
    total_poem_height = len(poem_lines) * line_spacing
    poem_area_bottom = SIGNATURE_TOP - 20
    available_height = poem_area_bottom - TEXT_AREA_TOP
    start_y = TEXT_AREA_TOP + (available_height - total_poem_height) // 2
    start_y = max(start_y, TEXT_AREA_TOP + 30)

    for i, line in enumerate(poem_lines):
        y = start_y + i * line_spacing
        if y > poem_area_bottom - line_spacing:
            break
        draw.text(
            (CARD_WIDTH // 2, y),
            line,
            fill=(51, 51, 51),
            font=poem_font,
            anchor="mt",
        )

    # 署名：to 【TA的名字】 / 落款 【用户的名字】
    signature_font = _find_chinese_font(22)
    sig_y1 = SIGNATURE_TOP
    sig_y2 = SIGNATURE_TOP + 28
    if partner_name or my_name:
        if partner_name:
            draw.text(
                (CARD_WIDTH - 60, sig_y1),
                f"to 【{partner_name}】",
                fill=(80, 80, 80),
                font=signature_font,
                anchor="rm",
            )
        if my_name:
            draw.text(
                (CARD_WIDTH - 60, sig_y2),
                f"落款 【{my_name}】",
                fill=(80, 80, 80),
                font=signature_font,
                anchor="rm",
            )

    # 底部署名：Astrose 文案 + 公众号二维码 + 提示
    footer_font = _find_chinese_font(13)
    draw.text(
        (CARD_WIDTH // 2, FOOTER_AREA_TOP + 10),
        CARD_FOOTER_LINE1,
        fill=(153, 153, 153),
        font=footer_font,
        anchor="mm",
    )
    qr_path = Path(ASSETS_DIR) / CARD_FOOTER_QR
    if qr_path.exists():
        try:
            qr_img = Image.open(qr_path).convert("RGB")
            qr_img = qr_img.resize((FOOTER_QR_SIZE, FOOTER_QR_SIZE), Image.Resampling.LANCZOS)
            qr_x = (CARD_WIDTH - FOOTER_QR_SIZE) // 2
            canvas.paste(qr_img, (qr_x, FOOTER_AREA_TOP + 28))
        except Exception:
            pass
    draw.text(
        (CARD_WIDTH // 2, FOOTER_AREA_TOP + 28 + FOOTER_QR_SIZE + 14),
        CARD_FOOTER_PROMPT,
        fill=(153, 153, 153),
        font=footer_font,
        anchor="mm",
    )

    buffer = BytesIO()
    canvas.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    return buffer


# ============================================================
# 页面渲染：首页（输入页）
# ============================================================
def render_input_page():
    """渲染首页 - 情书输入界面"""

    # 获取用户身份标识
    fingerprint = get_browser_fingerprint()
    client_ip = get_client_ip()

    # 标题区域
    st.markdown("# ✨ Astrose")
    st.markdown('<p class="subtitle">Write your romance in the stars.</p>', unsafe_allow_html=True)
    st.markdown('<p class="hint-text">💡 每人可免费生成{}次</p>'.format(MAX_PER_USER), unsafe_allow_html=True)

    # ----- 检查限制 -----
    allowed, reason, remaining = check_rate_limit(fingerprint, client_ip)

    if not allowed:
        if reason == "total":
            st.markdown("""
            <div class="limit-box">
                <h3>❌ 今天的免费额度已用完 🥹</h3>
                <p>太受欢迎啦！今天已经为 {} 对情侣生成了画像。</p>
                <p>💕 可以在小红书评论区留言<br>我会手动帮你生成 ❤️</p>
                <p><strong>小红书：nyota佳树</strong></p>
            </div>
            """.format(TOTAL_LIMIT), unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="limit-box">
                <h3>❌ 你今天的次数已用完（{max}/{max}）🥹</h3>
                <p>💕 还想要更多？</p>
                <p>- 明天再来（每天重置）<br>- 或在小红书评论区留言，我会手动帮你生成</p>
                <p><strong>小红书：nyota佳树</strong></p>
            </div>
            """.format(max=MAX_PER_USER), unsafe_allow_html=True)
        return

    # ----- 输入区域 -----
    col_left, col_right = st.columns(2)
    with col_left:
        partner_name = st.text_input(
            "TA的称呼",
            key="partner_name_input",
        )
    with col_right:
        my_name = st.text_input(
            "你的称呼",
            key="my_name_input",
        )

    partner_gender = st.radio(
        "TA的性别",
        options=["女", "男", "无性别"],
        horizontal=True,
        key="partner_gender_input",
    )

    ta_in_my_eyes = st.text_area(
        "你眼中的Ta",
        placeholder="如：漂亮的短发，笑起来有浅浅的梨涡，眼睛很亮",
        height=100,
        key="ta_in_my_eyes_input",
        help="可以描述ta的外表特征或者你心中的ta的形象，用于生成ta的专属画像",
    )

    message_to_ta = st.text_input(
        "想对ta说的一句话",
        placeholder="如：谢谢你一直在我身边",
        key="message_to_ta_input",
    )

    user_input = st.text_area(
        "请写下你和TA的故事...",
        placeholder="可以描述你们经历的几个有意义的瞬间",
        height=150,
        key="love_letter_input",
        help="可以描述你们经历的几个有意义的瞬间",
    )

    # 生成按钮
    if st.button("✨ 生成TA的画像", type="primary", use_container_width=True):
        if not partner_name or not partner_name.strip():
            st.warning("请填写TA的称呼 ❤️")
            return
        if not my_name or not my_name.strip():
            st.warning("请填写你的称呼 ❤️")
            return
        if not user_input or not user_input.strip():
            st.warning("请先写下你想说的话 ❤️")
            return

        # ⚠️ 点击时再次校验（防止页面停留期间额度耗尽）
        allowed2, reason2, _ = check_rate_limit(fingerprint, client_ip)
        if not allowed2:
            st.error("次数已用完，请明天再来 🥹")
            return

        with st.spinner("正在为你创作小诗... ✨"):
            try:
                poem = call_coze_workflow_poem(
                    user_input=user_input.strip(),
                    partner_name=partner_name.strip(),
                    my_name=my_name.strip(),
                    partner_gender=partner_gender,
                    ta_in_my_eyes=(ta_in_my_eyes or "").strip(),
                    message_to_ta=(message_to_ta or "").strip(),
                )

                st.session_state.generated_poem = poem
                st.session_state.generated_image_url = None
                st.session_state.card_image = None
                st.session_state.image_request_failed = False
                st.session_state.generation_inputs = {
                    "user_input": user_input.strip(),
                    "partner_name": partner_name.strip(),
                    "my_name": my_name.strip(),
                    "partner_gender": partner_gender,
                    "ta_in_my_eyes": (ta_in_my_eyes or "").strip(),
                    "message_to_ta": (message_to_ta or "").strip(),
                }

                # 记录使用（仅小诗生成计一次）
                record_usage(fingerprint, client_ip)

                st.session_state.page = "result"
                st.rerun()

            except requests.exceptions.Timeout:
                st.error("生成超时，请重试 🥹")
            except requests.exceptions.RequestException:
                st.error("生成失败，请重试 🥹")
            except ValueError as e:
                st.error(f"生成失败：{e}")
            except Exception:
                st.error("生成失败，请重试 🥹")

    # 剩余次数
    left = get_remaining_count(fingerprint, client_ip)
    st.markdown(
        '<p class="usage-counter">剩余生成次数：{} / {}</p>'.format(left, MAX_PER_USER),
        unsafe_allow_html=True,
    )


# ============================================================
# 页面渲染：结果页
# ============================================================
def render_result_page():
    """渲染结果页 - 先展示纯文字贺卡，再在后台生成带头像版"""

    fingerprint = get_browser_fingerprint()
    client_ip = get_client_ip()
    poem = st.session_state.generated_poem

    st.balloons()
    st.markdown("# ✨ 你的专属情书贺卡")

    # 1. 纯文字版：有诗就展示并支持下载（含署名 to TA / 落款 用户）
    inputs = st.session_state.generation_inputs
    partner_name = (inputs.get("partner_name") or "").strip() if inputs else ""
    my_name = (inputs.get("my_name") or "").strip() if inputs else ""

    if poem:
        st.markdown("### 📝 纯文字版")
        text_only_buffer = create_text_only_card(poem, partner_name, my_name)
        text_only_buffer.seek(0)
        st.image(text_only_buffer, use_container_width=True)
        text_only_buffer.seek(0)
        st.download_button(
            label="💾 保存纯文字版",
            data=text_only_buffer,
            file_name="valentine_card_text.png",
            mime="image/png",
            use_container_width=True,
            key="dl_text_only",
        )

    # 2. 带头像版：若尚未生成则请求画像工作流（一直等到成功或失败）
    if poem and st.session_state.generated_image_url is None and not st.session_state.image_request_failed:
        if inputs:
            with st.spinner("正在生成专属画像，请稍候…"):
                try:
                    image_url = call_coze_workflow_image(**inputs)
                    st.session_state.generated_image_url = image_url
                    try:
                        st.session_state.card_image = create_valentine_card(
                            image_url, poem, partner_name, my_name
                        )
                    except Exception:
                        st.session_state.card_image = None
                    if fingerprint:
                        _save_last_result(
                            fingerprint, image_url, poem, partner_name, my_name
                        )
                    st.rerun()
                except Exception:
                    st.session_state.image_request_failed = True
                    st.rerun()

    if st.session_state.card_image is not None:
        st.markdown("### 🖼 带头像版")
        st.session_state.card_image.seek(0)
        st.image(st.session_state.card_image, use_container_width=True)
        st.session_state.card_image.seek(0)
        st.download_button(
            label="💾 保存带头像版",
            data=st.session_state.card_image,
            file_name="valentine_card_with_portrait.png",
            mime="image/png",
            use_container_width=True,
            key="dl_with_portrait",
        )
    elif poem and st.session_state.generated_image_url is None and st.session_state.image_request_failed:
        st.warning("专属画像生成失败，仅提供纯文字版；可点击「重新生成」再试。")
    elif poem and st.session_state.generated_image_url and st.session_state.card_image is None:
        st.markdown("### 🖼 带头像版")
        try:
            st.image(st.session_state.generated_image_url, use_container_width=True)
        except Exception:
            st.error("图片加载失败，仅提供纯文字版。")

    left = get_remaining_count(fingerprint, client_ip)
    st.markdown(
        '<p class="usage-counter">你今天还有 {} 次机会 ❤️</p>'.format(left),
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ----- 引流区域 -----
    st.markdown("### 🎁 获取更多AI恋爱玩法")

    col_left, col_right = st.columns(2)

    with col_left:
        xhs_qr = os.path.join(ASSETS_DIR, "xiaohongshu_qr.png")
        if os.path.exists(xhs_qr):
            st.image(xhs_qr, use_container_width=True)
        st.markdown(
            '<p style="text-align:center; color:#E91E63;">关注小红书：<strong>nyota佳树</strong></p>',
            unsafe_allow_html=True,
        )

    with col_right:
        wechat_qr = os.path.join(ASSETS_DIR, "wechat_qr.png")
        if os.path.exists(wechat_qr):
            st.image(wechat_qr, use_container_width=True)
        st.markdown(
            '<p style="text-align:center; color:#E91E63;">加入<strong>AI恋爱助手群</strong></p>',
            unsafe_allow_html=True,
        )

    with st.expander("❤️ 如果喜欢，请我喝杯咖啡"):
        pay_left, pay_right = st.columns(2)

        with pay_left:
            wechat_pay = os.path.join(ASSETS_DIR, "wechat_pay_qr.png")
            if os.path.exists(wechat_pay):
                st.image(wechat_pay, use_container_width=True)
            st.markdown(
                '<p style="text-align:center; font-size:0.9rem;">微信支付</p>',
                unsafe_allow_html=True,
            )

        with pay_right:
            alipay_qr = os.path.join(ASSETS_DIR, "alipay_qr.png")
            if os.path.exists(alipay_qr):
                st.image(alipay_qr, use_container_width=True)
            st.markdown(
                '<p style="text-align:center; font-size:0.9rem;">支付宝</p>',
                unsafe_allow_html=True,
            )

        st.markdown(
            '<p style="text-align:center; color:#999; font-size:0.8rem;">任意金额都是鼓励 ☕</p>',
            unsafe_allow_html=True,
        )

    st.markdown("")
    if st.button("🔄 重新生成", use_container_width=True):
        st.session_state.page = "input"
        st.session_state.card_image = None
        st.session_state.generated_poem = None
        st.session_state.generated_image_url = None
        st.session_state.generation_inputs = None
        st.session_state.image_request_failed = False
        st.rerun()

    st.markdown(
        '<p class="footer-text">Astrose — Write your romance in the stars.</p>',
        unsafe_allow_html=True,
    )


# ============================================================
# 主路由
# ============================================================
def main():
    # 同用户再进或刷新时：若有当日持久化结果则恢复为结果页
    fingerprint = get_browser_fingerprint()
    if (
        fingerprint
        and st.session_state.page != "result"
        and st.session_state.card_image is None
    ):
        data = _load_last_results()
        saved = data.get("results", {}).get(fingerprint)
        if saved:
            image_url = saved.get("image_url", "")
            poem = saved.get("poem", "")
            partner_name = saved.get("partner_name", "")
            my_name = saved.get("my_name", "")
            if image_url and poem:
                st.session_state.page = "result"
                st.session_state.generated_image_url = image_url
                st.session_state.generated_poem = poem
                try:
                    st.session_state.card_image = create_valentine_card(
                        image_url, poem, partner_name, my_name
                    )
                except Exception:
                    st.session_state.card_image = None

    if st.session_state.page == "result":
        render_result_page()
    else:
        render_input_page()


if __name__ == "__main__":
    main()
