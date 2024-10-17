from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *  # 导入事件类
from mirai import MessageChain,At,Image
import asyncio
import os
import json
import requests

"""查询频率，单位为秒，推荐为60"""
CHECK_DELAY = 60
"""发生问题时，是否通知管理员(通知则把ID修改为机器人管理员的QQ)"""
NOTIFY_ADMIN = False
ADMIN_ID = None   # int

# https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomBaseInfo?room_ids=room_id&req_biz=video
# 注册插件
@register(name="BreminderPlugin", description="订阅B站UP主的开播状态信息（施工中）", version="0.1", author="Hanschase")
class BreminderPlugin(BasePlugin):
    # 插件加载时触发
    def __init__(self, host: APIHost):
        # 检测是否存在subscription.json
        if not os.path.exists("subscription.json"):
            self.ap.logger.error("The file subscription.json was not found; it has been created and initialized.")
            with open("subscription.json", "w", encoding="utf-8") as f:
                data = {
                    "group_ids":[]
                }
                '''
                样例示范：
                {
                 "group_ids":[],        # 群号列表
                 "group_id": {          # 群号
                     "room_ids": [
                         "room_id1",
                         "room_id2"
                     ],
                     "room_id": [
                         "0",           # 房间状态码
                         "member_id1",
                         "member_id2"
                     ]
                 }
                 '''
                json.dump(data, f, indent=4)
        try:
            with open("subscription.json", "r", encoding="utf-8") as f:
                self.subscription = json.load(f)
        except json.JSONDecodeError:
            self.ap.logger.error("subscription.json decoding failed")
            print("subscription.json decoding failed")

    # 异步初始化
    async def initialize(self):
        pass
    # 写入json
    def write_json(self):
        with open("subscription.json", "w", encoding="utf-8") as f:
            json.dump(self.subscription, f, indent=4)

    # 执行任务
    async def run(self, ctx:EventContext):
        while True:
            for group_id in self.subscription["group_ids"]:
                for room_id in self.subscription[group_id]["room_ids"]:
                    if int(self.subscription[group_id][room_id][0]) == 0:  # 上一时段状态为未开播时
                        live_status = self.check_room_live(room_id)
                        if live_status == 1:
                            self.subscription[group_id][room_id][0] = 1 # 修改开播状态
                            await self.notify_person(group_id,room_id,ctx) # 通知群友
                    elif int(self.subscription[group_id][room_id][0]) == 1:  # 上一时段为开播时
                        live_status = self.check_room_live(room_id)
                        if live_status == 0 or 2:   # 增加轮播状态判定
                            self.subscription[group_id][room_id][0] = 0  # 修改未开播状态
                    else:
                        if NOTIFY_ADMIN:
                            await ctx.send_message("person",ADMIN_ID,[f"直播间通知插件出了点问题，去看看后台,房间号{room_id},群号：{group_id}，状态码：{self.subscription[group_id][room_id][0]}"])
                    self.write_json()
            await asyncio.sleep(CHECK_DELAY)

    # 通知群友
    async def notify_person(self,group_id,room_id,ctx:EventContext):  # 一直在重复请求，不知道会不会被ban，出问题再说
        API = f'https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomBaseInfo?room_ids={room_id}&req_biz=video'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://live.bilibili.com/{room_id}",
        }
        try:
            response = requests.get(API, headers=headers)
            response.raise_for_status()  # 如果请求返回错误状态码，会引发异常
            data = response.json()
            room_cover = data["data"]["by_room_ids"][room_id]["cover"]   # 封面
            room_title = data["data"]["by_room_ids"][room_id]["title"]   # 直播间标题
            up_name = data["data"]["by_room_ids"][room_id]["uname"]      # UP主
            room_url = data["data"]["by_room_ids"][room_id]["live_url"]  # 直播间地址
            atperson = MessageChain()
            for person_id in self.subscription[group_id][room_id][1:]:  # 排除状态码
                atperson.append(At(int(person_id)))
            await ctx.send_message("group",int(group_id),atperson + MessageChain([
                f"\n您订阅的直播间开播啦！",
                Image(url=room_cover),
                f"直播间标题：{room_title}",
                f"\nUP主：{up_name}",
                f"\n直播间地址：{room_url}"
            ]))
            await ctx.send_message("person", ADMIN_ID,[f"朝{group_id}的{atperson}发送了订阅信息"])
        except Exception as e:
            self.ap.logger.error(f"在调用notify_person函数时，发生错误：{e}")

    # 查询直播间状态
    def check_room_live(self,room_id):
        API = f'https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomBaseInfo?room_ids={room_id}&req_biz=video'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://live.bilibili.com/{room_id}",
        }
        try:
            response = requests.get(API, headers=headers)
            response.raise_for_status()  # 如果请求返回错误状态码，会引发异常
            data = response.json()
            live_status = int(data["data"]["by_room_ids"][room_id]["live_status"])
            return live_status
        except Exception as e:
            self.ap.logger.error(f"在调用check_room_live函数时，访问URL失败，发生错误：{e}")
            return -400  # 400：Bad Request

    # 检查B站直播间是否存在
    def check_if_exit(self, room_id):
        API = f'https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomBaseInfo?room_ids={room_id}&req_biz=video'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://live.bilibili.com/{room_id}",
        }
        try:
            response = requests.get(API, headers=headers)
            response.raise_for_status()  # 如果请求返回错误状态码，会引发异常
            data = response.json()
            code = data['code']
        except Exception as e:
            self.ap.logger.error(f"在调用check_if_exit函数时，访问URL失败，发生错误：{e}")
            return e
        return code

    # 检查是否已经注册提醒
    def check_if_apply(self,group_id,person_id,room_id):
        if group_id in self.subscription["group_ids"]:
            if room_id in self.subscription[group_id]:
                if person_id in self.subscription[group_id][room_id][1:]:   # 【1：】排除状态码
                    return True

    # 写入注册信息
    def apply_sub(self,group_id,person_id,room_id):
        if group_id not in self.subscription["group_ids"]:
            self.subscription["group_ids"].append(group_id)
            self.subscription[group_id]={
                "room_ids": []
            }
        if room_id not in self.subscription[group_id]:
            self.subscription[group_id]["room_ids"].append(room_id)
            self.subscription[group_id][room_id] = [0]
        if person_id not in self.subscription[group_id][room_id]:
            self.subscription[group_id][room_id].append(person_id)
        self.write_json()

    # 开始监控信息
    @handler(GroupCommandSent)
    async def cmd_run(self, ctx: EventContext):
        command = ctx.event.command
        if command == "startrem":
            ctx.prevent_default()
            ctx.prevent_postorder()
            if hasattr(self, 'run_task') and not self.run_task.done():
                await ctx.reply(["订阅任务已经开始执行了哦~"])
                return
            try:
                self.run_task = asyncio.create_task(self.run(ctx))
                await ctx.reply(["订阅任务开始执行"])
            except Exception as e:
                self.ap.logger.error(f"Error starting task: {e}")
        elif command == "apply":
            self.ap.logger.info(f"执行apply命令")
            group_id = str(ctx.event.launcher_id)
            person_id = str(ctx.event.sender_id)
            room_id = ctx.event.text_message.split()[1]
            ctx.prevent_default()
            ctx.prevent_postorder()
            code = self.check_if_exit(room_id)
            if code == -400:
                await ctx.reply([At(int(ctx.event.sender_id)),"房间号不存在，请检查B站直播间号格式或者指令输入是否正确！"])
            elif code == 0:
                if self.check_if_apply(group_id,person_id,room_id):
                    await ctx.reply([At(int(ctx.event.sender_id)), f"已经注册过B站直播间号[{room_id}],请不要重复注册哦~"])
                else:
                    await ctx.reply([At(int(ctx.event.sender_id)), f"成功订阅B站直播间号[{room_id}],在开播时我会通知你哦！"])
                    self.apply_sub(group_id,person_id,room_id)
            else:
                await ctx.reply([At(int(ctx.event.sender_id)), f"抱歉,订阅直播间发生了一个错误：{code}，请联系管理员"])
        elif command == "cancel":
            self.ap.logger.info(f"执行cancel命令")
            group_id = str(ctx.event.launcher_id)
            person_id = str(ctx.event.sender_id)
            room_id = ctx.event.text_message.split()[1]
            ctx.prevent_default()
            ctx.prevent_postorder()
            if self.check_if_apply(group_id, person_id, room_id):  # 如果订阅了就开始逐层删除
                self.subscription[group_id][room_id].remove(person_id)
                if len(self.subscription[group_id][room_id]) == 1:  # 如果只剩状态码，删了
                    del self.subscription[group_id][room_id]
                    self.subscription[group_id]["room_ids"].remove(room_id)
                    if len(self.subscription[group_id]["room_ids"]) == 0:  # 如果该群号没有订阅房间，删了
                        del self.subscription[group_id]
                        self.subscription["group_ids"].remove(group_id)
                await ctx.reply([At(int(ctx.event.sender_id)), f"成功取消订阅B站直播间号{room_id}"])
                self.write_json()
            else:
                await ctx.reply([At(int(ctx.event.sender_id)), f"您并未订阅B站直播间号{room_id}"])

    # 插件卸载时触发
    def __del__(self):
        pass
