import re
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import (
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


GID_REGEX = re.compile(r"^[A-Za-z0-9]{118}$")
# 保持与最开始脚本一致的入口：先走 authserver/login?service=...，登录后再进入服务大厅/成绩查询
LOGIN_ENTRY_URL = "https://auth.bjmu.edu.cn/authserver/login?service=http%3A%2F%2Fapps.bjmu.edu.cn%2Flogin%3Fservice%3Dhttp%3A%2F%2Fapps.bjmu.edu.cn%2F%2Fywtb-portal%2Fofficialbjmu%2Findex.html"


def extract_gid_from_url(url: str) -> str | None:
    parsed = urlparse(url)

    query_params = parse_qs(parsed.query)
    value = query_params.get("gid_", [None])[0]
    if value:
        if GID_REGEX.match(value):
            return value

    if parsed.fragment:
        fragment_params = parse_qs(parsed.fragment)
        value = fragment_params.get("gid_", [None])[0]
        if value:
            if GID_REGEX.match(value):
                return value

    match = re.search(r"(?:[?&#]|^)gid_=([A-Za-z0-9]{118})", url)
    if match:
        candidate = match.group(1)
        if GID_REGEX.match(candidate):
            return candidate

    return None


def _pick_visible(locator):
    count = locator.count()
    for index in range(count):
        candidate = locator.nth(index)
        if candidate.is_visible():
            return candidate
    return locator.first


def fetch_gid(playwright: Playwright, username: str, password: str) -> str:
    browser = playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(30_000)

    try:
        page.goto(LOGIN_ENTRY_URL, wait_until="domcontentloaded")

        if "auth.bjmu.edu.cn/authserver/login" in page.url:
            username_input = _pick_visible(page.locator("input#username"))
            password_input = _pick_visible(page.locator("input#password"))
            submit_button = _pick_visible(page.locator("a#login_submit"))

            username_input.wait_for(state="visible", timeout=30_000)
            username_input.fill(username)
            password_input.fill(password)
            submit_button.wait_for(state="visible", timeout=30_000)
            try:
                with page.expect_navigation(
                    wait_until="domcontentloaded", timeout=30_000
                ):
                    submit_button.click()
            except PlaywrightTimeoutError:
                # 有的情况下登录是局部刷新/重定向较慢：给一点缓冲，并在仍停留登录页时抛错
                page.wait_for_timeout(3_000)
                if "auth.bjmu.edu.cn/authserver/login" in page.url:
                    raise

        try:
            page.locator(".name:has-text('服务大厅')").click(timeout=10_000)
        except PlaywrightTimeoutError:
            pass

        try:
            with page.expect_popup(timeout=10_000) as popup_info:
                try:
                    page.locator("label[title='成绩查询']").click()
                except PlaywrightTimeoutError:
                    raise
            target = popup_info.value
        except PlaywrightTimeoutError:
            try:
                page.locator("label[title='成绩查询']").click()
            except PlaywrightTimeoutError:
                raise
            target = page

        target.wait_for_load_state("domcontentloaded")
        try:
            target.wait_for_url(re.compile(r".*gid_=[A-Za-z0-9]{118}"), timeout=15_000)
        except PlaywrightTimeoutError:
            pass

        gid = extract_gid_from_url(target.url)
        if not gid:
            raise ValueError(f"未在成绩查询页面 URL 中找到有效的 gid_: {target.url}")
        return gid
    finally:
        context.close()
        browser.close()


if __name__ == "__main__":
    with sync_playwright() as playwright:
        user = input("Username: ").strip()
        pwd = input("Password: ").strip()
        print(fetch_gid(playwright, user, pwd))
