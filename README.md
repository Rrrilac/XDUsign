<h2>某高校全自动课程签到脚本<h2>
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

2024.7.16 v1.0
添加注释并更换selenium方式采集为m3u8流直接采集
添加功能测试入口
制作懒人包，省去配环境的麻烦
