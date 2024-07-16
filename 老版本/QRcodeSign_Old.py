from loguru import logger as log
import re
import time
from datetime import datetime, timedelta
from selenium import webdriver
from cv2 import imread, cvtColor, COLOR_BGR2GRAY
from skimage.metrics import structural_similarity as ssim
from pyzbar import pyzbar
from core import account, name, web, uid, fid
from core import validate_pass
# 旧版，采用selenium方式，打开浏览器进行扫码签到(2024.6)
# 采用了无头模式，当时是部署给给低带宽的云服务器用
def qrcode_sign_back(courseid, clazzid, code, first=True):
    refresh_flag = 4
    initial_time = time.time()
    last_barcode_data = 'default'
    image_error = imread('1.png')
    # 使用了edge作为webdriver
    options = webdriver.EdgeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')

    for i in range(5):
        try:
            # 视频读取失败会有一个黑窗
            # 我截好了一个870x540的图，对比相似度需要同分辨率
            driver = webdriver.Edge(options=options)
            driver.set_window_size(870, 540)
            driver.get(
                f'http://newesxidian.chaoxing.com/threepart/index-alihls.html?info=%7B%22type%22%3A%221%22%2C%22videoPath%22%3A%7B%22teacherTrack%22%3A%22http%3A%2F%2F202.117.115.53%3A8092%2Fpag%2F202.117.115.50%2F7302%2F00{code}%2F0%2FMAIN%2FTCP%2Flive.m3u8%22%7D%7D')
            break
        except:
            driver.close()
            continue
    if 4 == i:
        return 0
    # 执行五次后仍无法加载推流页面，则放弃签到
    # 循环截图和二维码识别
    while True:
        current_time = time.time()
        time_diff = (current_time - initial_time) / 60
        if first is True and time_diff > 110:
            driver.close()
            return 1
        # 110分钟未检测到签到，则说明没有检测到二维码，或上课教室有误
        driver.save_screenshot(f'screenshot{account}.png')
        image = imread(f'screenshot{account}.png')
        # 对比故障图片，检测是否卡顿
        gray_image1 = cvtColor(image_error, COLOR_BGR2GRAY)
        gray_image2 = cvtColor(image, COLOR_BGR2GRAY)
        score, diff = ssim(gray_image1, gray_image2, full=True)
        # 如果和故障图片相似度过高，则是网络问题，刷新浏览器
        if score > 0.965:
            driver.refresh()
            log.warning(f'{account}的网页慢，重新加载！')
            time.sleep(10)
        barcodes = pyzbar.decode(image)
        # 扫描出二维码，开始签到
        if len(barcodes):
            for barcode in barcodes:
                barcode_data = barcode.data.decode('utf-8')
                if barcode_data == last_barcode_data:
                    break
                qrcode_information = re.findall('id=(.*?)&.*?enc=(.*?)&DB_STRATEGY', barcode_data)
                if len(qrcode_information) == 0:
                    last_barcode_data = barcode_data
                    break
                log.info(f'{account}识别到二维码，尝试签到')
                for item in qrcode_information:
                    aid = item[0]
                    qrcode_activeid = item[0]
                    enc = item[1]
                web.get(
                    f'http://mobilelearn.chaoxing.com/newsign/preSign?courseId={courseid}&clazzid={clazzid}&activePrimaryId={aid}&general=1&sys=1&ls=1&appType=15&uid=191345671&isTeacherViewOpen=0')
                presign_pattern = web.get(
                    f'http://mobilelearn.chaoxing.com/pptSign/analysis?DB_STRATEGY=RANDOM&aid={aid}').text
                presign_code = re.findall("DB_STRATEGY=RANDOM&code='\+'(.*?)'", presign_pattern, re.S)[0]
                web.get(f'http://mobilelearn.chaoxing.com/pptSign/analysis2?DB_STRATEGY=RANDOM&code={presign_code}')
                html = web.get(
                    f'https://mobilelearn.chaoxing.com/pptSign/errorLocation?DB_STRATEGY=PRIMARY_KEY&STRATEGY_PARA=activeId&activeId={aid}&uid={uid}&location=%7B%22result%22%3A1%2C%22latitude%22%3A%2C%22longitude%22%3A%2C%22address%22%3A%22%22%7D&errortype=errorLocation1')
                location = \
                    re.findall('locationLatitud.*?value="(.*?)".*?locationLong.*?value="(.*?)">', html.text, re.S)[0]
                latitude = location[0]
                longitude = location[1]
                html_half = web.get(
                    f'http://mobilelearn.chaoxing.com/pptSign/stuSignajax?enc={enc}&name={name}&activeId={aid}&uid={uid}&clientip=&location=%7B%22result%22%3A1%2C%22latitude%22%3A{latitude}%2C%22longitude%22%3A{longitude}%2C%22address%22%3A%22%E4%B8%AD%E5%9B%BD%E9%99%95%E8%A5%BF%E7%9C%81%E8%A5%BF%E5%AE%89%E5%B8%82%E9%95%BF%E5%AE%89%E5%8C%BA%E5%85%B4%E9%9A%86%E8%A1%97%E9%81%93%E8%A5%BF%E5%AE%89%E7%94%B5%E5%AD%90%E7%A7%91%E6%8A%80%E5%A4%A7%E5%AD%A6(%E5%8D%97%E6%A0%A1%E5%8C%BA)%22%7D&latitude=-1&longitude=-1&fid={fid}&appType=15').text
                if html_half == "签到失败，请重新扫描。":
                    refresh_flag = refresh_flag - 1
                    if refresh_flag <= 0:
                        print(f"[INFO]让{account}刷新一下")
                        driver.refresh()
                        time.sleep(8)
                if html_half == '您已签到过了':
                    print(f"[INFO]{account}签完了，累死我了。")
                    return 9
                enc2_match = re.search("validate_(\w+)", html_half)
                if enc2_match:
                    enc2 = enc2_match.group(1)
                    # print(presign_code, location, html_half, enc2)
                    validate = validate_pass()
                    # print(f'{datetime.datetime.now().strftime("%H:%M:%S")}：validate识别结果为 {validate}')
                    while validate == 'callback({"error":0,"msg":"ok","result":false})':
                        validate = validate_pass()
                    html_final = web.get(
                        f'http://mobilelearn.chaoxing.com/pptSign/stuSignajax?enc={enc}&name={name}&activeId={aid}&uid={uid}&clientip=&location=%7B%22result%22%3A1%2C%22latitude%22%3A{latitude}%2C%22longitude%22%3A{longitude}%2C%22address%22%3A%22%E4%B8%AD%E5%9B%BD%E9%99%95%E8%A5%BF%E7%9C%81%E8%A5%BF%E5%AE%89%E5%B8%82%E9%95%BF%E5%AE%89%E5%8C%BA%E5%85%B4%E9%9A%86%E8%A1%97%E9%81%93%E8%A5%BF%E5%AE%89%E7%94%B5%E5%AD%90%E7%A7%91%E6%8A%80%E5%A4%A7%E5%AD%A6(%E5%8D%97%E6%A0%A1%E5%8C%BA)%22%7D&latitude=-1&longitude=-1&fid={fid}&appType=15&enc2={enc2}&validate={validate}').text
                    if html_final == 'success' or html_final == '您已签到过了':
                        print(f'[INFO]{datetime.datetime.now().strftime("%H:%M:%S")}:{account}签完啦')
                        return 9
                # 在早期我尝试过实现两次签到，第一次必须签上，第二次无所谓
                # 用于防止某些老师发很多签到
                # 然而实践表明，在教务系统只要签上一次就判定到课
                # 而且实施这些二次签到的老师也没在期末怎么扣平时分
                # html = web.get(
                #     f'http://mobilelearn.chaoxing.com/pptSign/stuSignajax?enc={enc}&name={name}&activeId={aid}&uid={uid}&clientip=&location=%7B%22result%22%3A1%2C%22latitude%22%3A{latitude}%2C%22longitude%22%3A{longitude}%2C%22address%22%3A%22%E4%B8%AD%E5%9B%BD%E9%99%95%E8%A5%BF%E7%9C%81%E8%A5%BF%E5%AE%89%E5%B8%82%E9%95%BF%E5%AE%89%E5%8C%BA%E5%85%B4%E9%9A%86%E8%A1%97%E9%81%93%E8%A5%BF%E5%AE%89%E7%94%B5%E5%AD%90%E7%A7%91%E6%8A%80%E5%A4%A7%E5%AD%A6(%E5%8D%97%E6%A0%A1%E5%8C%BA)%22%7D&latitude=-1&longitude=-1&fid={fid}&appType=15')
                # print(f'{datetime.datetime.now().strftime("%H:%M")}:result of {account} is ' + html.text)
                # if html.text == 'success' or html.text == '您已签到过了':
                #     driver.close()
                #     if first is False:
                #         print(f'{account} 的二次扫码签到 is ' + html.text)
                #     return 9

                # if html.text == '签到失败，请重新扫描。':
                #     refresh_flag= refresh_flag - 1
                #     if refresh_flag <= 0:
                #         print("让{account}刷新一下")
                #         driver.refresh()
                #         time.sleep(8)
                last_barcode_data = barcode_data
        time.sleep(1.3)

# 这是原来course_sign(s1:int, second_sign=False):的一部分
# if second_sign:
#    url = f'https://mobilelearn.chaoxing.com/widget/pcpick/stu/index?'\
#          f'courseId={item["courseId"]}&jclassId={item["teachClazzId"]}'
#    html_str = web.get(url).text
#   if len(re.findall("进行中\(([1-9])\)", html_str, re.S)) > 0:
#        end_index = html_str.find('已结束')
#        if end_index != -1:
#            part = html_str[:end_index]
#            pattern = r'onclick="activeDetail\((\d+)'
#            sign_list = re.findall(pattern, part)
#        for activeId in sign_list:
#            sign_html = web.get(
#               f'https://mobilelearn.chaoxing.com/widget/sign/pcStuSignController/preSign?activeId={activeId}&classId={item["teachClazzId"]}&fid={fid}&courseId={item["courseId"]}')
#            sign_type = re.findall('<title>学生端-(.*?)<', sign_html.text, re.S)
#            if sign_type[0] == '签到' or sign_type[0] == '位置签到':
#                normal_sign()
#            if sign_type[0] == '二维码签到' and qrcode_activeid != activeId:
#                qrcode_sign(item["courseId"], item["teachClazzId"], code, False)
#return