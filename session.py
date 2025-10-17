#!/usr/bin/env python
# -*- encoding: utf-8 -*-
# @Author  :   Arthals
# @File    :   session.py
# @Time    :   2025/01/25 01:44:46
# @Contact :   zhuozhiyongde@126.com
# @Software:   Visual Studio Code


import base64
import json
import random
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad


AES_CHARS = "ABCDEFGHJKMNPQRSTWXYZabcdefhijkmnprstwxyz2345678"
GRADE_INDEX_URL = "https://apps.bjmu.edu.cn/jwapp/sys/cjcx/*default/index.do"
GRADE_QUERY_URL = (
    "https://apps.bjmu.edu.cn/jwapp/sys/cjcx/modules/cjcx/xscjcx.do"
)
GRADE_SERVICE_GID = (
    "V3hMVFErb1V5QzlMTmVSUFZNd3E0Z3kxQzRxeE1VQWlPemFDQnJJWVV2cUNBQzVLVWVDM0R0Q2VR"
    "bzNPM1Q4MDlKQlcxK2NDWXFKZXVndkFvaXlFdnc9PQ"
)


class Session(requests.Session):
    def __init__(self, config, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._config = config
        self.verify = False  # PKUHSC 证书链经常异常，关闭校验更稳
        requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
        self._grade_referer = None
        self.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Connection": "keep-alive",
            }
        )

    def __del__(self):
        self.close()

    def get(self, url, *args, **kwargs):
        res = super().get(url, *args, **kwargs)
        res.raise_for_status()
        return res

    def post(self, url, *args, **kwargs):
        res = super().post(url, *args, **kwargs)
        res.raise_for_status()
        return res

    def login(self) -> bool:
        """登录北医医学部统一身份认证"""
        login_url = self._build_login_url()
        login_page = self.get(login_url)
        soup = BeautifulSoup(login_page.text, "html.parser")

        lt = soup.find("input", {"name": "lt"})
        execution = soup.find("input", {"name": "execution"})
        salt = soup.find("input", {"id": "pwdEncryptSalt"})
        if not all([lt, execution, salt]):
            raise ValueError("登录页缺少必要字段，无法继续登录")

        encrypted_pwd = self._encrypt_password(
            self._config["password"], salt["value"]
        )

        form_data = {
            "username": self._config["username"],
            "password": encrypted_pwd,
            "captcha": "",
            "_eventId": "submit",
            "cllt": "userNameLogin",
            "dllt": "generalLogin",
            "lt": lt["value"],
            "execution": execution["value"],
            "rmShown": "1",
        }

        # 发送登录请求并跟随重定向直到进入成绩系统
        login_headers = dict(self.headers)
        login_headers.update(
            {
                "Referer": login_page.url,
                "Origin": "https://auth.bjmu.edu.cn",
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )

        response = self.post(
            login_page.url,
            data=form_data,
            allow_redirects=True,
            headers=login_headers,
        )
        if "统一身份认证平台" in response.text:
            raise ValueError("统一身份认证失败，请检查账号或密码")

        # 登录成功后记录成绩页面，用于后续成绩查询 Referer
        self._grade_referer = response.url or GRADE_INDEX_URL
        self.headers["Referer"] = self._grade_referer
        return True

    def _build_login_url(self) -> str:
        timestamp = int(time.time() * 1000)
        service = (
            f"{GRADE_INDEX_URL}"
            f"?t_s={timestamp}&amp_sec_version_=1&gid_={GRADE_SERVICE_GID}"
            "&EMAP_LANG=zh&THEME=bjmu#/cjcx"
        )
        encoded_service = quote(service, safe="")
        return f"https://auth.bjmu.edu.cn/authserver/login?service={encoded_service}"

    def get_grade(self):
        """获取成绩"""
        payload = {
            "querySetting": json.dumps(
                [
                    {
                        "name": "SFYX",
                        "caption": "是否有效",
                        "linkOpt": "AND",
                        "builderList": "cbl_m_List",
                        "builder": "m_value_equal",
                        "value": "1",
                        "value_display": "是",
                    },
                    {
                        "name": "SHOWMAXCJ",
                        "caption": "显示最高成绩",
                        "linkOpt": "AND",
                        "builderList": "cbl_m_List",
                        "builder": "m_value_equal",
                        "value": 0,
                        "value_display": "否",
                    },
                ],
                ensure_ascii=False,
            ),
            "*order": "-XNXQDM,-KCH,-KXH",
            "pageSize": 999,
            "pageNumber": 1,
        }

        headers = {
            "Origin": "https://apps.bjmu.edu.cn",
            "Referer": self._grade_referer or GRADE_INDEX_URL,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }

        res = self.post(GRADE_QUERY_URL, data=payload, headers=headers).json()
        if res.get("code") not in ("0", 0):
            raise ValueError(f"获取成绩失败: {res}")

        return res

    def _encrypt_password(self, password: str, salt: str) -> str:
        random_prefix = "".join(random.choices(AES_CHARS, k=64))
        iv = "".join(random.choices(AES_CHARS, k=16))

        payload = (random_prefix + password).encode("utf-8")
        cipher = AES.new(salt.encode("utf-8")[:16], AES.MODE_CBC, iv.encode("utf-8"))

        encrypted_bytes = cipher.encrypt(pad(payload, AES.block_size, style="pkcs7"))
        return base64.b64encode(encrypted_bytes).decode("utf-8")
