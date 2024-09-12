import ddddocr
import execjs
import ffmpeg
import json
import os
import re
import requests
import string
import sys
import time
import threading
from datetime import datetime, timedelta
from multiprocessing import Process
from loguru import logger as log
from random import choices, randint
from cv2 import imread
from pyzbar import pyzbar

account, send_key, password, uid, fid, name, exit_code = [None] * 7
web = requests.session()
# 如果部署云服务器，建议windows server（已测试）  
# 或centos+宝塔面板，经测试3M带宽情况下稳定极限是三线程  
# 设定捕捉直播流时片段超时时间，供低带宽云服务器使用，建议在0.3-0.6(s)，一个ts片段是1s
# 可通过解开capture()的注释部分测试
TIMEOUT = 0.42
URL_XDU_LOGIN = 'https://ids.xidian.edu.cn/authserver/login?service=http://xyt.learning.xidian.edu.cn/ydd/login'
URL_COURSES = 'https://mooc1-2.chaoxing.com/visit/courses'
URL_WEEK_TABLES = 'https://newesxidian.chaoxing.com/frontLive/studentSelectCourse1'
# 这是你定位签到会显示的位置信息，经纬度则会和教师位置一致
ADDRESS_DEFAULT = '中国陕西省西安市长安区兴隆街道西安电子科技大学(南校区)'

# ===============用户配置部分===================
# scid: Serverchan_SendKey_ID [server酱的推送码]
# 注册网站后复制即可： https://sct.ftqq.com/login
# 可以把签到消息发送给你的微信，记得公众号设置开启通知
# acc: 学号  pw: 密码 [统一认证登录]
# 填不满五个的话留空即可
users = [
    {"acc": "", "scid": "", "pw": ""},
    {"acc": "", "scid": "", "pw": ""},
    {"acc": "", "scid": "", "pw": ""},
    {"acc": "", "scid": "", "pw": ""},
    {"acc": "", "scid": "", "pw": ""}
]
# =============================================


def load_account(account_input: str):
    # 开始处理用户相关信息，利用cookie登录超星系统
    global account, send_key, password, uid, fid, name
    account = account_input
    for user in users:
        if account == user["acc"]:
            send_key = user["scid"]
            password = user["pw"]

    if not os.path.exists(f'cookie/cookie{account}.json'):
        log.info(f"未发现{account}的cookie文件，尝试登录中…")
        log.info(f"登陆时间可能较久，请耐心等待…")
        update_account(account, password)
    with open(f'cookie/cookie{account}.json', "r") as cookie_file:
        cookie = json.load(cookie_file)

    # 随机机器码，防止同一设备警告
    # 超星的新认证方式会检测ip，如果是服务器公网ip会触发validate，伪造ip就不会了
    ip = randint(111, 255)
    random_code = ''.join(choices(string.ascii_lowercase + string.digits, k=32))
    headers = {
        'User-Agent': f'Dalvik/2.1.0 (Linux; U; Android 13.0.0; Pixel 2 XL Build/OPM4.171019.021.R1) '
                      f'(device:Pixel 2 XL Build) Language/zh_CN '
                      f'com.chaoxing.mobile.xuezaixidian/ChaoXingStudy_1000149_5.3.1_android_phone_5000_83 '
                      f'(@Kalimdor)_{random_code}',
        'X-Forwarded-For': f'113.200.157.{ip}'
    }
    web.cookies.update(cookie)
    web.headers.update(headers)

    # 检验使用的cookie有效性
    test = web.get(URL_COURSES)
    if re.findall('双因子登录滑动校验用', test.text, re.S):
        log.warning('cookie失效, 正在尝试重新登录')
        update_account(account, password)
    uid = cookie['UID']
    fid = cookie['fid']
    url = web.get('https://i.mooc.chaoxing.com/settings/info')
    name = re.search('<p class="personalName" title="(.*?)"', url.text, re.S).group(1)

    log.info(f'账号{account}开始24小时无人值守签到啦~')

    # 启动课程时间表
    time_table()


# 寻找教室对应的推流序号
def get_code(place: str):
    with open('DATA.txt', 'r') as file:
        for line in file:
            if line.startswith(place):
                return str(line.split('\t')[1]).strip()
    return None


def get_weekcourse():
    headers_refresh = {
        'User-Agent': f'Dalvik/2.1.0 (Linux; U; Android 13.0.0; Pixel 2 XL Build/OPM4.171019.021.R1) '
                      f'(device:Pixel 2 XL Build) Language/zh_CN '
                      f'com.chaoxing.mobile.xuezaixidian/ChaoXingStudy_1000149_5.3.1_android_phone_5000_83 '
                      f"(@Kalimdor)_{''.join(choices(string.ascii_lowercase + string.digits, k=32))}"
    }
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
        return data
    except Exception as e:
        log.error(f'{account}:获取课表时发生错误: {str(e)}')
        web.headers.update(headers_refresh)
        time.sleep(15)


def self_check():
    test = web.get(URL_COURSES)
    if re.findall('双因子登录滑动校验用', test.text, re.S):
        log.info("【自检】------账号过期，重新登陆------")
        update_account(account, password)


# 其实可以用全局变量，但是为了做测试接口，保留局部变量，会话也单独设置变量
def update_account(account_input: str, password_input: str):
    web_login = requests.session()

    def load_js():
        with open('encrypt.js', 'r', encoding='UTF-8') as a:
            line = a.readline()
            javascript = ''
            while line:
                javascript = javascript + line
                line = a.readline()
            return javascript

    while True:
        # 获得登录所需的salt和execution
        login_start = web_login.get(URL_XDU_LOGIN)
        salt_pattern = re.compile('<input type="hidden" id="pwdEncryptSalt" value="(.*?)"', re.S)
        key = re.findall(salt_pattern, login_start.text)[0]
        execution = re.findall('id="execution" name="execution" value="(.*?)"', login_start.text, re.S)[0]

        # javascript调用函数: encrypt_password = encryptPassword(pwd0, key)
        # 加盐密码
        ctx = execjs.compile(load_js())
        encrypt_password = ctx.call('encryptPassword', password_input, key)
        # 检查encrypt.js是否需要更换
        # print(encrypt_password)

        data = {
            'username': account_input,
            'password': encrypt_password,
            'cappresign_patternha': '',
            'rememberMe': 'true',
            '_eventId': 'submit',
            'cllt': 'userNameLogin',
            'dllt': 'generalLogin',
            'execution': execution
        }
        headers = {
            'Referer': URL_XDU_LOGIN,
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/124.0.0.0 Safari/537.36 '
        }
        # 含金量最高的部分，没有之一
        # 反复提交滑动长度114的结果，总有一次能过（匹配机制是误差小于5就能过)
        data_captcha = {'canvasLength': 280, 'moveLength': 114}
        while True:
            web_login.get("https://ids.xidian.edu.cn/authserver/common/openSliderCaptcha.htl?_=114514")
            login_captcha = web_login.post("https://ids.xidian.edu.cn/authserver/common/verifySliderCaptcha.htl",
                                           data=data_captcha)
            if login_captcha.text == '{"errorCode":1,"errorMsg":"success"}':
                break
            time.sleep(0.6)

        login = web_login.post(url=URL_XDU_LOGIN, data=data, headers=headers)
        if login.status_code == 401:
            timeout_msg = f"因登录失败，签到程序无法进行，请检查密码是否正确"
            requests.get(f"https://sctapi.ftqq.com/{send_key}.send?title={timeout_msg}")
            log.error(timeout_msg)
            sys.exit()
        else:
            log.info(f'{account_input}登录成功')
            break

    with open(f'cookie/cookie{account_input}.json', 'w', encoding='UTF-8') as f:
        cookie = requests.utils.dict_from_cookiejar(login.cookies)
        f.write(json.dumps(cookie))
    with open(f'cookie/cookie{account_input}.json', "r") as h:
        cookie_new = json.load(h)
    web.cookies.update(cookie_new)


# 定时处理定位签到和普通签到 支持滑块验证码
# 西电已经不开放手势和签到码签到所以没有开发这个功能
def normal_sign():
    # 一直定时访问的话可能被掐，更新UA后刷新
    headers_refresh = {
        'User-Agent': f'Dalvik/2.1.0 (Linux; U; Android 13.0.0; Pixel 2 XL Build/OPM4.171019.021.R1) '
                      f'(device:Pixel 2 XL Build) Language/zh_CN '
                      f'com.chaoxing.mobile.xuezaixidian/ChaoXingStudy_1000149_5.3.1_android_phone_5000_83 '
                      f"(@Kalimdor)_{''.join(choices(string.ascii_lowercase + string.digits, k=32))}"
    }
    while True:
        try:
            html = web.get(URL_COURSES)
            pattern = re.compile('<a class="courseName".*?courseid=(.*?)&clazzid=(.*?)&vc.*?title="(.*?)">.*?', re.S)
            courses = re.findall(pattern, html.text)
            break
        except Exception as e:
            course_fail_msg = f'{account}:Error: {str(e)}'
            log.error(course_fail_msg)
            requests.get(f"https://sctapi.ftqq.com/{send_key}.send?title={course_fail_msg}")
            web.headers.update(headers_refresh)
            time.sleep(15)
    if not courses:
        log.warning(f"{account}本次获取课程失败！过会再签吧")
        return
    for unit in courses:
        course_id = unit[0]
        clazz_id = unit[1]
        course_name = unit[2]
        url = f'https://mobilelearn.chaoxing.com/widget/pcpick/stu/index?courseId={course_id}&jclassId={clazz_id}'
        html_str = web.get(url).text
        ak = re.findall(r'进行中\((\d{1,2})\)', html_str, re.S)
        if ak:
            end_index = html_str.find('已结束')
            if end_index != -1:
                part = html_str[:end_index]
                pattern = r'onclick="activeDetail\((\d+)'
                sign_list = re.findall(pattern, part)
            for active_id in sign_list:
                sign_html = web.get(
                    f'https://mobilelearn.chaoxing.com/widget/sign/pcStuSignController/preSign?activeId={active_id}'
                    f'&classId={clazz_id}&fid={fid}&courseId={course_id}')
                sign_type = re.findall('<title>学生端-(.*?)<', sign_html.text, re.S)
                if sign_type[0] == '签到':
                    validate = validate_pass(web)
                    validate = validate_again(validate, web)
                    web.get(
                        f'https://mobilelearn.chaoxing.com/widget/sign/pcStuSignController/signIn?courseId={course_id}'
                        f'&classId={clazz_id}&activeId={active_id}&validate={validate}')
                elif sign_type[0] == '位置签到':
                    web.get(
                        f'http://mobilelearn.chaoxing.com/newsign/preSign?courseId={course_id}&clazzid={clazz_id}'
                        f'&activePrimaryId={active_id}&general=1&sys=1&ls=1&appType=15&uid={uid}&isTeacherViewOpen=0')
                    presign_pattern = web.get(
                        f'http://mobilelearn.chaoxing.com/pptSign/analysis?DB_STRATEGY=RANDOM&aid={active_id}').text
                    p = re.findall("DB_STRATEGY=RANDOM&code='\+'(.*?)'", presign_pattern, re.S)
                    presign_code = p[0]
                    web.get(
                        f'http://mobilelearn.chaoxing.com/pptSign/analysis2?DB_STRATEGY=RANDOM&code={presign_code}').text
                    time.sleep(2)
                    html = web.get(
                        f'https://mobilelearn.chaoxing.com/pptSign/errorLocation?'
                        f'DB_STRATEGY=PRIMARY_KEY&STRATEGY_PARA=activeId&activeId={active_id}')
                    location = re.search('Latitude.*?value="(.*?)".*?Longitude" value="(.*?)">', html.text, re.S)
                    latitude = location.group(1)
                    longitude = location.group(2)
                    # 如果发布的定位没有距离限制，则默认发送A楼定位
                    if len(latitude) == 0:
                        latitude = 34.132591
                        longitude = 108.838502
                    # 强行加上validate，提交以后也可以通过无验证码的定位签到
                    validate = validate_pass(web)
                    validate = validate_again(validate, web)
                    device_code = f"{''.join(choices(string.ascii_letters + string.digits, k=32))}" \
                                  f"oZ4tVAn2TkbLrU5KaqE5c2nrYcLjiTPsIvES0bMOtfX445GAQKnMrMo+3W2FKfGichnoLiFd2iU= "
                    # 2024.7 新增设备指纹（防同一设备多次签到）以及定位作弊检测
                    # 然而这些是针对设备码以及模拟定位软件的，对直接网络访问无影响
                    location_url = f'https://mobilelearn.chaoxing.com/pptSign/stuSignajax?address={ADDRESS_DEFAULT}&' \
                                   f'activeId={active_id}&latitude={latitude}&longitude={longitude}&fid=0&appType=15&'\
                                   f'ifTiJiao=1&validate={validate}&deviceCode={device_code}&vpProbability=-1&vpStrategy='
                    # 暂时不考虑发送到微信，个人认为无关紧要
                    log.info(f'{account}：检测到来自{course_name}的位置签到，签到结果为' + web.get(location_url).text)


def course_sign(s1: int):
    day = datetime.now().weekday() + 1
    course_data = None
    while course_data is None:
        try:
            course_data = get_weekcourse()
        except Exception as e:
            log.error(f'{account}：课表获取失败 {str(e)}')
            time.sleep(30)
    s2 = s1 + 1
    for item in course_data:
        if item["weekDay"] == day and item["section"] == f'{s1}-{s2}':
            try:
                code = get_code(item['place'])
                result = qrcode_sign(item["courseId"], item["teachClazzId"], code)
            except Exception as e:
                log.error(f'{account}:课程签到出错： {str(e)}')
                global exit_code
                exit_code = True
                result = 0
            result_str = {
                0: '星期' + str(day) + '的' + str(s1) + '-' + str(s2) + '节签到线程启动失败，发生什么事了……',
                1: '星期' + str(day) + '的' + str(s1) + '-' + str(s2) + '节全程未检测到二维码，发生什么事了……',
                9: '星期' + str(day) + '的' + str(s1) + '-' + str(s2) + '节已为您代签'
            }
            requests.get(f'https://sctapi.ftqq.com/{send_key}.send?title={result_str[result]}')
            return


def qrcode_sign(courseid: str, clazzid: str, code: str):
    global exit_code
    final_time = datetime.now() + timedelta(minutes=115)
    last_barcode_data = 'default'
    stream_url = f'http://202.117.115.53:8092/pag/202.117.115.50/7302/00{code}/0/MAIN/TCP/live.m3u8'
    thread = threading.Thread(target=capture, args=(stream_url, 1.8))
    thread.start()
    while not os.path.exists(f'captures/{account}.jpg'):
        time.sleep(2)
    # 循环截图和二维码识别
    while True:
        current_time = datetime.now()
        if current_time > final_time:
            log.warning(f'{account}扫了整节课都没扫上……')
            exit_code = True
            os.remove(f'captures/{account}.jpg')
            return 1
        try:
            image = imread(f'captures/{account}.jpg')
            barcodes = pyzbar.decode(image)
        except Exception as e:
            log.error(f'{account}:解析图片异常: {str(e)}')
            continue
        # 扫描出二维码，开始签到
        if len(barcodes):
            for barcode in barcodes:
                barcode_data = barcode.data.decode('utf-8')
                if barcode_data == last_barcode_data:
                    break
                qrcode_information = re.findall('id=(.*?)&.*?enc=(.*?)&DB_STRATEGY', barcode_data)
                if not len(qrcode_information):
                    last_barcode_data = barcode_data
                    break
                log.info(f'{account}识别到二维码，尝试签到')
                for item in qrcode_information:
                    aid = item[0]
                    enc = item[1]
                # 查询活动，如果已经签过则显示结果，没签过则开始引导签到
                web.get(
                    f'https://mobilelearn.chaoxing.com/newsign/preSign?courseId={courseid}&clazzid={clazzid}'
                    f'&activePrimaryId={aid}&general=1&sys=1&ls=1&appType=15&uid={uid}&isTeacherViewOpen=0')

                # 预签到，这个无需cookie，应该是认证在session上的
                presign_pattern = web.get(
                    f'https://mobilelearn.chaoxing.com/pptSign/analysis?DB_STRATEGY=RANDOM&aid={aid}').text
                presign_code = re.findall("DB_STRATEGY=RANDOM&code='\+'(.*?)'", presign_pattern, re.S)[0]
                web.get(f'https://mobilelearn.chaoxing.com/pptSign/analysis2?DB_STRATEGY=RANDOM&code={presign_code}')

                # 发送错误信息，超星返回的结果里会含有发起者的位置信息，提取之
                html = web.get(
                    f'https://mobilelearn.chaoxing.com/pptSign/errorLocation?'
                    f'DB_STRATEGY=PRIMARY_KEY&STRATEGY_PARA=activeId&activeId={aid}')
                location = re.search('Latitude.*?value="(.*?)".*?Longitude" value="(.*?)">', html.text, re.S)
                latitude = location.group(1)
                longitude = location.group(2)

                # 这里可能有三种情况
                # 1.没有滑块验证，未完成签到
                # 2.有滑块验证，未完成签到
                # 3.本人线下已经签上了
                device_code = f"{''.join(choices(string.ascii_letters + string.digits, k=32))}" \
                              f"oZ4tVAn2TkbLrU5KaqE5c2nrYcLjiTPsIvES0bMOtfX445GAQKnMrMo+3W2FKfGichnoLiFd2iU= "
                sign_ordinary = web.get(
                    f'https://mobilelearn.chaoxing.com/pptSign/stuSignajax?enc={enc}&name={name}'
                    f'&activeId={aid}&uid={uid}&clientip=&location={{"result":1,"latitude":{latitude},"longitude":{longitude},"mockData": {{"strategy": 0,"probability": -1}},"address":"{ADDRESS_DEFAULT}"}}&latitude=-1&longitude=-1&fid={fid}'
                    f'&appType=15&deviceCode={device_code}&vpProbability=-1&vpStrategy=').text
                # 直播推流延迟过高可能导致二维码失效
                if sign_ordinary == "签到失败，请重新扫描。" or sign_ordinary == "非本班学生":
                    pass
                if sign_ordinary == 'success' or sign_ordinary == '您已签到过了':
                    log.info(f'{account}签完啦')
                    exit_code = True
                    os.remove(f'captures/{account}.jpg')
                    return 9
                enc2_match = re.search("validate_(\w+)", sign_ordinary)
                if enc2_match:
                    enc2 = enc2_match.group(1)
                    # 识别成功率在90%左右，再加一个作为保险机制
                    validate = validate_pass(web)
                    validate = validate_again(validate, web)
                    sign_validate = web.get(
                        f'https://mobilelearn.chaoxing.com/pptSign/stuSignajax?enc={enc}&name={name}&activeId={aid}'
                        f'&uid={uid}&clientip=&location={{"result":1,"latitude":{latitude},"longitude":{longitude},"mockData": {{"strategy": 0,"probability": -1}},"address":"{ADDRESS_DEFAULT}"}}&latitude=-1&longitude=-1&fid={fid}&appType=15'
                        f'&enc2={enc2}&validate={validate}&deviceCode={device_code}&vpProbability=-1&vpStrategy=').text
                    if sign_validate == 'success' or sign_validate == '您已签到过了':
                        log.info(f'{account}签完啦')
                        exit_code = True
                        os.remove(f'captures/{account}.jpg')
                        return 9
                last_barcode_data = barcode_data
        time.sleep(1.3)


# 目前探明的机制：和签到活动完全无关
# 通过验证码获得一个短暂时效的票据，加在发起签到的参数中
# 但需要登录账户才能访问否则403
# 开发人员注意：captcha_id可能会和version可能会变
# 变了的话在这更改，同时也需要编辑generateCaptchaKey.js
# 把末尾的captcha_id值给改了
def validate_pass(web_v):
    with open('generateCaptchaKey.js', encoding='utf-8') as f:
        js = f.read()
    # 通过compile命令转成一个js对象
    docjs = execjs.compile(js)
    # 调用function
    res = docjs.call('generateCaptchaKey')
    ckey = res['captchaKey']
    token = res['token']
    captcha_id = 'Qt9FIw9o4pwRjOyqM6yizZBh682qN2TU'
    referer = 'https://mobilelearn.chaoxing.com/newsign/preSign'
    version = '1.1.20'
    # 这里的captchaId和version可能会变化，3-6个月变一次?
    text_test = web_v.get(
        f"https://captcha.chaoxing.com/captcha/get/verification/image?callback=callback&captchaId={captcha_id}"
        f"&type=slide&version={version}&captchaKey={ckey}&token={token}&referer={referer}").text
    captcha_data = json.loads(re.search(r'\{.*\}', text_test)[0])
    # captcha_data["imageVerificationVo"]["shadeImage"]对应了图片的URL
    try:
        background = web_v.get(captcha_data["imageVerificationVo"]["shadeImage"]).content
        target = web_v.get(captcha_data["imageVerificationVo"]["cutoutImage"]).content
    except Exception as e:
        log.error(f'无法获取验证码，captcha_id可能发生变化！已终止程序，请尽快排查----{str(e)}')
        web_v.get(f'https://sctapi.ftqq.com/{send_key}.send?title=程序意外终止，请查看日志')
        sys.exit()
    token_new = captcha_data["token"]
    det = ddddocr.DdddOcr(det=False, ocr=False)
    res_det = det.slide_match(target, background)

    data_check = {
        "callback": "callback",
        "captchaId": captcha_id,
        "type": "slide",
        "token": token_new,
        "textClickArr": ('[{{\"x\":{x}}}]').format(x=res_det['target'][0]),
        "coordinate": "[]",
        "runEnv": "10",
        "version": version
    }
    res_check = web_v.get("http://captcha.chaoxing.com/captcha/check/verification/result",
                        params=data_check, headers={"Referer": referer})
    check_result = json.loads(re.search(r'\{.*\}', res_check.text)[0])
    if check_result['result']:
        return json.loads(check_result['extraData'])['validate']
    else:
        return res_check.text


def validate_again(validate_msg: str, web_vv):
    while validate_msg == 'callback({"error":0,"msg":"ok","result":false})':
        v_limit = 4
        validate_msg = validate_pass(web_vv)
        v_limit = v_limit - 1
        if not v_limit:
            fatal_error = f'{account}:滑块验证机制出现故障，签到程序被迫终止'
            log.error(fatal_error)
            requests.get(f"https://sctapi.ftqq.com/{send_key}.send?title=程序意外终止，请查看日志")
            sys.exit()
    return validate_msg


def time_table():
    count = 0
    # 时间表，时间一到就访问网络，匹配第's1'节课
    time_params = [
        {"start_time": "08:20", "end_time": "10:10", "s1": 1},
        {"start_time": "10:14", "end_time": "12:05", "s1": 3},
        {"start_time": "13:50", "end_time": "15:40", "s1": 5},
        {"start_time": "15:44", "end_time": "17:35", "s1": 7},
        {"start_time": "18:50", "end_time": "20:35", "s1": 9}
    ]

    def within_timing(start_time, end_time):
        current_time = datetime.now().strftime("%H:%M")
        # 超星的cookies有效期大约是半个月，每日自检是否有效
        if current_time == "08:00":
            self_check()
        return start_time <= current_time <= end_time


    while True:
        for param in time_params:
            if within_timing(param["start_time"], param["end_time"]):
                # 如果进入时间，就发起签到
                course_sign(param["s1"])
                # 签到完毕以后，课程剩余时间检测其他签到
                while within_timing(param["start_time"], param["end_time"]):
                    if (count % 10) == 0:
                        count = 0
                        normal_sign()
                    count = count + 1
                    time.sleep(59)
        if (count % 10) == 0:
            count = 0
            normal_sign()
        count = count + 1
        time.sleep(59)


@log.catch
def capture(url: str, interval: int):
    global exit_code
    last_ts_name = None
    exit_code = False
    while not exit_code:
        try:
            # 使用requests库获取M3U8文件内容
            response = requests.get(url)
            m3u8_content = response.text
            # 找到TS流的URL（通常在M3U8文件中以.ts结尾）
            ts_name = m3u8_content.splitlines()[-1]
            # 对于网络通畅情况，选择等待下一个包
            if ts_name != last_ts_name:
                ts_url = url.rsplit('/', 1)[0] + '/' + ts_name
                # 我真的是气死，timeout属性必须放最前面，但ffmpeg-python的开发作者没想到这个
                # 只能本地保存.ts了

                # 对于网络不通畅情况，选择放弃该包
                if not download_ts(ts_url):
                    continue
                ffmpeg \
                    .input(f"captures/{account}.ts") \
                    .filter('select', 'gte(n,{})'.format(21)) \
                    .output(f'captures/{account}.jpg', vframes=1, format='image2', vcodec='mjpeg') \
                    .run(overwrite_output=True, capture_stderr=True)
                last_ts_name = ts_name
            time.sleep(interval)
        except Exception as e:
            log.error(f'{account}:本帧下载异常： {str(e)}')
            time.sleep(1)


def download_ts(url: str):
    with requests.get(url, stream=True, timeout=0.5) as ts:
        test_begin = datetime.now()
        if ts.status_code == 200:
            with open(f"captures/{account}.ts", 'wb') as f:
                for chunk in ts.iter_content(chunk_size=128000):
                    test_end = datetime.now()
                    delta = test_end - test_begin
                    if delta.total_seconds() > TIMEOUT:
                        # log.warning("分包下载时间过长，丢弃")
                        return False
                    f.write(chunk)
                    test_begin = datetime.now()
        log.info('downloaded')
        return True
        # 使用ffmpeg-python来截取一帧图像


def WanDianMing():
    load_account('23009209999')
    # python中，字符串(str)可以用'内容'，"内容"表示
    code = get_code('A-105')
    qrcode_sign('9999999', '8888888', code)
    # qrcode_sign(courseid, clazzid, code)
    # courseid是课程id, clazzid是班级id，访问源码头部的URL_COURSES
    # 点击发晚点名签到的课程，即可在网址处看到该课的courseid和clazzid
    # 把参数都换成你的就可以使用了


if __name__ == '__main__':
    # 设定默认目录为当前目录，可兼容linux和windows
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    # 晚点名专用，使用前先配置函数
    # WanDianMing()

    # 如果是第一次使用请查阅开头部分，完成用户信息配置
    # 在此处填充你需要签到的学号，多余的行需要删除
    # 支持多进程
    # 在正式启动前请打开TEST.py 进行功能检查
    Process(target=load_account, args=('2300920xxxx',)).start()
    Process(target=load_account, args=('2300920yyyy',)).start()
    Process(target=load_account, args=('23009208888',)).start()







