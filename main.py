from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image, Plain, Forward, Node
import requests
import json
import os
import tempfile

@register("lanraragi", "LanraragiSearch", "Lanraragi 搜索插件", "1.0.0")
class LanraragiSearch(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.api_url = "http://192.168.31.1:3000/api"
        self.api_key = "123456"
        self.temp_dir = tempfile.gettempdir()

    async def download_thumbnail(self, url, arcid):
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            # 保存到临时文件
            img_path = os.path.join(self.temp_dir, f"{arcid}.jpg")
            with open(img_path, 'wb') as f:
                f.write(response.content)
            return img_path
        except Exception as e:
            logger.error(f"下载缩略图失败：{e}")
            return None

    @filter.command("ex")
    async def search(self, event: AstrMessageEvent):
        """搜索 Lanraragi 中的内容，使用方法：/ex 关键词"""
        args = event.message_str.split(maxsplit=1)
        if len(args) < 2:
            yield event.plain_result("请输入搜索关键词，例如：/ex 团队:壁の彩度")
            return

        search_query = args[1]
        search_url = f"{self.api_url}/search?filter={search_query}&start=-1&"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        try:
            response = requests.get(search_url, headers=headers)
            response.raise_for_status()
            
            search_result = response.json()
            
            if not search_result["data"]:
                yield event.plain_result("未找到相关结果")
                return

            results = search_result["data"][:5]
            message_text = f"找到 {len(search_result['data'])} 个结果：\n\n"
            
            # 添加每个搜索结果
            for item in results:
                title = item.get("title", "无标题")
                arcid = item["arcid"]
                reader_url = f"https://写你外网访问的地址和端口:66/reader?id={arcid}"
                
                # 构建格式化的文本
                message_text += f"{title}\n"  # 标题
                message_text += f"阅读链接：{reader_url}\n"  # 链接
                message_text += "------------------------\n"  # 分隔线
            
            # 发送单条消息
            yield event.plain_result(message_text)

        except Exception as e:
            error_msg = f"搜索出错：{str(e)}"
            logger.error(error_msg, exc_info=True)
            yield event.plain_result(error_msg)

    async def terminate(self):
        logger.info("Lanraragi 搜索插件已终止")