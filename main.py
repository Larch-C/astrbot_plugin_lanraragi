from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain, Forward, Node
import requests
import json
import os
import tempfile
from PIL import Image as PILImage
import io

@register("lanraragi", "LanraragiSearch", "Lanraragi 搜索插件", "1.0.0")
class LanraragiSearch(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.api_url = "http://192.168.31.136:3000/api" #这里/api不要丢了
        self.api_key = "123456"
        self.external_url = "https://lanraragi.com:3000"
        self.temp_dir = tempfile.gettempdir()

    async def download_thumbnail(self, url, arcid):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            response = requests.get(url, headers=headers)
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

        # 计算拼接图片的大小
        thumb_width = 200  # 缩略图宽度
        thumb_height = 300  # 缩略图高度
        padding = 10  # 图片间距
        
        # 创建新图片
        total_width = (thumb_width + padding) * len(valid_images) - padding
        total_height = thumb_height
        combined_image = PILImage.new('RGB', (total_width, total_height), (255, 255, 255))

        # 拼接图片
        x_offset = 0
        for img in valid_images:
            # 调整图片大小
            img = img.convert('RGB')
            img = img.resize((thumb_width, thumb_height), PILImage.Resampling.LANCZOS)
            
            # 粘贴到新图片上
            combined_image.paste(img, (x_offset, 0))
            x_offset += thumb_width + padding

        # 保存到临时文件
        temp_path = os.path.join(self.temp_dir, 'combined_thumbnails.jpg')
        combined_image.save(temp_path, 'JPEG')
        return temp_path

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
            response = requests.get(search_url, headers=headers)
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
        logger.info("Lanraragi 搜索插件已终止")