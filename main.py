from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain
import httpx
import os
import tempfile
from PIL import Image as PILImage
import io
from datetime import datetime

@register("lanraragi", "LanraragiSearch", "Lanraragi 搜索插件", "1.2.0")
class LanraragiSearch(Star):
    def __init__(self, context: Context, config: dict):
        # 使用配置信息，如果没有则使用默认值
        super().__init__(context)
        self.config = config
        self.api_url = config.get('api_url')
        self.api_key = config.get('api_key')
        self.external_url = config.get('external_url')
        self.temp_dir = tempfile.gettempdir()
        self.client = httpx.AsyncClient(timeout=30.0)  # 创建异步客户端

    async def download_thumbnail(self, url, arcid):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            
            # 将图片数据转换为PIL Image对象
            return PILImage.open(io.BytesIO(response.content))
        except Exception as e:
            logger.error(f"下载缩略图失败：{e}")
            return None

    def create_combined_image(self, images):
        """将多个缩略图拼接成一张图片"""
        if not images:
            return None

        # 过滤掉None值
        valid_images = [img for img in images if img is not None]
        if not valid_images:
            return None

        # 设置统一的目标高度
        target_height = 800  # 统一高度
        padding = 10  # 图片间距
        
        # 计算每张图片按比例缩放后的宽度
        scaled_widths = []
        for img in valid_images:
            # 获取原始尺寸
            width, height = img.size
            # 按高度等比例缩放
            scaled_width = int((width * target_height) / height)
            scaled_widths.append(scaled_width)
        
        # 计算总宽度（包含间距）
        total_width = sum(scaled_widths) + (len(valid_images) - 1) * padding
        
        # 创建新图片
        combined_image = PILImage.new('RGB', (total_width, target_height), (255, 255, 255))

        # 拼接图片
        x_offset = 0
        for img, scaled_width in zip(valid_images, scaled_widths):
            # 调整图片大小，保持比例
            img = img.convert('RGB')
            img = img.resize((scaled_width, target_height), PILImage.Resampling.LANCZOS)
            
            # 粘贴到新图片上
            combined_image.paste(img, (x_offset, 0))
            x_offset += scaled_width + padding

        # 添加随机色块以规避图片审查
        self.add_random_blocks(combined_image)

        # 保存到临时文件
        temp_path = os.path.join(self.temp_dir, 'combined_thumbnails.jpg')
        combined_image.save(temp_path, 'JPEG')
        return temp_path
        
    def add_random_blocks(self, image):
        """添加随机色块以规避图片审查"""
        import random
        from PIL import ImageDraw
        
        width, height = image.size
        draw = ImageDraw.Draw(image)
        
        # 添加10-20个随机色块
        num_blocks = random.randint(10, 20)
        
        for _ in range(num_blocks):
            # 随机位置
            x1 = random.randint(0, width - 1)
            y1 = random.randint(0, height - 1)
            
            # 随机大小（较小，不影响观看）
            block_width = random.randint(3, 8)
            block_height = random.randint(3, 8)
            
            # 确保色块不超出图片边界
            x2 = min(x1 + block_width, width - 1)
            y2 = min(y1 + block_height, height - 1)
            
            # 随机颜色（半透明）
            r = random.randint(0, 255)
            g = random.randint(0, 255)
            b = random.randint(0, 255)
            alpha = random.randint(30, 100)  # 透明度
            
            # 绘制半透明色块
            color = (r, g, b, alpha)
            
            # 获取原始像素
            for x in range(x1, x2):
                for y in range(y1, y2):
                    if 0 <= x < width and 0 <= y < height:
                        # 获取当前像素颜色
                        current = image.getpixel((x, y))
                        
                        # 混合颜色（考虑透明度）
                        new_r = int((current[0] * (255 - alpha) + r * alpha) / 255)
                        new_g = int((current[1] * (255 - alpha) + g * alpha) / 255)
                        new_b = int((current[2] * (255 - alpha) + b * alpha) / 255)
                        
                        # 设置新颜色
                        image.putpixel((x, y), (new_r, new_g, new_b))

    @filter.command("ex")
    async def search(self, event: AstrMessageEvent):
        """搜索 Lanraragi 中的内容，使用方法：/ex 关键词"""
        args = event.message_str.split(maxsplit=1)
        if len(args) < 2:
            yield event.plain_result("请输入搜索关键词，例如：/ex 团队:壁の彩度")
            return

        search_query = args[1]
        search_url = f"{self.api_url}/search/random?filter={search_query}&start=20"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        try:
            response = await self.client.get(search_url, headers=headers)
            response.raise_for_status()
            
            search_result = response.json()
            
            if not search_result["data"]:
                yield event.plain_result("未找到相关结果")
                return

            results = search_result["data"][:5]
            
            # 下载所有缩略图
            thumbnails = []
            for item in results:
                thumb_url = f"{self.api_url}/archives/{item['arcid']}/thumbnail"  # 修改缩略图URL格式
                thumb = await self.download_thumbnail(thumb_url, item['arcid'])
                thumbnails.append(thumb)

            # 创建拼接图片
            combined_image_path = self.create_combined_image(thumbnails)
            
            # 构建消息内容
            message_components = []
            
            # 添加拼接后的缩略图
            if combined_image_path:
                message_components.append(Image(combined_image_path))
            
            # 添加文字内容
            message_text = f"搜索结果中，随机展示 {len(search_result['data'])} 个结果：\n\n"
            
            # 添加每个搜索结果
            for item in results:
                title = item.get("title", "无标题")
                arcid = item["arcid"]
                reader_url = f"{self.external_url}/reader?id={arcid}"
                
                # 构建格式化的文本
                message_text += f"📚 {title}\n"  # 标题
                message_text += f"🔗 阅读链接：{reader_url}\n"  # 链接
                message_text += "------------------------\n"  # 分隔线
            
            message_components.append(Plain(message_text))
            
            # 发送消息
            yield MessageEventResult(message_components)  # 直接传入消息组件列表作为位置参数

        except Exception as e:
            error_msg = f"搜索出错：{str(e)}"
            logger.error(error_msg, exc_info=True)
            yield event.plain_result(error_msg)

    async def terminate(self):
        # 关闭异步客户端
        await self.client.aclose()
        logger.info("Lanraragi 搜索插件已终止")

    async def handle_ehentai_link(self, event: AstrMessageEvent):
        import re
        match = re.search(r'https://e[-x]hentai\.org/g/(\d+)/([0-9a-f]{10})', event.message_str)
        if not match:
            return
        url, gid, token = match.group(0, 1, 2)
        # 获取元数据
        api_url = 'https://api.e-hentai.org/api.php'
        data = {"method": "gdata", "gidlist": [[int(gid), token]], "namespace": 1}
        try:
            response = await self.client.post(api_url, json=data)
            response.raise_for_status()
            gdata = response.json()['gmetadata'][0]
            title = gdata['title']
            title_jpn = gdata['title_jpn']
            category = gdata['category']
            uploader = gdata['uploader']
            posted = datetime.fromtimestamp(float(gdata['posted']))
            filecount = gdata['filecount']
            rating = gdata['rating']
            translated_tags = self.translate_tags(gdata['tags'])
            tags = ', '.join(translated_tags)
            thumb_url = gdata['thumb']
            # 下载封面
            thumb_resp = await self.client.get(thumb_url)
            thumb_resp.raise_for_status()
            thumb_img = PILImage.open(io.BytesIO(thumb_resp.content))
            # 保存临时文件
            temp_path = os.path.join(self.temp_dir, 'ehentai_thumb.jpg')
            thumb_img.save(temp_path, 'JPEG')
            # 构建消息
            message_text = f"📌 标题：{title}\n📙 日文标题：{title_jpn}\n📂 类型：{category}\n👤 上传者：{uploader}\n🕒 上传时间：{posted:%Y-%m-%d %H:%M}\n📄 页数：{filecount}\n⭐ 评分：{rating}\n🏷️ 标签：{tags}"
            message_components = [Image(temp_path), Plain(message_text)]
            yield MessageEventResult(message_components)
        except Exception as e:
            logger.error(f"处理 e-hentai 链接出错：{e}")
            yield event.plain_result("处理链接出错")

    def translate_tags(self, tags_list):
        import json
        db_path = '/AstrBot/data/plugins/astrbot_plugin_lanraragi/db.text.json'
        with open(db_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        target = data['data']
        translated = []
        for item in tags_list:
            parts = item.split(':', 1)
            if len(parts) == 2:
                namespace, key = parts
            else:
                translated.append(item)
                continue
            for element in target:
                if element['namespace'] == namespace:
                    ns_name = element['frontMatters']['name']
                    translated_item = item.replace(namespace, ns_name, 1)
                    data_dict = element.get('data', {})
                    if key in data_dict:
                        value = data_dict[key]['name']
                        translated_item = translated_item.replace(key, value, 1)
                    translated.append(translated_item)
                    break
            else:
                translated.append(item)
        return translated

    @filter.regex(r'https://e[-x]hentai\.org/g/\d+/[0-9a-f]{10}')
    async def message_handler(self, event: AstrMessageEvent):
        async for result in self.handle_ehentai_link(event):
            yield result