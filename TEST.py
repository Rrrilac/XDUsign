import ffmpeg
import json
import os
import re
import requests
import string
import sys
import time
import threading
from cv2 import imread
from pyzbar import pyzbar
from datetime import datetime, timedelta
from loguru import logger as log
from random import choices, randint
from core import account, web, users, URL_WEEK_TABLES, URL_COURSES
from core import validate_pass, download_ts, get_code, update_account, validate_again

account, send_key, password, uid, fid, name, exit_code = [None] * 7
web = requests.session()


# 这里是专门用来测试的模块，也可以根据需求构建其他的测试函数
# 获取直播流
def get_stream():
    code = get_code('A-105')
    stream_url = f'http://202.117.115.53:8092/pag/202.117.115.50/7302/00{code}/0/MAIN/TCP/live.m3u8'
    capture_first(stream_url)


def capture_first(url_ts):
    global exit_code
    last_ts_name = None
    quit_number = 10
    while quit_number:
        try:
            t_s = datetime.now()
            # t_s, t_e 用于测试每个包接收加处理的时间
            # 使用requests库获取M3U8文件内容
            response = requests.get(url_ts)
            m3u8_content = response.text
            # 找到TS流的URL（通常在M3U8文件中以.ts结尾）
            ts_name = m3u8_content.splitlines()[-1]
            # 对于网络通畅情况，选择等待下一个包
            if ts_name != last_ts_name:
                ts_url = url_ts.rsplit('/', 1)[0] + '/' + ts_name
                # 我真的是气死，timeout属性必须放最前面，但ffmpeg-python的开发作者没想到这个
                # 只能本地保存.ts了
                log.info(f"[测试]预下载分片：{ts_name}")
                # 对于网络不通畅情况，选择放弃该包
                if not download_ts_test(ts_url):
                    continue
                quit_number = quit_number - 1
                ffmpeg \
                    .input(f"captures/{account}.ts") \
                    .filter('select', 'gte(n,{})'.format(21)) \
                    .output(f'captures/{account}.jpg', vframes=1, format='image2', vcodec='mjpeg') \
                    .run(overwrite_output=True)
                # capture_stderr=True 如果加上这个属性，那么只显示错误信息
                # 不加就会完全显示，使用quiet=True则会完全静默

                t_e = datetime.now()
                t_delta = t_e - t_s
                log.info(f"[测试]分片获取成功:耗时 {(t_delta.total_seconds() * 1000):.3f}ms")
                last_ts_name = ts_name
            time.sleep(0.3)
        except Exception as e:
            log.error(f'{account}:下载直播流时出现问题： {str(e)}')
            time.sleep(1)


def download_ts_test(url: str):
    with requests.get(url, stream=True, timeout=0.5) as ts:
        test_begin = datetime.now()
        if ts.status_code == 200:
            with open(f"captures/{account}.ts", 'wb') as f:
                for chunk in ts.iter_content(chunk_size=128000):
                    test_end = datetime.now()
                    delta = test_end - test_begin
                    if delta.total_seconds() > 0.42:
                        log.warning("分包下载时间预估超过>0.7s，丢弃")
                        return False
                    f.write(chunk)
                    test_begin = datetime.now()
        return True
        # 使用ffmpeg-python来截取一帧图像


# 测试用，使用录制的视频，每10帧截图一次
# 可用于本地测试二维码签到
def capture_test(interval):
    global exit_code
    exit_code = False
    n = 0
    while not exit_code:
        n = n + 10
        try:
            ffmpeg \
                .input('test.mp4') \
                .filter('select', 'gte(n,{})'.format(15 + n)) \
                .output(f'captures/{account}.jpg', vframes=1, format='image2', vcodec='mjpeg') \
                .run(overwrite_output=True, quiet=True)
            log.info("不错")
            # capture_stdout=True
            time.sleep(interval)
        except Exception as e:
            log.error(f'Error: {str(e)}')
            time.sleep(2)  # 出现错误时等待2秒再重试


def test(account_str):
    print("======开始检查各模块运作情况======")
    time.sleep(0.5)
    global account, send_key, password, uid, fid, name
    account = account_str
    for user in users:
        if account == user["acc"]:
            send_key = user["scid"]
            password = user["pw"]
            log.info(f'学号：{account}，密码：{password}，SENDKEY：{send_key}')
    if not password:
        log.error("个人信息配置不完全，请检查")
        sys.exit()
    log.info(f"登录账号中")
    if not os.path.exists(f'cookie/cookie{account}.json'):
        print(f"第一次登录，请耐心等待，可能需要3-10秒……")
        update_account(account, password)

    with open(f'cookie/cookie{account}.json', "r") as cookie_file:
        cookie = json.load(cookie_file)

    ip = randint(111, 255)
    random_code = ''.join(choices(string.ascii_lowercase + string.digits, k=32))
    headers = {
        'User-Agent': f'Dalvik/2.1.0 (Linux; U; Android 13.0.0; Pixel 2 XL Build/OPM4.171019.021.R1) '
                      f'(device:Pixel 2 XL Build) Language/zh_CN '
                      f'com.chaoxing.mobile.xuezaixidian/ChaoXingStudy_1000149_5.3.1_android_phone_5000_83 '
                      f'(@Kalimdor)_{random_code}',
        'X-Forwarded-For': f'113.200.157.{ip}'
    }
    log.info(f'选用的随机ip:113.200.157.{ip}')
    web.cookies.update(cookie)
    web.headers.update(headers)

    test_url = web.get(URL_COURSES)
    if re.findall('双因子登录滑动校验用', test_url.text, re.S):
        log.warning('cookie失效, 正在尝试重新登录')
        update_account(account, password)
    uid = cookie['UID']
    fid = cookie['fid']
    url = web.get('https://i.mooc.chaoxing.com/settings/info')
    name = re.search('<p class="personalName" title="(.*?)"', url.text, re.S).group(1)
    print(f'您的信息：姓名：{name}，UID：{uid}')
    time.sleep(1)

    print("尝试获取课程信息")
    time.sleep(0.5)

    try:
        html = web.get(URL_COURSES)
        pattern = re.compile('<a class="courseName".*?courseid=(.*?)&clazzid=(.*?)&vc.*?title="(.*?)">.*?', re.S)
        courses = re.findall(pattern, html.text)
    except Exception as e:
        log.error(f'{account}:访问{URL_COURSES}时发生错误：{str(e)}')
        time.sleep(3)
    if not courses:
        log.warning(f"{account}无法获取课程，请检查{URL_COURSES}")
    print('成功获取到课程信息，正在为您打印……')
    time.sleep(0.5)
    for unit in courses:
        course_id = unit[0]
        clazz_id = unit[1]
        course_name = unit[2]
        print(f'课程:{course_name} - 课程号:{course_id} - 班级号:{clazz_id}')
    print()
    print("尝试获取您本周的课程表")
    time.sleep(1)
    try:
        html_week = web.get(URL_WEEK_TABLES)
        # 获取年份，学期，周，用于获取课表信息
        week = re.findall('getWeekDetail\(\'(\d{1,2})\'', html_week.text, re.S)[0]
        infer = re.findall('<option  selected  value=".*?">(.*?)-.*?第(.*?)学期</option>', html_week.text, re.S)[0]
        termYear = infer[0]
        if '一' == infer[1]:
            termId = 1
        else:
            termId = 2
        course_url = f'https://newesxidian.chaoxing.com/frontLive/listStudentCourseLivePage?fid={fid}&userId={uid}&' \
                     f'week={week}&termYear={termYear}&termId={termId}&type=1'
        course = web.get(course_url)
        data = json.loads(course.text)
    except Exception as e:
        log.error(f'{account}:获取课表时发生错误: {str(e)}')
    printed_items = set()
    for item in data:
        course_name = item["courseName"]
        week_day = item["weekDay"]
        section = item["section"]
        place = item["place"]
        item_tuple = (course_name, week_day, section, place)

        if item_tuple not in printed_items:
            printed_items.add(item_tuple)
            print(f'课程名:{course_name}, 星期{week_day}, 节次：{section}节, 教室地点：{place}')
    print()
    print('测试滑块验证模块中…')
    print('如果您发现ddddocr的广告，请找到core.py第一行,ctrl+alt+左键 import ddddocr')
    print('以进入它的__init__.py，翻几下就能看到广告')
    time.sleep(0.5)
    try:
        validate = validate_pass(web)
    except Exception as e:
        log.error(f'{account}:执行时发生错误：{str(e)}')
        log.error('可能是execjs编译js文件发生报错，常见于windows')
        log.error('请下载node.js的msi安装包(可配path) 并配置好环境')
        sys.exit()
    print(f'如果验证结果为validate_xxx_xxx即为成功:{validate}')
    if validate == 'callback({"error":0,"msg":"ok","result":false})':
        validate = validate_again(validate, web)
        print(validate)
    print("功能正常")
    time.sleep(0.5)

    print("")
    print("测试二维码解码功能")
    time.sleep(1)
    image = imread(f'captures/TEST.png')
    barcodes = pyzbar.decode(image)
    if len(barcodes):
        for barcode in barcodes:
            barcode_data = barcode.data.decode('utf-8')
    print(f"识别结果：{barcode_data}")

    print("测试直播流抓取")
    get_stream()
    # 建立连接开销较大，第一个分包下载三四秒很正常
    # 红色文字是ffmpeg的提示，虽然是红字但是除非系统终止否则一般没大碍
    # 主要关注网络性能，如果分片无法下载或平均超过750ms则异常

    print("==========测试完毕==========")
    time.sleep(0.4)
    print("除正式签到外的功能已全部测试成功")
    print("如果您是初次使用，请先开启脚本并到课测试一天，确保全部签上再无人值守")


if __name__ == '__main__':
    # 填写一个配置好的学号
    # 测试目的是测试代码能否跑通，测试一个号即可
    test('23009888888')



