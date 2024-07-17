![](https://img.shields.io/badge/Python-3.10.1-blue)
![](https://img.shields.io/badge/version-1.0.1-green)
## 某高校全自动课程签到模块
基于采集课程直播流实现的二维码签到  

支持XDU特有的二维码+定位课程签到  
自动获取课程，到点自动采集二维码并提交签到  
支持滑块验证码自动识别

带有告警系统和多重稳定机制，网络不好也能用  
python万岁😌

可部署服务器实现24小时全程运行  
方便实用，直到下一个意外出现  
（一般是系统升级改参数）  
脚本含有大量注释，方便排查更新  

支持签到消息推送微信（server酱）  


>2024.7.16 v1.0.1
>添加注释 换selenium采集方式为m3u8流直接采集  
>添加功能测试入口  
>制作整合包，省去配环境的麻烦  


## 使用说明
核心文件为core.py  
功能测试文件为TEST.py  
DATA.txt存放了支持采集直播流的教室

已经自带requirements.txt了,建议python版本3.10  
需要ffmpeg和node.js环境  
对python编程不太熟悉的或者懒得配环境的  
可以下载整合包  
链接：https://pan.quark.cn/s/629cedc42074

