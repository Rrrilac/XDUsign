![](https://img.shields.io/badge/Python-3.10.1-blue)
![](https://img.shields.io/badge/version-1.0.1-green)
## 某高校全自动课程签到模块
>有时，你会遇到一些尴尬  
>痛得快来不及请假，但导员仿佛在度假  
>事后补假办材料虽是正义，但有时还是过于繁琐  
>好麻烦……可不办，75%的红线会逼你办  

唉 有没有什么应急*~~食物~~*策略呢  
有的呢亲！基于采集课程直播流实现的二维码签到上线啦   

支持XDU特有的二维码+定位课程签到  
自动获取课程，到点自动采集二维码并提交签到  
支持滑块验证码自动识别  

带有告警系统和多重稳定机制，提高网络不稳定环境的成功率    
python万岁😌

支持签到结果消息推送微信（server酱）  
含有大量注释，方便排查修改 

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
(9.12注：下完整合包再把core.py和test.py拉取一下，整合包里的是旧版

## 友情提醒
本模块仅供计算机开发方向学习使用，或给特殊需求的同学应急  
例如请假批准过晚等，可缓和部分考勤和重要需求的冲突  
作者只是提供工具，而工具如何使用在于人    
**不鼓励将其作为长期不到课的作弊工具，同时本模块自带一定的失败概率（大约1-5％）**  
**如果您因滥用此工具受到学校处分，或因工具未能如期运行造成了缺勤，本工具概不负责**  
**禁止用于收费代课！！！**
